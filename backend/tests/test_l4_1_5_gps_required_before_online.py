"""
L4.1.5: current GPS required before going online.

An approved driver with an approved vehicle and sufficient wallet may go
online only when current_latitude and current_longitude are both present.
Missing either coordinate is insufficient GPS. Go-online must not mutate
wallet, vehicle verification, or ride state on rejection.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.constants.ride_status import RideStatus
from app.constants.verification import VerificationStatus
from app.models.driver_wallet import DriverWallet
from app.models.ride_request import RideRequest
from app.models.user import User
from app.models.vehicle import Vehicle
from app.models.wallet_ledger_entry import WalletLedgerEntry

from tests.ride_flow import RIDE_CREATE_PAYLOAD
from tests.test_dispatch import (
    NEAR_LAT,
    NEAR_LON,
    _create_driver as _create_dispatch_driver,
)
from tests.test_l4_1_1_active_ride_restoration import select_active_assigned_ride

GO_ONLINE_PATH = "/drivers/go-online"
GPS_REQUIRED = "Current GPS location is required to go online."
NO_APPROVED_VEHICLE = "Driver does not have an approved vehicle."
VALID_LAT = -26.2041
VALID_LON = 28.0473
INTERNAL_SECRET = "l415-test-secret"


def _driver_vehicles(db_session: Session, driver_id: int) -> list[Vehicle]:
    return (
        db_session.query(Vehicle)
        .filter(Vehicle.driver_id == driver_id)
        .order_by(Vehicle.id.asc())
        .all()
    )


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


def _set_offline(db_session: Session, driver: User) -> None:
    db_session.expire_all()
    row = db_session.get(User, driver.id)
    assert row is not None
    row.availability_status = "offline"
    db_session.commit()


def _set_gps(
    db_session: Session,
    driver: User,
    latitude: float | None,
    longitude: float | None,
) -> None:
    db_session.expire_all()
    row = db_session.get(User, driver.id)
    assert row is not None
    row.current_latitude = latitude
    row.current_longitude = longitude
    db_session.commit()


def _add_vehicle(
    db_session: Session,
    driver_id: int,
    *,
    plate: str,
    verification_status: str,
) -> Vehicle:
    vehicle = Vehicle(
        driver_id=driver_id,
        make="Toyota",
        model="Corolla",
        year=2021,
        color="White",
        registration_number=plate,
        vehicle_type="sedan",
        verification_status=verification_status,
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)
    return vehicle


def _seed_assigned_ride(
    db_session: Session,
    *,
    passenger_id: int,
    driver_id: int,
    status: str = RideStatus.ACCEPTED,
) -> RideRequest:
    ride = RideRequest(
        passenger_id=passenger_id,
        pickup_location=RIDE_CREATE_PAYLOAD["pickup_location"],
        pickup_latitude=RIDE_CREATE_PAYLOAD["pickup_latitude"],
        pickup_longitude=RIDE_CREATE_PAYLOAD["pickup_longitude"],
        destination=RIDE_CREATE_PAYLOAD["destination"],
        destination_latitude=RIDE_CREATE_PAYLOAD["destination_latitude"],
        destination_longitude=RIDE_CREATE_PAYLOAD["destination_longitude"],
        proposed_fare=RIDE_CREATE_PAYLOAD["proposed_fare"],
        status=status,
        accepted_driver_id=driver_id,
    )
    db_session.add(ride)
    db_session.commit()
    db_session.refresh(ride)
    return ride


def _go_online(client: TestClient, headers: dict[str, str]):
    return client.put(GO_ONLINE_PATH, headers=headers)


def _snapshot(db_session: Session, *, driver_id: int, ride_id: int | None):
    db_session.expire_all()
    driver = db_session.get(User, driver_id)
    wallet = (
        db_session.query(DriverWallet)
        .filter(DriverWallet.driver_id == driver_id)
        .one()
    )
    ledger_count = (
        db_session.query(WalletLedgerEntry)
        .filter(WalletLedgerEntry.driver_id == driver_id)
        .count()
    )
    vehicles = _driver_vehicles(db_session, driver_id)
    ride = db_session.get(RideRequest, ride_id) if ride_id is not None else None
    return {
        "availability": driver.availability_status,
        "driver_verification": driver.verification_status,
        "latitude": driver.current_latitude,
        "longitude": driver.current_longitude,
        "wallet": Decimal(str(wallet.available_balance)),
        "ledger_count": ledger_count,
        "vehicle_statuses": {
            vehicle.id: vehicle.verification_status for vehicle in vehicles
        },
        "ride_status": ride.status if ride is not None else None,
        "accepted_driver_id": ride.accepted_driver_id if ride is not None else None,
    }


def _assert_snapshot_unchanged(
    db_session: Session,
    *,
    driver_id: int,
    ride_id: int | None,
    before: dict,
) -> None:
    after = _snapshot(db_session, driver_id=driver_id, ride_id=ride_id)
    assert after == before


def test_missing_latitude_and_longitude_rejects_go_online(
    authenticated_driver,
    db_session: Session,
):
    driver = authenticated_driver["user"]
    _set_offline(db_session, driver)
    _set_gps(db_session, driver, None, None)

    response = _go_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    assert response.status_code == 400
    assert response.json()["detail"] == GPS_REQUIRED

    db_session.expire_all()
    row = db_session.get(User, driver.id)
    assert row.availability_status == "offline"
    assert row.current_latitude is None
    assert row.current_longitude is None


def test_missing_latitude_with_valid_longitude_rejects_go_online(
    authenticated_driver,
    db_session: Session,
):
    driver = authenticated_driver["user"]
    _set_offline(db_session, driver)
    _set_gps(db_session, driver, None, VALID_LON)

    response = _go_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    assert response.status_code == 400
    assert response.json()["detail"] == GPS_REQUIRED

    db_session.expire_all()
    row = db_session.get(User, driver.id)
    assert row.availability_status == "offline"
    assert row.current_latitude is None
    assert row.current_longitude == VALID_LON


def test_valid_latitude_with_missing_longitude_rejects_go_online(
    authenticated_driver,
    db_session: Session,
):
    driver = authenticated_driver["user"]
    _set_offline(db_session, driver)
    _set_gps(db_session, driver, VALID_LAT, None)

    response = _go_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    assert response.status_code == 400
    assert response.json()["detail"] == GPS_REQUIRED

    db_session.expire_all()
    row = db_session.get(User, driver.id)
    assert row.availability_status == "offline"
    assert row.current_latitude == VALID_LAT
    assert row.current_longitude is None


def test_valid_latitude_and_longitude_allows_go_online(
    authenticated_driver,
    db_session: Session,
):
    driver = authenticated_driver["user"]
    _set_offline(db_session, driver)
    _set_gps(db_session, driver, VALID_LAT, VALID_LON)
    vehicles = _driver_vehicles(db_session, driver.id)
    assert vehicles[0].verification_status == VerificationStatus.APPROVED

    response = _go_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "available"
    assert response.json()["message"] == "Driver is now online."

    db_session.expire_all()
    row = db_session.get(User, driver.id)
    assert row.availability_status == "available"
    assert row.current_latitude == VALID_LAT
    assert row.current_longitude == VALID_LON


def test_driver_remains_offline_after_gps_rejection(
    authenticated_driver,
    db_session: Session,
):
    driver = authenticated_driver["user"]
    _set_offline(db_session, driver)
    _set_gps(db_session, driver, None, None)

    first = _go_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    assert first.status_code == 400
    db_session.expire_all()
    assert db_session.get(User, driver.id).availability_status == "offline"

    second = _go_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    assert second.status_code == 400
    db_session.expire_all()
    assert db_session.get(User, driver.id).availability_status == "offline"


def test_unapproved_driver_protection_still_blocks_go_online(
    authenticated_driver,
    db_session: Session,
):
    driver = authenticated_driver["user"]
    _set_offline(db_session, driver)
    _set_gps(db_session, driver, VALID_LAT, VALID_LON)
    db_session.expire_all()
    row = db_session.get(User, driver.id)
    row.verification_status = VerificationStatus.PENDING
    db_session.commit()

    response = _go_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Driver account is not approved."
    db_session.expire_all()
    row = db_session.get(User, driver.id)
    assert row.availability_status == "offline"
    assert row.verification_status == VerificationStatus.PENDING


def test_approved_vehicle_requirement_still_blocks_go_online(
    authenticated_driver,
    db_session: Session,
):
    driver = authenticated_driver["user"]
    _set_offline(db_session, driver)
    _set_gps(db_session, driver, VALID_LAT, VALID_LON)
    vehicles = _driver_vehicles(db_session, driver.id)
    db_session.expire_all()
    vehicle = db_session.get(Vehicle, vehicles[0].id)
    vehicle.verification_status = VerificationStatus.PENDING
    db_session.commit()

    response = _go_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    assert response.status_code == 403
    assert response.json()["detail"] == NO_APPROVED_VEHICLE
    db_session.expire_all()
    assert db_session.get(User, driver.id).availability_status == "offline"
    assert (
        db_session.get(Vehicle, vehicles[0].id).verification_status
        == VerificationStatus.PENDING
    )


def test_zero_wallet_still_blocks_go_online(
    authenticated_driver,
    db_session: Session,
):
    driver = authenticated_driver["user"]
    _set_offline(db_session, driver)
    _set_gps(db_session, driver, VALID_LAT, VALID_LON)
    _set_wallet(db_session, driver.id, Decimal("0.00"))

    response = _go_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    assert response.status_code == 400
    assert "P0" in response.json()["detail"]
    db_session.expire_all()
    assert db_session.get(User, driver.id).availability_status == "offline"
    wallet = (
        db_session.query(DriverWallet)
        .filter(DriverWallet.driver_id == driver.id)
        .one()
    )
    assert Decimal(str(wallet.available_balance)) == Decimal("0.00")


def test_active_ride_protection_still_blocks_go_online(
    authenticated_driver,
    authenticated_passenger,
    db_session: Session,
):
    driver = authenticated_driver["user"]
    _set_offline(db_session, driver)
    _set_gps(db_session, driver, VALID_LAT, VALID_LON)
    ride = _seed_assigned_ride(
        db_session,
        passenger_id=authenticated_passenger["passenger"].id,
        driver_id=driver.id,
        status=RideStatus.ACCEPTED,
    )

    response = _go_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Driver has an active ride."
    db_session.expire_all()
    assert db_session.get(User, driver.id).availability_status == "offline"
    ride_row = db_session.get(RideRequest, ride.id)
    assert ride_row.status == RideStatus.ACCEPTED
    assert ride_row.accepted_driver_id == driver.id


def test_l4_1_1_active_ride_restoration_still_works(
    authenticated_driver,
    authenticated_passenger,
    db_session: Session,
):
    driver = authenticated_driver["user"]
    ride = _seed_assigned_ride(
        db_session,
        passenger_id=authenticated_passenger["passenger"].id,
        driver_id=driver.id,
        status=RideStatus.ACCEPTED,
    )

    response = authenticated_driver["client"].get(
        "/drivers/rides",
        headers=authenticated_driver["headers"],
    )
    assert response.status_code == 200, response.text
    restored = select_active_assigned_ride(response.json(), driver.id, None)
    assert restored is not None
    assert restored["id"] == ride.id
    assert restored["status"] == RideStatus.ACCEPTED
    assert restored["accepted_driver_id"] == driver.id


def test_l4_1_2_vehicle_verification_still_works(
    authenticated_driver,
    db_session: Session,
    monkeypatch,
):
    monkeypatch.setattr("app.config.INTERNAL_VERIFY_SECRET", INTERNAL_SECRET)
    driver = authenticated_driver["user"]
    vehicle = _add_vehicle(
        db_session,
        driver.id,
        plate="B415VER",
        verification_status=VerificationStatus.PENDING,
    )

    response = authenticated_driver["client"].post(
        f"/internal/vehicles/{vehicle.id}/verification",
        headers={"X-NEXO-INTERNAL-SECRET": INTERNAL_SECRET},
        json={"status": VerificationStatus.APPROVED},
    )
    assert response.status_code == 200, response.text
    assert response.json()["verification_status"] == VerificationStatus.APPROVED
    db_session.expire_all()
    assert (
        db_session.get(Vehicle, vehicle.id).verification_status
        == VerificationStatus.APPROVED
    )


def test_l4_1_4_passenger_vehicle_api_restriction_still_works(
    authenticated_passenger,
    db_session: Session,
):
    before = db_session.query(Vehicle).count()
    response = authenticated_passenger["client"].post(
        "/vehicles/",
        headers=authenticated_passenger["headers"],
        json={
            "make": "Toyota",
            "model": "Corolla",
            "year": 2022,
            "color": "White",
            "registration_number": "B415PAS",
            "vehicle_type": "sedan",
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Only drivers can access this resource."
    db_session.expire_all()
    assert db_session.query(Vehicle).count() == before


def test_gps_rejection_does_not_modify_wallet_vehicle_or_ride(
    authenticated_driver,
    authenticated_passenger,
    db_session: Session,
):
    driver = authenticated_driver["user"]
    _set_offline(db_session, driver)
    _set_gps(db_session, driver, None, None)
    ride = RideRequest(
        passenger_id=authenticated_passenger["passenger"].id,
        pickup_location=RIDE_CREATE_PAYLOAD["pickup_location"],
        pickup_latitude=RIDE_CREATE_PAYLOAD["pickup_latitude"],
        pickup_longitude=RIDE_CREATE_PAYLOAD["pickup_longitude"],
        destination=RIDE_CREATE_PAYLOAD["destination"],
        destination_latitude=RIDE_CREATE_PAYLOAD["destination_latitude"],
        destination_longitude=RIDE_CREATE_PAYLOAD["destination_longitude"],
        proposed_fare=RIDE_CREATE_PAYLOAD["proposed_fare"],
        status=RideStatus.PENDING,
    )
    db_session.add(ride)
    db_session.commit()
    db_session.refresh(ride)

    before = _snapshot(db_session, driver_id=driver.id, ride_id=ride.id)
    assert before["availability"] == "offline"
    assert before["latitude"] is None
    assert before["longitude"] is None

    response = _go_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    assert response.status_code == 400
    assert response.json()["detail"] == GPS_REQUIRED
    _assert_snapshot_unchanged(
        db_session,
        driver_id=driver.id,
        ride_id=ride.id,
        before=before,
    )


def test_marketplace_dispatch_gps_eligibility_unchanged(
    authenticated_passenger,
    db_session: Session,
):
    with_gps = _create_dispatch_driver(
        db_session,
        full_name="L415 GPS Driver",
        phone_number="+15550004150",
        email="l415.gps.driver.dispatch@test.nexo",
        current_latitude=NEAR_LAT,
        current_longitude=NEAR_LON,
    )
    without_gps = _create_dispatch_driver(
        db_session,
        full_name="L415 No GPS Driver",
        phone_number="+15550004151",
        email="l415.nogps.driver.dispatch@test.nexo",
    )
    offline_no_gps = _create_dispatch_driver(
        db_session,
        full_name="L415 Offline No GPS",
        phone_number="+15550004152",
        email="l415.offline.nogps.dispatch@test.nexo",
        availability_status="offline",
    )

    with patch(
        "app.services.notification_service.NotificationService.notify_marketplace_request_created"
    ) as broadcast:
        payload = authenticated_passenger["client"].post(
            "/rides/",
            headers=authenticated_passenger["headers"],
            json=RIDE_CREATE_PAYLOAD,
        ).json()

    notified = {call.kwargs["driver_id"] for call in broadcast.call_args_list}
    assert payload["status"] == "pending"
    assert payload["accepted_driver_id"] is None
    assert with_gps.id in notified
    assert without_gps.id not in notified
    assert offline_no_gps.id not in notified
    db_session.expire_all()
    assert db_session.get(User, without_gps.id).availability_status == "available"
    assert db_session.get(User, without_gps.id).current_latitude is None
    assert db_session.get(User, without_gps.id).current_longitude is None
