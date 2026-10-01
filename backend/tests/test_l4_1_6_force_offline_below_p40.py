"""
L4.1.6: force a driver offline when commission leaves the wallet at P0
or negative.

Ride completion itself does not change availability. The existing 8%
commission, ledger posting, and marketplace/go-online above-P0 rules stay
as-is.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.constants.ride_status import RideStatus
from app.constants.verification import VerificationStatus
from app.constants.wallet import WalletEntryType
from app.models.driver_wallet import DriverWallet
from app.models.passenger import Passenger
from app.models.ride_request import RideRequest
from app.models.user import User
from app.models.vehicle import Vehicle
from app.models.wallet_ledger_entry import WalletLedgerEntry
from app.services.marketplace_service import MarketplaceService
from app.utils.money import (
    COMMISSION_RATE,
    DRIVER_WALLET_BELOW_MINIMUM,
    MIN_DRIVER_WALLET,
    calculate_commission,
    driver_wallet_meets_minimum,
)
from tests.ride_flow import (
    advance_to_accepted,
    create_pending_ride,
    prepare_driver_online,
)


FARE_P40 = Decimal("40.00")
COMMISSION_P40 = Decimal("3.20")
ABOVE_START = Decimal("100.00")
ZERO_START = Decimal("3.20")
NEGATIVE_START = Decimal("1.00")
ONE_THEBE_START = Decimal("3.21")


def _fare_payload(amount: float) -> dict:
    return {
        "pickup_location": "Main Mall",
        "pickup_latitude": -24.6545,
        "pickup_longitude": 25.9086,
        "destination": "Airport Junction",
        "destination_latitude": -24.6278,
        "destination_longitude": 25.9059,
        "proposed_fare": amount,
    }


def _set_wallet(db_session: Session, driver_id: int, amount: Decimal) -> None:
    db_session.expire_all()
    db_session.execute(
        update(DriverWallet)
        .where(DriverWallet.driver_id == driver_id)
        .values(available_balance=amount)
        .execution_options(synchronize_session="fetch")
    )
    db_session.commit()
    db_session.expire_all()


def _complete_selected_ride(client, headers, ride_id: int) -> dict:
    assert client.put(f"/rides/{ride_id}/arrive", headers=headers).status_code == 200
    assert client.put(
        f"/rides/{ride_id}/driver-arrived",
        headers=headers,
    ).status_code == 200
    assert client.put(f"/rides/{ride_id}/start", headers=headers).status_code == 200
    complete = client.put(f"/rides/{ride_id}/complete", headers=headers)
    assert complete.status_code == 200, complete.text
    return complete.json()


def _complete_ride_from_wallet(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
    start_balance: Decimal,
    fare: Decimal = FARE_P40,
) -> dict:
    _set_wallet(db_session, authenticated_driver["user"].id, start_balance)
    selected = advance_to_accepted(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        authenticated_driver["user"].id,
        payload=_fare_payload(float(fare)),
    )
    body = _complete_selected_ride(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        selected["id"],
    )
    db_session.expire_all()
    return body


def _driver_row(db_session: Session, driver_id: int) -> User:
    driver = db_session.get(User, driver_id)
    assert driver is not None
    return driver


def _wallet_row(db_session: Session, driver_id: int) -> DriverWallet:
    wallet = (
        db_session.query(DriverWallet)
        .filter(DriverWallet.driver_id == driver_id)
        .one()
    )
    return wallet


def _commission_entries(db_session: Session, ride_id: int) -> list[WalletLedgerEntry]:
    return (
        db_session.query(WalletLedgerEntry)
        .filter(
            WalletLedgerEntry.ride_id == ride_id,
            WalletLedgerEntry.entry_type == WalletEntryType.COMMISSION,
        )
        .all()
    )


def _snapshot_driver(db_session: Session, driver_id: int) -> dict:
    driver = _driver_row(db_session, driver_id)
    vehicles = (
        db_session.query(Vehicle)
        .filter(Vehicle.driver_id == driver_id)
        .order_by(Vehicle.id.asc())
        .all()
    )
    return {
        "full_name": driver.full_name,
        "email": driver.email,
        "phone_number": driver.phone_number,
        "role": driver.role,
        "verification_status": driver.verification_status,
        "current_latitude": driver.current_latitude,
        "current_longitude": driver.current_longitude,
        "last_seen": driver.last_seen,
        "profile_photo_url": driver.profile_photo_url,
        "vehicle_statuses": {
            vehicle.id: vehicle.verification_status for vehicle in vehicles
        },
    }


def _snapshot_passenger(db_session: Session, passenger_id: int) -> dict:
    passenger = db_session.get(Passenger, passenger_id)
    assert passenger is not None
    user = db_session.get(User, passenger.user_id)
    assert user is not None
    return {
        "first_name": passenger.first_name,
        "last_name": passenger.last_name,
        "phone": passenger.phone,
        "email": passenger.email,
        "user_id": passenger.user_id,
        "user_role": user.role,
        "user_email": user.email,
        "user_availability": user.availability_status,
    }


def test_commission_rate_is_still_eight_percent():
    assert COMMISSION_RATE == Decimal("0.08")
    assert MIN_DRIVER_WALLET == Decimal("0.00")
    assert calculate_commission(FARE_P40) == COMMISSION_P40
    assert driver_wallet_meets_minimum(Decimal("0.01")) is True
    assert driver_wallet_meets_minimum(Decimal("0.00")) is False


def test_commission_above_p40_leaves_driver_available(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    driver_id = authenticated_driver["user"].id
    body = _complete_ride_from_wallet(
        authenticated_passenger,
        authenticated_driver,
        db_session,
        ABOVE_START,
    )
    expected_balance = ABOVE_START - COMMISSION_P40
    assert expected_balance > MIN_DRIVER_WALLET
    assert body["status"] == RideStatus.COMPLETED
    assert Decimal(str(_wallet_row(db_session, driver_id).available_balance)) == (
        expected_balance
    )
    assert _driver_row(db_session, driver_id).availability_status == "available"


def test_commission_to_zero_forces_available_driver_offline(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    driver_id = authenticated_driver["user"].id
    body = _complete_ride_from_wallet(
        authenticated_passenger,
        authenticated_driver,
        db_session,
        ZERO_START,
    )
    expected_balance = ZERO_START - COMMISSION_P40
    assert expected_balance == MIN_DRIVER_WALLET
    assert not driver_wallet_meets_minimum(expected_balance)
    assert body["status"] == RideStatus.COMPLETED
    assert Decimal(str(_wallet_row(db_session, driver_id).available_balance)) == (
        expected_balance
    )
    assert _driver_row(db_session, driver_id).availability_status == "offline"


def test_already_offline_driver_stays_offline_when_wallet_hits_zero(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    driver_id = authenticated_driver["user"].id
    _set_wallet(db_session, driver_id, ZERO_START)
    selected = advance_to_accepted(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        driver_id,
        payload=_fare_payload(float(FARE_P40)),
    )
    headers = authenticated_driver["headers"]
    client = authenticated_driver["client"]
    assert client.put(f"/rides/{selected['id']}/arrive", headers=headers).status_code == 200
    assert client.put(
        f"/rides/{selected['id']}/driver-arrived",
        headers=headers,
    ).status_code == 200
    assert client.put(f"/rides/{selected['id']}/start", headers=headers).status_code == 200

    db_session.expire_all()
    driver = _driver_row(db_session, driver_id)
    driver.availability_status = "offline"
    db_session.commit()
    assert _driver_row(db_session, driver_id).availability_status == "offline"

    complete = client.put(f"/rides/{selected['id']}/complete", headers=headers)
    assert complete.status_code == 200, complete.text
    db_session.expire_all()
    assert Decimal(str(_wallet_row(db_session, driver_id).available_balance)) == (
        MIN_DRIVER_WALLET
    )
    assert _driver_row(db_session, driver_id).availability_status == "offline"


def test_one_thebe_after_commission_does_not_force_offline(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    driver_id = authenticated_driver["user"].id
    body = _complete_ride_from_wallet(
        authenticated_passenger,
        authenticated_driver,
        db_session,
        ONE_THEBE_START,
    )
    remaining = Decimal(str(_wallet_row(db_session, driver_id).available_balance))
    assert remaining == Decimal("0.01")
    assert driver_wallet_meets_minimum(remaining)
    assert body["status"] == RideStatus.COMPLETED
    assert _driver_row(db_session, driver_id).availability_status == "available"


def test_commission_to_negative_forces_available_driver_offline(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    driver_id = authenticated_driver["user"].id
    body = _complete_ride_from_wallet(
        authenticated_passenger,
        authenticated_driver,
        db_session,
        NEGATIVE_START,
    )
    remaining = Decimal(str(_wallet_row(db_session, driver_id).available_balance))
    assert remaining == NEGATIVE_START - COMMISSION_P40
    assert remaining < MIN_DRIVER_WALLET
    assert body["status"] == RideStatus.COMPLETED
    assert _driver_row(db_session, driver_id).availability_status == "offline"


def test_commission_ledger_and_completed_ride_unchanged_when_forced_offline(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    driver_id = authenticated_driver["user"].id
    body = _complete_ride_from_wallet(
        authenticated_passenger,
        authenticated_driver,
        db_session,
        ZERO_START,
    )
    ride_id = body["id"]
    entries = _commission_entries(db_session, ride_id)
    assert len(entries) == 1
    assert entries[0].entry_type == WalletEntryType.COMMISSION
    assert Decimal(str(entries[0].amount)) == -COMMISSION_P40
    assert Decimal(str(entries[0].balance_after)) == ZERO_START - COMMISSION_P40
    assert entries[0].driver_id == driver_id
    assert entries[0].ride_id == ride_id

    ride = db_session.get(RideRequest, ride_id)
    assert ride is not None
    assert ride.status == RideStatus.COMPLETED
    assert ride.accepted_driver_id == driver_id
    assert Decimal(str(ride.agreed_fare)) == FARE_P40
    assert _driver_row(db_session, driver_id).availability_status == "offline"


def test_force_offline_does_not_mutate_unrelated_state(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    driver_id = authenticated_driver["user"].id
    passenger = authenticated_passenger["passenger"]
    _set_wallet(db_session, driver_id, ZERO_START)
    selected = advance_to_accepted(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        driver_id,
        payload=_fare_payload(float(FARE_P40)),
    )
    headers = authenticated_driver["headers"]
    client = authenticated_driver["client"]
    assert client.put(f"/rides/{selected['id']}/arrive", headers=headers).status_code == 200
    assert client.put(
        f"/rides/{selected['id']}/driver-arrived",
        headers=headers,
    ).status_code == 200
    assert client.put(f"/rides/{selected['id']}/start", headers=headers).status_code == 200

    db_session.expire_all()
    before_driver = _snapshot_driver(db_session, driver_id)
    before_passenger = _snapshot_passenger(db_session, passenger.id)
    assert before_driver["verification_status"] == VerificationStatus.APPROVED
    assert before_driver["current_latitude"] is not None
    assert before_driver["current_longitude"] is not None
    assert _driver_row(db_session, driver_id).availability_status == "busy"

    complete = client.put(f"/rides/{selected['id']}/complete", headers=headers)
    assert complete.status_code == 200, complete.text

    db_session.expire_all()
    after_driver = _snapshot_driver(db_session, driver_id)
    after_passenger = _snapshot_passenger(db_session, passenger.id)
    assert after_driver == before_driver
    assert after_passenger == before_passenger
    assert _driver_row(db_session, driver_id).availability_status == "offline"
    assert db_session.get(RideRequest, selected["id"]).status == RideStatus.COMPLETED


def test_zero_after_commission_cannot_go_online(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    _complete_ride_from_wallet(
        authenticated_passenger,
        authenticated_driver,
        db_session,
        ZERO_START,
    )
    driver_id = authenticated_driver["user"].id
    assert Decimal(str(_wallet_row(db_session, driver_id).available_balance)) == (
        MIN_DRIVER_WALLET
    )
    assert _driver_row(db_session, driver_id).availability_status == "offline"

    response = authenticated_driver["client"].put(
        "/drivers/go-online",
        headers=authenticated_driver["headers"],
    )
    assert response.status_code == 400
    assert response.json()["detail"] == DRIVER_WALLET_BELOW_MINIMUM
    assert _driver_row(db_session, driver_id).availability_status == "offline"


def test_zero_after_commission_excluded_from_marketplace(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    _complete_ride_from_wallet(
        authenticated_passenger,
        authenticated_driver,
        db_session,
        ZERO_START,
    )
    driver_id = authenticated_driver["user"].id
    assert Decimal(str(_wallet_row(db_session, driver_id).available_balance)) == (
        MIN_DRIVER_WALLET
    )

    db_session.expire_all()
    driver = _driver_row(db_session, driver_id)
    driver.availability_status = "available"
    db_session.commit()

    eligible_ids = {row.id for row in MarketplaceService.eligible_drivers(db_session)}
    assert driver_id not in eligible_ids

    with patch(
        "app.services.notification_service.NotificationService.notify_marketplace_request_created"
    ) as broadcast:
        created = create_pending_ride(
            authenticated_passenger["client"],
            authenticated_passenger["headers"],
        )
    notified = {call.kwargs["driver_id"] for call in broadcast.call_args_list}
    assert driver_id not in notified

    late = authenticated_driver["client"].put(
        f"/rides/{created['id']}/respond",
        headers=authenticated_driver["headers"],
        json={"response_type": "accept_passenger_offer"},
    )
    assert late.status_code == 400
    assert late.json()["detail"] == DRIVER_WALLET_BELOW_MINIMUM


def test_offline_transition_is_from_wallet_not_completion(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    driver_id = authenticated_driver["user"].id
    above = _complete_ride_from_wallet(
        authenticated_passenger,
        authenticated_driver,
        db_session,
        ABOVE_START,
    )
    assert above["status"] == RideStatus.COMPLETED
    assert Decimal(str(_wallet_row(db_session, driver_id).available_balance)) > (
        MIN_DRIVER_WALLET
    )
    assert _driver_row(db_session, driver_id).availability_status == "available"

    prepare_driver_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    below = _complete_ride_from_wallet(
        authenticated_passenger,
        authenticated_driver,
        db_session,
        ZERO_START,
    )
    assert below["status"] == RideStatus.COMPLETED
    assert Decimal(str(_wallet_row(db_session, driver_id).available_balance)) == (
        MIN_DRIVER_WALLET
    )
    assert _driver_row(db_session, driver_id).availability_status == "offline"
