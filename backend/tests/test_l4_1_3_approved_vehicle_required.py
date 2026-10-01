"""
L4.1.3: approved vehicle required before going online.

An approved driver may go online only with at least one vehicle that
belongs to that driver and has verification_status == approved.
Go-online must not mutate vehicle verification, wallet, or ride state.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.constants.ride_status import RideStatus
from app.constants.verification import VerificationStatus
from app.models.driver_wallet import DriverWallet
from app.models.ride_request import RideRequest
from app.models.user import User
from app.models.vehicle import Vehicle
from app.utils.jwt import create_access_token
from app.utils.security import hash_password

from tests.ride_flow import RIDE_CREATE_PAYLOAD

GO_ONLINE_PATH = "/drivers/go-online"
NO_APPROVED_VEHICLE = "Driver does not have an approved vehicle."


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(
        data={
            "sub": str(user.id),
            "email": user.email,
            "role": user.role,
        }
    )
    return {"Authorization": f"Bearer {token}"}


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


def _driver_vehicles(db_session: Session, driver_id: int) -> list[Vehicle]:
    return (
        db_session.query(Vehicle)
        .filter(Vehicle.driver_id == driver_id)
        .order_by(Vehicle.id.asc())
        .all()
    )


def _clear_vehicles(db_session: Session, driver_id: int) -> None:
    for vehicle in _driver_vehicles(db_session, driver_id):
        db_session.delete(vehicle)
    db_session.commit()


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


def _create_other_driver(db_session: Session) -> User:
    user = User(
        full_name="Other L413 Driver",
        phone_number="+15550004130",
        email="other.l413.driver@test.nexo",
        password=hash_password("TestDriverL413!"),
        role="driver",
        verification_status=VerificationStatus.APPROVED,
        availability_status="offline",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _go_online(client: TestClient, headers: dict[str, str]):
    return client.put(GO_ONLINE_PATH, headers=headers)


def _assert_offline_and_vehicle_unchanged(
    db_session: Session,
    *,
    driver_id: int,
    vehicle_ids: list[int],
    expected_statuses: list[str],
) -> None:
    db_session.expire_all()
    driver = db_session.get(User, driver_id)
    assert driver is not None
    assert driver.availability_status == "offline"
    statuses = [
        db_session.get(Vehicle, vehicle_id).verification_status
        for vehicle_id in vehicle_ids
    ]
    assert statuses == expected_statuses


def test_approved_driver_with_no_vehicle_cannot_go_online(
    authenticated_driver,
    db_session: Session,
):
    driver = authenticated_driver["user"]
    _set_offline(db_session, driver)
    _clear_vehicles(db_session, driver.id)
    assert _driver_vehicles(db_session, driver.id) == []

    response = _go_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    assert response.status_code == 403
    assert response.json()["detail"] == NO_APPROVED_VEHICLE
    _assert_offline_and_vehicle_unchanged(
        db_session,
        driver_id=driver.id,
        vehicle_ids=[],
        expected_statuses=[],
    )


def test_approved_driver_with_pending_vehicle_cannot_go_online(
    authenticated_driver,
    db_session: Session,
):
    driver = authenticated_driver["user"]
    _set_offline(db_session, driver)
    _clear_vehicles(db_session, driver.id)
    vehicle = _add_vehicle(
        db_session,
        driver.id,
        plate="B413PND",
        verification_status=VerificationStatus.PENDING,
    )

    response = _go_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    assert response.status_code == 403
    assert response.json()["detail"] == NO_APPROVED_VEHICLE
    _assert_offline_and_vehicle_unchanged(
        db_session,
        driver_id=driver.id,
        vehicle_ids=[vehicle.id],
        expected_statuses=[VerificationStatus.PENDING],
    )


def test_approved_driver_with_rejected_vehicle_cannot_go_online(
    authenticated_driver,
    db_session: Session,
):
    driver = authenticated_driver["user"]
    _set_offline(db_session, driver)
    _clear_vehicles(db_session, driver.id)
    vehicle = _add_vehicle(
        db_session,
        driver.id,
        plate="B413REJ",
        verification_status=VerificationStatus.REJECTED,
    )

    response = _go_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    assert response.status_code == 403
    assert response.json()["detail"] == NO_APPROVED_VEHICLE
    _assert_offline_and_vehicle_unchanged(
        db_session,
        driver_id=driver.id,
        vehicle_ids=[vehicle.id],
        expected_statuses=[VerificationStatus.REJECTED],
    )


def test_approved_driver_with_suspended_vehicle_cannot_go_online(
    authenticated_driver,
    db_session: Session,
):
    driver = authenticated_driver["user"]
    _set_offline(db_session, driver)
    _clear_vehicles(db_session, driver.id)
    vehicle = _add_vehicle(
        db_session,
        driver.id,
        plate="B413SUS",
        verification_status=VerificationStatus.SUSPENDED,
    )

    response = _go_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    assert response.status_code == 403
    assert response.json()["detail"] == NO_APPROVED_VEHICLE
    _assert_offline_and_vehicle_unchanged(
        db_session,
        driver_id=driver.id,
        vehicle_ids=[vehicle.id],
        expected_statuses=[VerificationStatus.SUSPENDED],
    )


def test_approved_driver_with_approved_vehicle_can_go_online(
    authenticated_driver,
    db_session: Session,
):
    driver = authenticated_driver["user"]
    _set_offline(db_session, driver)
    vehicles = _driver_vehicles(db_session, driver.id)
    assert len(vehicles) == 1
    assert vehicles[0].driver_id == driver.id
    assert vehicles[0].verification_status == VerificationStatus.APPROVED

    before_wallet = (
        db_session.query(DriverWallet)
        .filter(DriverWallet.driver_id == driver.id)
        .one()
    )
    wallet_before = Decimal(str(before_wallet.available_balance))

    response = _go_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "available"
    assert response.json()["message"] == "Driver is now online."

    db_session.expire_all()
    row = db_session.get(User, driver.id)
    assert row is not None
    assert row.availability_status == "available"
    assert (
        db_session.get(Vehicle, vehicles[0].id).verification_status
        == VerificationStatus.APPROVED
    )
    after_wallet = (
        db_session.query(DriverWallet)
        .filter(DriverWallet.driver_id == driver.id)
        .one()
    )
    assert Decimal(str(after_wallet.available_balance)) == wallet_before


def test_other_drivers_vehicle_cannot_satisfy_go_online(
    authenticated_driver,
    db_session: Session,
):
    driver = authenticated_driver["user"]
    _set_offline(db_session, driver)
    _clear_vehicles(db_session, driver.id)

    other = _create_other_driver(db_session)
    other_vehicle = _add_vehicle(
        db_session,
        other.id,
        plate="B413OTH",
        verification_status=VerificationStatus.APPROVED,
    )

    response = _go_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    assert response.status_code == 403
    assert response.json()["detail"] == NO_APPROVED_VEHICLE

    db_session.expire_all()
    assert db_session.get(User, driver.id).availability_status == "offline"
    assert db_session.get(User, other.id).availability_status == "offline"
    assert (
        db_session.get(Vehicle, other_vehicle.id).driver_id == other.id
    )
    assert (
        db_session.get(Vehicle, other_vehicle.id).verification_status
        == VerificationStatus.APPROVED
    )
    assert _driver_vehicles(db_session, driver.id) == []


def test_unapproved_driver_still_rejected_with_approved_vehicle(
    authenticated_driver,
    db_session: Session,
):
    driver = authenticated_driver["user"]
    _set_offline(db_session, driver)
    vehicles = _driver_vehicles(db_session, driver.id)
    assert vehicles[0].verification_status == VerificationStatus.APPROVED

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
    _assert_offline_and_vehicle_unchanged(
        db_session,
        driver_id=driver.id,
        vehicle_ids=[vehicles[0].id],
        expected_statuses=[VerificationStatus.APPROVED],
    )
    db_session.expire_all()
    assert (
        db_session.get(User, driver.id).verification_status
        == VerificationStatus.PENDING
    )


def test_zero_wallet_still_blocks_go_online(
    authenticated_driver,
    db_session: Session,
):
    driver = authenticated_driver["user"]
    _set_offline(db_session, driver)
    vehicles = _driver_vehicles(db_session, driver.id)
    assert vehicles[0].verification_status == VerificationStatus.APPROVED
    _set_wallet(db_session, driver.id, Decimal("0.00"))

    response = _go_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    assert response.status_code == 400
    assert "P0" in response.json()["detail"]
    _assert_offline_and_vehicle_unchanged(
        db_session,
        driver_id=driver.id,
        vehicle_ids=[vehicles[0].id],
        expected_statuses=[VerificationStatus.APPROVED],
    )
    db_session.expire_all()
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
    vehicles = _driver_vehicles(db_session, driver.id)
    assert vehicles[0].verification_status == VerificationStatus.APPROVED
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
    _assert_offline_and_vehicle_unchanged(
        db_session,
        driver_id=driver.id,
        vehicle_ids=[vehicles[0].id],
        expected_statuses=[VerificationStatus.APPROVED],
    )
    db_session.expire_all()
    ride_row = db_session.get(RideRequest, ride.id)
    assert ride_row.status == RideStatus.ACCEPTED
    assert ride_row.accepted_driver_id == driver.id


def test_go_online_does_not_change_vehicle_verification_status(
    authenticated_driver,
    db_session: Session,
):
    driver = authenticated_driver["user"]
    _set_offline(db_session, driver)
    _clear_vehicles(db_session, driver.id)
    approved = _add_vehicle(
        db_session,
        driver.id,
        plate="B413OK1",
        verification_status=VerificationStatus.APPROVED,
    )
    pending = _add_vehicle(
        db_session,
        driver.id,
        plate="B413OK2",
        verification_status=VerificationStatus.PENDING,
    )

    response = _go_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    assert response.status_code == 200, response.text

    db_session.expire_all()
    assert db_session.get(User, driver.id).availability_status == "available"
    assert (
        db_session.get(Vehicle, approved.id).verification_status
        == VerificationStatus.APPROVED
    )
    assert (
        db_session.get(Vehicle, pending.id).verification_status
        == VerificationStatus.PENDING
    )
    assert db_session.get(Vehicle, approved.id).driver_id == driver.id
    assert db_session.get(Vehicle, pending.id).driver_id == driver.id
