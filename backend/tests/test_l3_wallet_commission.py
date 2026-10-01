"""
L3 wallet + 8% commission: above-P0 operating gate, exactly-once ledger
posting, no commission on cancel, no commission cap.
"""
from __future__ import annotations

import threading
from decimal import Decimal
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker

from app import config
from app.constants.ride_status import RideStatus
from app.constants.wallet import WalletEntryType
from app.models.driver_wallet import DriverWallet
from app.models.ride_request import RideRequest
from app.models.user import User
from app.models.wallet_ledger_entry import WalletLedgerEntry
from app.services.ride_service import RideService
from app.services.wallet_service import WalletService
from app.utils.money import (
    COMMISSION_RATE,
    DRIVER_WALLET_BELOW_MINIMUM,
    LAUNCH_SEED_AMOUNT,
    MIN_DRIVER_WALLET,
    calculate_commission,
    driver_net_from_agreed,
    driver_wallet_meets_minimum,
)
from tests.ride_flow import (
    advance_to_accepted,
    create_pending_ride,
    prepare_driver_online,
)


def _complete_selected_ride(client, headers, ride_id: int):
    assert client.put(f"/rides/{ride_id}/arrive", headers=headers).status_code == 200
    assert client.put(
        f"/rides/{ride_id}/driver-arrived",
        headers=headers,
    ).status_code == 200
    assert client.put(f"/rides/{ride_id}/start", headers=headers).status_code == 200
    complete = client.put(f"/rides/{ride_id}/complete", headers=headers)
    assert complete.status_code == 200, complete.text
    return complete.json()


def test_commission_examples_have_no_cap():
    assert COMMISSION_RATE == Decimal("0.08")
    assert calculate_commission(Decimal("20.00")) == Decimal("1.60")
    assert calculate_commission(Decimal("40.00")) == Decimal("3.20")
    assert driver_net_from_agreed(Decimal("40.00")) == Decimal("36.80")
    assert calculate_commission(Decimal("70.00")) == Decimal("5.60")
    assert calculate_commission(Decimal("100.00")) == Decimal("8.00")
    assert driver_net_from_agreed(Decimal("100.00")) == Decimal("92.00")
    assert calculate_commission(Decimal("150.00")) == Decimal("12.00")
    assert calculate_commission(Decimal("1000.00")) == Decimal("80.00")


def test_new_driver_wallet_is_seeded_at_p40(
    driver_user: User,
    db_session: Session,
):
    db_session.expire_all()
    seed = (
        db_session.query(WalletLedgerEntry)
        .filter(
            WalletLedgerEntry.driver_id == driver_user.id,
            WalletLedgerEntry.entry_type == WalletEntryType.LAUNCH_SEED,
        )
        .one()
    )
    assert Decimal(str(seed.amount)) == LAUNCH_SEED_AMOUNT
    assert LAUNCH_SEED_AMOUNT == Decimal("40.00")
    assert MIN_DRIVER_WALLET == Decimal("0.00")
    assert driver_wallet_meets_minimum(Decimal("0.01")) is True
    assert driver_wallet_meets_minimum(Decimal("0.00")) is False
    assert driver_wallet_meets_minimum(Decimal("-0.01")) is False


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


