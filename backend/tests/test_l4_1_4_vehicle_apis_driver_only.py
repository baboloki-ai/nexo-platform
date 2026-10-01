"""
L4.1.4: vehicle management APIs are restricted to drivers.

Every /vehicles endpoint must reject non-driver users with HTTP 403
before any ownership or CRUD work. Drivers keep existing CRUD and
ownership isolation. Vehicle verification_status is not changed by
this protection.
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.constants.verification import VerificationStatus
from app.models.user import User
from app.models.vehicle import Vehicle
from app.utils.jwt import create_access_token
from app.utils.security import hash_password


VEHICLE_CREATE_PAYLOAD = {
    "make": "Toyota",
    "model": "Corolla",
    "year": 2022,
    "color": "White",
    "registration_number": "B414NEX",
    "vehicle_type": "sedan",
}

VEHICLE_UPDATE_PAYLOAD = {
    "make": "Honda",
    "model": "Civic",
    "year": 2023,
    "color": "Black",
    "registration_number": "B414UPD",
    "vehicle_type": "sedan",
}

FORBIDDEN_DETAIL = "Only drivers can access this resource."


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


def _create_other_driver(db_session: Session) -> User:
    user = User(
        full_name="Other L414 Driver",
        phone_number="+15550004141",
        email="other.l414.driver@test.nexo",
        password=hash_password("TestDriverL414!"),
        role="driver",
        verification_status=VerificationStatus.APPROVED,
        availability_status="offline",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _assert_forbidden(response) -> None:
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == FORBIDDEN_DETAIL


def test_passenger_cannot_create_vehicle(
    authenticated_passenger,
    db_session: Session,
):
    passenger = authenticated_passenger["user"]
    before = db_session.query(Vehicle).count()

    response = authenticated_passenger["client"].post(
        "/vehicles/",
        headers=authenticated_passenger["headers"],
        json=VEHICLE_CREATE_PAYLOAD,
    )
    _assert_forbidden(response)

    db_session.expire_all()
    assert db_session.query(Vehicle).count() == before
    assert (
        db_session.query(Vehicle)
        .filter(Vehicle.driver_id == passenger.id)
        .count()
        == 0
    )


def test_passenger_cannot_list_vehicles(authenticated_passenger):
    client = authenticated_passenger["client"]
    headers = authenticated_passenger["headers"]

    for path in ("/vehicles", "/vehicles/", "/vehicles/my"):
        _assert_forbidden(client.get(path, headers=headers))


def test_passenger_cannot_get_vehicle_by_id(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    driver = authenticated_driver["user"]
    vehicle = _add_vehicle(db_session, driver.id, plate="B414GET")

    response = authenticated_passenger["client"].get(
        f"/vehicles/{vehicle.id}",
        headers=authenticated_passenger["headers"],
    )
    _assert_forbidden(response)

    db_session.expire_all()
    row = db_session.get(Vehicle, vehicle.id)
    assert row is not None
    assert row.driver_id == driver.id
    assert row.verification_status == VerificationStatus.PENDING


def test_passenger_cannot_update_vehicle(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    driver = authenticated_driver["user"]
    vehicle = _add_vehicle(db_session, driver.id, plate="B414PUT")
    before = {
        "make": vehicle.make,
        "model": vehicle.model,
        "year": vehicle.year,
        "color": vehicle.color,
        "registration_number": vehicle.registration_number,
        "vehicle_type": vehicle.vehicle_type,
        "verification_status": vehicle.verification_status,
    }

    response = authenticated_passenger["client"].put(
        f"/vehicles/{vehicle.id}",
        headers=authenticated_passenger["headers"],
        json=VEHICLE_UPDATE_PAYLOAD,
    )
    _assert_forbidden(response)

    db_session.expire_all()
    row = db_session.get(Vehicle, vehicle.id)
    assert row is not None
    assert row.make == before["make"]
    assert row.model == before["model"]
    assert row.year == before["year"]
    assert row.color == before["color"]
    assert row.registration_number == before["registration_number"]
    assert row.vehicle_type == before["vehicle_type"]
    assert row.verification_status == before["verification_status"]


def test_passenger_cannot_delete_vehicle(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    driver = authenticated_driver["user"]
    vehicle = _add_vehicle(db_session, driver.id, plate="B414DEL")

    response = authenticated_passenger["client"].delete(
        f"/vehicles/{vehicle.id}",
        headers=authenticated_passenger["headers"],
    )
    _assert_forbidden(response)

    db_session.expire_all()
    assert db_session.get(Vehicle, vehicle.id) is not None


def test_passenger_cannot_manage_vehicle_tied_to_own_user_id(
    authenticated_passenger,
    db_session: Session,
):
    passenger = authenticated_passenger["user"]
    planted = _add_vehicle(
        db_session,
        passenger.id,
        plate="B414OWN",
        verification_status=VerificationStatus.APPROVED,
    )
    client = authenticated_passenger["client"]
    headers = authenticated_passenger["headers"]

    _assert_forbidden(client.get("/vehicles/my", headers=headers))
    _assert_forbidden(client.get(f"/vehicles/{planted.id}", headers=headers))
    _assert_forbidden(
        client.put(
            f"/vehicles/{planted.id}",
            headers=headers,
            json=VEHICLE_UPDATE_PAYLOAD,
        )
    )
    _assert_forbidden(client.delete(f"/vehicles/{planted.id}", headers=headers))

    db_session.expire_all()
    row = db_session.get(Vehicle, planted.id)
    assert row is not None
    assert row.driver_id == passenger.id
    assert row.verification_status == VerificationStatus.APPROVED
    assert row.registration_number == "B414OWN"


def test_driver_can_create_vehicle(authenticated_driver, db_session: Session):
    driver = authenticated_driver["user"]

    response = authenticated_driver["client"].post(
        "/vehicles/",
        headers=authenticated_driver["headers"],
        json=VEHICLE_CREATE_PAYLOAD,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["driver_id"] == driver.id
    assert payload["registration_number"] == VEHICLE_CREATE_PAYLOAD["registration_number"]
    assert payload["verification_status"] == VerificationStatus.PENDING

    db_session.expire_all()
    row = db_session.get(Vehicle, payload["id"])
    assert row is not None
    assert row.driver_id == driver.id
    assert row.verification_status == VerificationStatus.PENDING


def test_driver_can_list_own_vehicles(authenticated_driver, db_session: Session):
    driver = authenticated_driver["user"]
    created = _add_vehicle(db_session, driver.id, plate="B414LST")
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]

    for path in ("/vehicles", "/vehicles/", "/vehicles/my"):
        response = client.get(path, headers=headers)
        assert response.status_code == 200, response.text
        ids = {item["id"] for item in response.json()}
        assert created.id in ids
        assert all(item["driver_id"] == driver.id for item in response.json())


def test_driver_can_update_own_vehicle(authenticated_driver, db_session: Session):
    driver = authenticated_driver["user"]
    vehicle = _add_vehicle(
        db_session,
        driver.id,
        plate="B414OLD",
        verification_status=VerificationStatus.PENDING,
    )

    response = authenticated_driver["client"].put(
        f"/vehicles/{vehicle.id}",
        headers=authenticated_driver["headers"],
        json=VEHICLE_UPDATE_PAYLOAD,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["make"] == VEHICLE_UPDATE_PAYLOAD["make"]
    assert payload["registration_number"] == VEHICLE_UPDATE_PAYLOAD["registration_number"]
    assert payload["verification_status"] == VerificationStatus.PENDING

    db_session.expire_all()
    row = db_session.get(Vehicle, vehicle.id)
    assert row is not None
    assert row.driver_id == driver.id
    assert row.make == VEHICLE_UPDATE_PAYLOAD["make"]
    assert row.verification_status == VerificationStatus.PENDING


def test_driver_can_delete_own_vehicle(authenticated_driver, db_session: Session):
    driver = authenticated_driver["user"]
    vehicle = _add_vehicle(db_session, driver.id, plate="B414RM")

    response = authenticated_driver["client"].delete(
        f"/vehicles/{vehicle.id}",
        headers=authenticated_driver["headers"],
    )
    assert response.status_code == 200, response.text
    assert response.json()["message"] == "Vehicle deleted successfully"

    db_session.expire_all()
    assert db_session.get(Vehicle, vehicle.id) is None


def test_driver_cannot_access_another_drivers_vehicle(
    authenticated_driver,
    db_session: Session,
):
    other = _create_other_driver(db_session)
    other_vehicle = _add_vehicle(
        db_session,
        other.id,
        plate="B414OTH",
        verification_status=VerificationStatus.APPROVED,
    )
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]

    get_response = client.get(f"/vehicles/{other_vehicle.id}", headers=headers)
    assert get_response.status_code == 404
    assert get_response.json()["detail"] == "Vehicle not found"

    put_response = client.put(
        f"/vehicles/{other_vehicle.id}",
        headers=headers,
        json=VEHICLE_UPDATE_PAYLOAD,
    )
    assert put_response.status_code == 404

    delete_response = client.delete(
        f"/vehicles/{other_vehicle.id}",
        headers=headers,
    )
    assert delete_response.status_code == 404

    list_response = client.get("/vehicles/my", headers=headers)
    assert list_response.status_code == 200
    assert all(item["id"] != other_vehicle.id for item in list_response.json())

    db_session.expire_all()
    row = db_session.get(Vehicle, other_vehicle.id)
    assert row is not None
    assert row.driver_id == other.id
    assert row.verification_status == VerificationStatus.APPROVED
    assert row.registration_number == "B414OTH"


def test_unauthenticated_vehicle_requests_rejected(client: TestClient):
    paths = (
        ("GET", "/vehicles"),
        ("GET", "/vehicles/"),
        ("GET", "/vehicles/my"),
        ("GET", "/vehicles/1"),
        ("POST", "/vehicles/"),
        ("PUT", "/vehicles/1"),
        ("DELETE", "/vehicles/1"),
    )
    for method, path in paths:
        response = client.request(method, path, json=VEHICLE_CREATE_PAYLOAD)
        assert response.status_code == 401, f"{method} {path}: {response.text}"
        assert response.json()["detail"] == "Not authenticated"


def test_vehicle_verification_status_unchanged_by_role_protection(
    authenticated_driver,
    authenticated_passenger,
    db_session: Session,
):
    driver = authenticated_driver["user"]
    approved = _add_vehicle(
        db_session,
        driver.id,
        plate="B414APR",
        verification_status=VerificationStatus.APPROVED,
    )
    pending = _add_vehicle(
        db_session,
        driver.id,
        plate="B414PND",
        verification_status=VerificationStatus.PENDING,
    )

    _assert_forbidden(
        authenticated_passenger["client"].put(
            f"/vehicles/{approved.id}",
            headers=authenticated_passenger["headers"],
            json=VEHICLE_UPDATE_PAYLOAD,
        )
    )
    _assert_forbidden(
        authenticated_passenger["client"].delete(
            f"/vehicles/{pending.id}",
            headers=authenticated_passenger["headers"],
        )
    )

    created = authenticated_driver["client"].post(
        "/vehicles/",
        headers=authenticated_driver["headers"],
        json={
            **VEHICLE_CREATE_PAYLOAD,
            "registration_number": "B414NEW",
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["verification_status"] == VerificationStatus.PENDING

    updated = authenticated_driver["client"].put(
        f"/vehicles/{pending.id}",
        headers=authenticated_driver["headers"],
        json={
            **VEHICLE_UPDATE_PAYLOAD,
            "registration_number": "B414PN2",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["verification_status"] == VerificationStatus.PENDING

    db_session.expire_all()
    assert (
        db_session.get(Vehicle, approved.id).verification_status
        == VerificationStatus.APPROVED
    )
    assert (
        db_session.get(Vehicle, pending.id).verification_status
        == VerificationStatus.PENDING
    )
    assert (
        db_session.get(Vehicle, created.json()["id"]).verification_status
        == VerificationStatus.PENDING
    )
