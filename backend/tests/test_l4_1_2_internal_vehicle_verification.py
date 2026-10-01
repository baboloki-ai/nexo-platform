"""
L4.1.2: internal vehicle verification.

POST /internal/vehicles/{vehicle_id}/verification is the only write path
for vehicle.verification_status from ops. It uses the same internal secret
as driver verification and must not mutate driver, ride, or wallet state.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.constants.ride_status import RideStatus
from app.constants.verification import VerificationStatus
from app.models.driver_wallet import DriverWallet
from app.models.passenger import Passenger
from app.models.ride_request import RideRequest
from app.models.user import User
from app.models.vehicle import Vehicle
from app.models.wallet_ledger_entry import WalletLedgerEntry

from tests.ride_flow import RIDE_CREATE_PAYLOAD

INTERNAL_SECRET = "l412-test-secret"
VEHICLE_PATH = "/internal/vehicles/{vehicle_id}/verification"


def _internal_headers(secret: str) -> dict[str, str]:
    return {"X-NEXO-INTERNAL-SECRET": secret}


def _add_vehicle(
    db_session: Session,
    driver_id: int,
    *,
    plate: str = "B412NEX",
    verification_status: str = VerificationStatus.PENDING,
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


def _verify_vehicle(
    client: TestClient,
    vehicle_id: int,
    status: str,
    secret: str | None,
):
    headers = _internal_headers(secret) if secret is not None else {}
    return client.post(
        VEHICLE_PATH.format(vehicle_id=vehicle_id),
        headers=headers,
        json={"status": status},
    )


def test_internal_vehicle_verification_approves_with_secret(
    authenticated_driver,
    db_session: Session,
    monkeypatch,
):
    monkeypatch.setattr("app.config.INTERNAL_VERIFY_SECRET", INTERNAL_SECRET)
    client = authenticated_driver["client"]
    driver = authenticated_driver["user"]
    vehicle = _add_vehicle(db_session, driver.id)
    assert vehicle.verification_status == VerificationStatus.PENDING

    response = _verify_vehicle(
        client,
        vehicle.id,
        VerificationStatus.APPROVED,
        INTERNAL_SECRET,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == vehicle.id
    assert body["driver_id"] == driver.id
    assert body["verification_status"] == VerificationStatus.APPROVED

    db_session.expire_all()
    row = db_session.get(Vehicle, vehicle.id)
    assert row is not None
    assert row.verification_status == VerificationStatus.APPROVED


def test_internal_vehicle_verification_rejects_with_secret(
    authenticated_driver,
    db_session: Session,
    monkeypatch,
):
    monkeypatch.setattr("app.config.INTERNAL_VERIFY_SECRET", INTERNAL_SECRET)
    client = authenticated_driver["client"]
    driver = authenticated_driver["user"]
    vehicle = _add_vehicle(db_session, driver.id)

    response = _verify_vehicle(
        client,
        vehicle.id,
        VerificationStatus.REJECTED,
        INTERNAL_SECRET,
    )
    assert response.status_code == 200, response.text
    assert response.json()["verification_status"] == VerificationStatus.REJECTED

    db_session.expire_all()
    assert (
        db_session.get(Vehicle, vehicle.id).verification_status
        == VerificationStatus.REJECTED
    )


def test_internal_vehicle_verification_missing_or_invalid_secret_rejected(
    authenticated_driver,
    db_session: Session,
    monkeypatch,
):
    monkeypatch.setattr("app.config.INTERNAL_VERIFY_SECRET", INTERNAL_SECRET)
    client = authenticated_driver["client"]
    driver = authenticated_driver["user"]
    vehicle = _add_vehicle(db_session, driver.id)

    missing = _verify_vehicle(
        client,
        vehicle.id,
        VerificationStatus.APPROVED,
        secret=None,
    )
    assert missing.status_code == 401

    bearer_only = client.post(
        VEHICLE_PATH.format(vehicle_id=vehicle.id),
        headers=authenticated_driver["headers"],
        json={"status": VerificationStatus.APPROVED},
    )
    assert bearer_only.status_code == 401

    invalid = _verify_vehicle(
        client,
        vehicle.id,
        VerificationStatus.APPROVED,
        secret="wrong-secret",
    )
    assert invalid.status_code == 401

    db_session.expire_all()
    assert (
        db_session.get(Vehicle, vehicle.id).verification_status
        == VerificationStatus.PENDING
    )


def test_internal_vehicle_verification_hidden_without_secret(
    authenticated_driver,
    db_session: Session,
    monkeypatch,
):
    monkeypatch.setattr("app.config.INTERNAL_VERIFY_SECRET", None)
    client = authenticated_driver["client"]
    driver = authenticated_driver["user"]
    vehicle = _add_vehicle(db_session, driver.id)

    response = _verify_vehicle(
        client,
        vehicle.id,
        VerificationStatus.APPROVED,
        secret=None,
    )
    assert response.status_code == 404

    with_header = _verify_vehicle(
        client,
        vehicle.id,
        VerificationStatus.APPROVED,
        secret="anything",
    )
    assert with_header.status_code == 404

    db_session.expire_all()
    assert (
        db_session.get(Vehicle, vehicle.id).verification_status
        == VerificationStatus.PENDING
    )


def test_internal_vehicle_verification_nonexistent_vehicle(
    authenticated_driver,
    monkeypatch,
):
    monkeypatch.setattr("app.config.INTERNAL_VERIFY_SECRET", INTERNAL_SECRET)
    response = _verify_vehicle(
        authenticated_driver["client"],
        999_999,
        VerificationStatus.APPROVED,
        INTERNAL_SECRET,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Vehicle not found."


def test_internal_vehicle_verification_does_not_mutate_unrelated_state(
    authenticated_driver,
    passenger_profile: Passenger,
    db_session: Session,
    monkeypatch,
):
    monkeypatch.setattr("app.config.INTERNAL_VERIFY_SECRET", INTERNAL_SECRET)
    client = authenticated_driver["client"]
    driver = authenticated_driver["user"]

    db_session.expire_all()
    driver_row = db_session.get(User, driver.id)
    driver_row.availability_status = "offline"
    db_session.commit()

    vehicle = _add_vehicle(db_session, driver.id)
    ride = _seed_assigned_ride(
        db_session,
        passenger_id=passenger_profile.id,
        driver_id=driver.id,
    )

    db_session.expire_all()
    before_driver = db_session.get(User, driver.id)
    before_wallet = (
        db_session.query(DriverWallet)
        .filter(DriverWallet.driver_id == driver.id)
        .one()
    )
    before_ledger_count = (
        db_session.query(WalletLedgerEntry)
        .filter(WalletLedgerEntry.driver_id == driver.id)
        .count()
    )
    before_ride = db_session.get(RideRequest, ride.id)
    snapshot = {
        "driver_verification": before_driver.verification_status,
        "availability": before_driver.availability_status,
        "latitude": before_driver.current_latitude,
        "longitude": before_driver.current_longitude,
        "wallet": Decimal(str(before_wallet.available_balance)),
        "ledger_count": before_ledger_count,
        "ride_status": before_ride.status,
        "accepted_driver_id": before_ride.accepted_driver_id,
    }
    assert snapshot["driver_verification"] == VerificationStatus.APPROVED
    assert snapshot["availability"] == "offline"

    response = _verify_vehicle(
        client,
        vehicle.id,
        VerificationStatus.APPROVED,
        INTERNAL_SECRET,
    )
    assert response.status_code == 200, response.text
    assert response.json()["verification_status"] == VerificationStatus.APPROVED

    db_session.expire_all()
    after_vehicle = db_session.get(Vehicle, vehicle.id)
    after_driver = db_session.get(User, driver.id)
    after_wallet = (
        db_session.query(DriverWallet)
        .filter(DriverWallet.driver_id == driver.id)
        .one()
    )
    after_ledger_count = (
        db_session.query(WalletLedgerEntry)
        .filter(WalletLedgerEntry.driver_id == driver.id)
        .count()
    )
    after_ride = db_session.get(RideRequest, ride.id)

    assert after_vehicle.verification_status == VerificationStatus.APPROVED
    assert after_driver.verification_status == snapshot["driver_verification"]
    assert after_driver.availability_status == snapshot["availability"]
    assert after_driver.current_latitude == snapshot["latitude"]
    assert after_driver.current_longitude == snapshot["longitude"]
    assert Decimal(str(after_wallet.available_balance)) == snapshot["wallet"]
    assert after_ledger_count == snapshot["ledger_count"]
    assert after_ride.status == snapshot["ride_status"]
    assert after_ride.accepted_driver_id == snapshot["accepted_driver_id"]


def test_internal_vehicle_verification_not_public_and_hidden_from_openapi(
    authenticated_driver,
    db_session: Session,
    client: TestClient,
):
    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    paths = spec.json().get("paths") or {}
    assert all(not path.startswith("/internal") for path in paths)
    assert "/internal/vehicles/{vehicle_id}/verification" not in paths
    assert "/vehicles/{vehicle_id}/verification" not in paths

    driver = authenticated_driver["user"]
    vehicle = _add_vehicle(db_session, driver.id)
    headers = authenticated_driver["headers"]
    public_paths = (
        f"/vehicles/{vehicle.id}/verification",
        "/vehicles/verification",
        f"/drivers/vehicles/{vehicle.id}/verification",
        f"/drivers/{driver.id}/vehicles/{vehicle.id}/verification",
    )
    for path in public_paths:
        response = authenticated_driver["client"].post(
            path,
            headers=headers,
            json={"status": VerificationStatus.APPROVED},
        )
        assert response.status_code in (404, 405), path

    db_session.expire_all()
    assert (
        db_session.get(Vehicle, vehicle.id).verification_status
        == VerificationStatus.PENDING
    )