def test_commission_posted_once_on_completed_p40(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    _set_wallet(db_session, authenticated_driver["user"].id, Decimal("40.00"))
    payload = {
        "pickup_location": "Main Mall",
        "pickup_latitude": -24.6545,
        "pickup_longitude": 25.9086,
        "destination": "Airport Junction",
        "destination_latitude": -24.6278,
        "destination_longitude": 25.9059,
        "proposed_fare": 40.0,
    }
    selected = advance_to_accepted(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        authenticated_driver["user"].id,
        payload=payload,
    )
    body = _complete_selected_ride(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        selected["id"],
    )
    assert body["status"] == "completed"
    assert body["agreed_fare"] == 40.0

    db_session.expire_all()
    entries = (
        db_session.query(WalletLedgerEntry)
        .filter(
            WalletLedgerEntry.ride_id == selected["id"],
            WalletLedgerEntry.entry_type == WalletEntryType.COMMISSION,
        )
        .all()
    )
    assert len(entries) == 1
    assert Decimal(str(entries[0].amount)) == Decimal("-3.20")
    wallet = (
        db_session.query(DriverWallet)
        .filter(DriverWallet.driver_id == authenticated_driver["user"].id)
        .one()
    )
    assert Decimal(str(wallet.available_balance)) == Decimal("36.80")

    second = authenticated_driver["client"].put(
        f"/rides/{selected['id']}/complete",
        headers=authenticated_driver["headers"],
    )
    assert second.status_code == 400
    db_session.expire_all()
    assert (
        db_session.query(WalletLedgerEntry)
        .filter(
            WalletLedgerEntry.ride_id == selected["id"],
            WalletLedgerEntry.entry_type == WalletEntryType.COMMISSION,
        )
        .count()
        == 1
    )


def test_commission_on_p100_and_no_cap_on_large_fare(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    _set_wallet(db_session, authenticated_driver["user"].id, Decimal("40.00"))
    selected = advance_to_accepted(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        authenticated_driver["user"].id,
        payload={
            "pickup_location": "Main Mall",
            "pickup_latitude": -24.6545,
            "pickup_longitude": 25.9086,
            "destination": "Airport Junction",
            "destination_latitude": -24.6278,
            "destination_longitude": 25.9059,
            "proposed_fare": 100.0,
        },
    )
    _complete_selected_ride(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        selected["id"],
    )
    db_session.expire_all()
    entry = (
        db_session.query(WalletLedgerEntry)
        .filter(
            WalletLedgerEntry.ride_id == selected["id"],
            WalletLedgerEntry.entry_type == WalletEntryType.COMMISSION,
        )
        .one()
    )
    assert Decimal(str(entry.amount)) == Decimal("-8.00")
    wallet = (
        db_session.query(DriverWallet)
        .filter(DriverWallet.driver_id == authenticated_driver["user"].id)
        .one()
    )
    assert Decimal(str(wallet.available_balance)) == Decimal("32.00")


def test_no_commission_on_cancelled_ride(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    _set_wallet(db_session, authenticated_driver["user"].id, Decimal("40.00"))
    prepare_driver_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    created = create_pending_ride(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
    )
    cancelled = authenticated_passenger["client"].put(
        f"/rides/{created['id']}/cancel",
        headers=authenticated_passenger["headers"],
    )
    assert cancelled.status_code == 200
    db_session.expire_all()
    assert (
        db_session.query(WalletLedgerEntry)
        .filter(WalletLedgerEntry.entry_type == WalletEntryType.COMMISSION)
        .count()
        == 0
    )
    wallet = (
        db_session.query(DriverWallet)
        .filter(DriverWallet.driver_id == authenticated_driver["user"].id)
        .one()
    )
    assert Decimal(str(wallet.available_balance)) == LAUNCH_SEED_AMOUNT


def test_wallet_at_zero_cannot_go_online(
    authenticated_driver,
    db_session: Session,
):
    _set_wallet(
        db_session,
        authenticated_driver["user"].id,
        Decimal("0.00"),
    )

    response = authenticated_driver["client"].put(
        "/drivers/go-online",
        headers=authenticated_driver["headers"],
    )
    assert response.status_code == 400
    assert response.json()["detail"] == DRIVER_WALLET_BELOW_MINIMUM


def test_wallet_negative_cannot_go_online(
    authenticated_driver,
    db_session: Session,
):
    _set_wallet(
        db_session,
        authenticated_driver["user"].id,
        Decimal("-0.01"),
    )

    response = authenticated_driver["client"].put(
        "/drivers/go-online",
        headers=authenticated_driver["headers"],
    )
    assert response.status_code == 400
    assert response.json()["detail"] == DRIVER_WALLET_BELOW_MINIMUM


def test_wallet_above_zero_can_go_online(
    authenticated_driver,
    db_session: Session,
):
    prepare_driver_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    authenticated_driver["client"].put(
        "/drivers/go-offline",
        headers=authenticated_driver["headers"],
    )
    _set_wallet(
        db_session,
        authenticated_driver["user"].id,
        Decimal("0.01"),
    )

    response = authenticated_driver["client"].put(
        "/drivers/go-online",
        headers=authenticated_driver["headers"],
    )
    assert response.status_code == 200, response.text
    db_session.expire_all()
    assert (
        db_session.get(User, authenticated_driver["user"].id).availability_status
        == "available"
    )


def test_wallet_below_old_p40_still_eligible_to_respond(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    prepare_driver_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    _set_wallet(
        db_session,
        authenticated_driver["user"].id,
        Decimal("10.00"),
    )

    with patch(
        "app.services.notification_service.NotificationService.notify_marketplace_request_created"
    ) as broadcast:
        created = create_pending_ride(
            authenticated_passenger["client"],
            authenticated_passenger["headers"],
        )
    notified = {call.kwargs["driver_id"] for call in broadcast.call_args_list}
    assert authenticated_driver["user"].id in notified

    late = authenticated_driver["client"].put(
        f"/rides/{created['id']}/respond",
        headers=authenticated_driver["headers"],
        json={"response_type": "accept_passenger_offer"},
    )
    assert late.status_code == 200, late.text


def test_wallet_at_zero_excluded_from_broadcast_and_respond(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    prepare_driver_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    _set_wallet(
        db_session,
        authenticated_driver["user"].id,
        Decimal("0.00"),
    )

    with patch(
        "app.services.notification_service.NotificationService.notify_marketplace_request_created"
    ) as broadcast:
        created = create_pending_ride(
            authenticated_passenger["client"],
            authenticated_passenger["headers"],
        )
    notified = {call.kwargs["driver_id"] for call in broadcast.call_args_list}
    assert authenticated_driver["user"].id not in notified

    late = authenticated_driver["client"].put(
        f"/rides/{created['id']}/respond",
        headers=authenticated_driver["headers"],
        json={"response_type": "accept_passenger_offer"},
    )
    assert late.status_code == 400
    assert late.json()["detail"] == DRIVER_WALLET_BELOW_MINIMUM


def test_wallet_and_performance_endpoints_after_complete(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    _set_wallet(db_session, authenticated_driver["user"].id, Decimal("40.00"))
    selected = advance_to_accepted(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        authenticated_driver["user"].id,
        payload={
            "pickup_location": "Main Mall",
            "pickup_latitude": -24.6545,
            "pickup_longitude": 25.9086,
            "destination": "Airport Junction",
            "destination_latitude": -24.6278,
            "destination_longitude": 25.9059,
            "proposed_fare": 40.0,
        },
    )
    _complete_selected_ride(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        selected["id"],
    )
    wallet = authenticated_driver["client"].get(
        "/drivers/wallet",
        headers=authenticated_driver["headers"],
    )
    assert wallet.status_code == 200
    assert wallet.json()["available_balance"] == 36.8
    assert wallet.json()["minimum_balance"] == 0.0
    assert wallet.json()["meets_minimum"] is True

    performance = authenticated_driver["client"].get(
        "/drivers/performance",
        headers=authenticated_driver["headers"],
    )
    assert performance.status_code == 200
    body = performance.json()
    assert body["completed_rides"] == 1
    assert body["today_gross"] == 40.0
    assert body["today_commission"] == 3.2
    assert body["today_net"] == 36.8
    assert body["commission_rate"] == 0.08
    assert body["wallet_balance"] == 36.8
    assert body["wallet_minimum"] == 0.0
    assert body["meets_wallet_minimum"] is True


def test_demand_uses_real_pickups_only(
    authenticated_passenger,
    authenticated_driver,
):
    prepare_driver_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    create_pending_ride(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
    )
    demand = authenticated_driver["client"].get(
        "/drivers/demand",
        headers=authenticated_driver["headers"],
    )
    assert demand.status_code == 200
    body = demand.json()
    assert body["window_minutes"] == 60
    assert sum(cell["count"] for cell in body["cells"]) >= 1
    assert any(item["self"] for item in body["online_drivers"])


def test_driver_requests_list_open_marketplace_rides(
    authenticated_passenger,
    authenticated_driver,
):
    prepare_driver_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    created = create_pending_ride(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
    )
    listed = authenticated_driver["client"].get(
        "/drivers/requests",
        headers=authenticated_driver["headers"],
    )
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 1
    assert rows[0]["ride_id"] == created["id"]
    assert rows[0]["passenger_current_offer"] == 150.0
    assert rows[0]["my_response"] is None
    assert rows[0]["cash"] is True
    assert "pickup_eta_seconds" in rows[0]
    assert "trip_distance_km" in rows[0]


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


def _commission_entries(db_session: Session, ride_id: int) -> list[WalletLedgerEntry]:
    db_session.expire_all()
    return (
        db_session.query(WalletLedgerEntry)
        .filter(
            WalletLedgerEntry.ride_id == ride_id,
            WalletLedgerEntry.entry_type == WalletEntryType.COMMISSION,
        )
        .all()
    )


def test_commission_on_p20_p70_and_p150(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    cases = (
        (Decimal("20.00"), Decimal("1.60"), Decimal("38.40")),
        (Decimal("70.00"), Decimal("5.60"), Decimal("34.40")),
        (Decimal("150.00"), Decimal("12.00"), Decimal("28.00")),
    )
    for fare, commission, expected_balance in cases:
        _set_wallet(db_session, authenticated_driver["user"].id, Decimal("40.00"))
        selected = advance_to_accepted(
            authenticated_passenger["client"],
            authenticated_passenger["headers"],
            authenticated_driver["client"],
            authenticated_driver["headers"],
            authenticated_driver["user"].id,
            payload=_fare_payload(float(fare)),
        )
        _complete_selected_ride(
            authenticated_driver["client"],
            authenticated_driver["headers"],
            selected["id"],
        )
        entries = _commission_entries(db_session, selected["id"])
        assert len(entries) == 1
        assert Decimal(str(entries[0].amount)) == -commission
        wallet = (
            db_session.query(DriverWallet)
            .filter(DriverWallet.driver_id == authenticated_driver["user"].id)
            .one()
        )
        assert Decimal(str(wallet.available_balance)) == expected_balance


def test_no_commission_on_incomplete_in_progress_ride(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    _set_wallet(db_session, authenticated_driver["user"].id, Decimal("40.00"))
    selected = advance_to_accepted(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        authenticated_driver["user"].id,
        payload=_fare_payload(40.0),
    )
    ride_id = selected["id"]
    headers = authenticated_driver["headers"]
    client = authenticated_driver["client"]
    assert client.put(f"/rides/{ride_id}/arrive", headers=headers).status_code == 200
    assert client.put(
        f"/rides/{ride_id}/driver-arrived",
        headers=headers,
    ).status_code == 200
    assert client.put(f"/rides/{ride_id}/start", headers=headers).status_code == 200
    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride.status == RideStatus.IN_PROGRESS
    assert (
        db_session.query(WalletLedgerEntry)
        .filter(WalletLedgerEntry.entry_type == WalletEntryType.COMMISSION)
        .count()
        == 0
    )


def test_unselected_driver_is_not_commissioned(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    _set_wallet(db_session, authenticated_driver["user"].id, Decimal("40.00"))
    selected = advance_to_accepted(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        authenticated_driver["user"].id,
        payload=_fare_payload(40.0),
    )
    _complete_selected_ride(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        selected["id"],
    )
    entries = _commission_entries(db_session, selected["id"])
    assert len(entries) == 1
    assert entries[0].driver_id == authenticated_driver["user"].id


def test_post_completion_commission_is_idempotent(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
    test_session_factory: sessionmaker,
):
    _set_wallet(db_session, authenticated_driver["user"].id, Decimal("40.00"))
    selected = advance_to_accepted(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        authenticated_driver["user"].id,
        payload=_fare_payload(40.0),
    )
    _complete_selected_ride(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        selected["id"],
    )
    session = test_session_factory()
    try:
        ride = session.get(RideRequest, selected["id"])
        second = WalletService.post_completion_commission(session, ride)
        session.commit()
    finally:
        session.close()
    assert second == Decimal("3.20")
    entries = _commission_entries(db_session, selected["id"])
    assert len(entries) == 1
    wallet = (
        db_session.query(DriverWallet)
        .filter(DriverWallet.driver_id == authenticated_driver["user"].id)
        .one()
    )
    assert Decimal(str(wallet.available_balance)) == Decimal("36.80")


def test_concurrent_completion_posts_one_commission(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
    test_session_factory: sessionmaker,
):
    _set_wallet(db_session, authenticated_driver["user"].id, Decimal("40.00"))
    selected = advance_to_accepted(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        authenticated_driver["user"].id,
        payload=_fare_payload(40.0),
    )
    ride_id = selected["id"]
    headers = authenticated_driver["headers"]
    client = authenticated_driver["client"]
    assert client.put(f"/rides/{ride_id}/arrive", headers=headers).status_code == 200
    assert client.put(
        f"/rides/{ride_id}/driver-arrived",
        headers=headers,
    ).status_code == 200
    assert client.put(f"/rides/{ride_id}/start", headers=headers).status_code == 200

    errors: list[Exception] = []
    results: list[str] = []

    def _complete() -> None:
        session = test_session_factory()
        try:
            RideService.complete_ride(
                session,
                ride_id,
                session.get(User, authenticated_driver["user"].id),
            )
            results.append("ok")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
            results.append("fail")
            session.rollback()
        finally:
            session.close()

    threads = [threading.Thread(target=_complete) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results.count("ok") == 1
    assert results.count("fail") == 1
    assert errors
    assert all(
        isinstance(exc, HTTPException) and exc.status_code == 400
        for exc in errors
    )
    entries = _commission_entries(db_session, ride_id)
    assert len(entries) == 1
    assert Decimal(str(entries[0].amount)) == Decimal("-3.20")
    wallet = (
        db_session.query(DriverWallet)
        .filter(DriverWallet.driver_id == authenticated_driver["user"].id)
        .one()
    )
    assert Decimal(str(wallet.available_balance)) == Decimal("36.80")
    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride.status == RideStatus.COMPLETED


def test_concurrent_commission_service_posts_once(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
    test_session_factory: sessionmaker,
):
    _set_wallet(db_session, authenticated_driver["user"].id, Decimal("40.00"))
    selected = advance_to_accepted(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        authenticated_driver["user"].id,
        payload=_fare_payload(40.0),
    )
    amounts: list[Decimal] = []
    errors: list[Exception] = []

    def _post() -> None:
        session = test_session_factory()
        try:
            ride = session.get(RideRequest, selected["id"])
            amounts.append(WalletService.post_completion_commission(session, ride))
            session.commit()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
            session.rollback()
        finally:
            session.close()

    threads = [threading.Thread(target=_post) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert amounts == [Decimal("3.20"), Decimal("3.20")]
    entries = _commission_entries(db_session, selected["id"])
    assert len(entries) == 1
    wallet = (
        db_session.query(DriverWallet)
        .filter(DriverWallet.driver_id == authenticated_driver["user"].id)
        .one()
    )
    assert Decimal(str(wallet.available_balance)) == Decimal("36.80")


def test_internal_wallet_credit_and_no_public_self_credit(
    authenticated_driver,
    db_session: Session,
):
    public = authenticated_driver["client"].post(
        "/drivers/wallet/credit",
        headers=authenticated_driver["headers"],
        json={"amount": 50},
    )
    assert public.status_code in (404, 405, 422)

    _set_wallet(db_session, authenticated_driver["user"].id, Decimal("36.80"))
    with patch.object(config, "INTERNAL_VERIFY_SECRET", "test-internal-secret"):
        credited = authenticated_driver["client"].post(
            f"/internal/drivers/{authenticated_driver['user'].id}/wallet/credit",
            headers={
                **authenticated_driver["headers"],
                "X-NEXO-INTERNAL-SECRET": "test-internal-secret",
            },
            json={"amount": 10},
        )
    assert credited.status_code == 200, credited.text
    body = credited.json()
    assert body["available_balance"] == 46.8
    assert body["meets_minimum"] is True
    db_session.expire_all()
    credit_rows = (
        db_session.query(WalletLedgerEntry)
        .filter(
            WalletLedgerEntry.driver_id == authenticated_driver["user"].id,
            WalletLedgerEntry.entry_type == WalletEntryType.CREDIT,
        )
        .all()
    )
    assert len(credit_rows) == 1
    assert Decimal(str(credit_rows[0].amount)) == Decimal("10.00")
    assert Decimal(str(credit_rows[0].balance_after)) == Decimal("46.80")


def test_wallet_ledger_history_includes_seed_and_commission(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    _set_wallet(db_session, authenticated_driver["user"].id, Decimal("40.00"))
    selected = advance_to_accepted(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        authenticated_driver["user"].id,
        payload=_fare_payload(40.0),
    )
    _complete_selected_ride(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        selected["id"],
    )
    wallet = authenticated_driver["client"].get(
        "/drivers/wallet",
        headers=authenticated_driver["headers"],
    )
    assert wallet.status_code == 200
    ledger = wallet.json()["ledger"]
    types = [entry["entry_type"] for entry in ledger]
    assert WalletEntryType.LAUNCH_SEED in types
    assert WalletEntryType.COMMISSION in types
    commission = next(
        entry for entry in ledger if entry["entry_type"] == WalletEntryType.COMMISSION
    )
    assert commission["amount"] == -3.2
    assert commission["balance_after"] == 36.8
    assert commission["ride_id"] == selected["id"]
    assert commission["created_at"] is not None
