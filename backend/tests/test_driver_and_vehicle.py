"""
Phase 1.7: driver offline/location and vehicle CRUD ownership tests.

Covers only behaviors currently enforced by driver and vehicle endpoints.
"""
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.vehicle import Vehicle
from app.utils.jwt import create_access_token
from app.utils.security import hash_password

VEHICLE_CREATE_PAYLOAD = {
    "make": "Toyota",
    "model": "Corolla",
    "year": 2022,
    "color": "White",
    "registration_number": "B123ABC",
    "vehicle_type": "sedan",
}

VEHICLE_UPDATE_PAYLOAD = {
    "make": "Honda",
    "model": "Civic",
    "year": 2023,
    "color": "Black",
    "registration_number": "B456DEF",
    "vehicle_type": "sedan",
}

DRIVER_LOCATION_PAYLOAD = {
    "latitude": -24.65,
    "longitude": 25.91,
}


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(
        data={
            "sub": str(user.id),
            "email": user.email,
            "role": user.role,
        }
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def second_driver_user(db_session: Session) -> User:
    user = User(
        full_name="Phase17 Driver B",
        phone_number="+15550001702",
        email="phase17.driver.b@test.nexo",
        password=hash_password("TestDriverBPhase17!"),
        role="driver",
        verification_status="approved",
        availability_status="offline",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def second_driver_vehicle(
    db_session: Session,
    second_driver_user: User,
) -> Vehicle:
    vehicle = Vehicle(
        driver_id=second_driver_user.id,
        make="Ford",
        model="Focus",
        year=2021,
        color="Blue",
        registration_number="B999XYZ",
        vehicle_type="sedan",
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)
    return vehicle


def _create_vehicle_for_driver(
    client: TestClient,
    headers: dict[str, str],
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = payload if payload is not None else VEHICLE_CREATE_PAYLOAD
    response = client.post("/vehicles/", headers=headers, json=body)
    assert response.status_code == 200
    return response.json()


# ---------------------------------------------------------------------------
# DRIVER TESTS
# ---------------------------------------------------------------------------


def test_driver_goes_offline(authenticated_driver, db_session):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]

    # Ensure online first if needed (fixture starts as available).
    if driver.availability_status != "available":
        online_response = client.put("/drivers/go-online", headers=headers)
        assert online_response.status_code == 200

    response = client.put("/drivers/go-offline", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "offline"
    assert payload["message"] == "Driver is now offline."

    db_session.expire_all()
    row = db_session.get(User, driver.id)
    assert row is not None
    assert row.availability_status == "offline"
    assert row.last_seen is not None


def test_driver_location_update(authenticated_driver, db_session):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]

    response = client.put(
        "/drivers/location",
        headers=headers,
        json=DRIVER_LOCATION_PAYLOAD,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["latitude"] == DRIVER_LOCATION_PAYLOAD["latitude"]
    assert payload["longitude"] == DRIVER_LOCATION_PAYLOAD["longitude"]

    db_session.expire_all()
    row = db_session.get(User, driver.id)
    assert row is not None
    assert row.current_latitude == DRIVER_LOCATION_PAYLOAD["latitude"]
    assert row.current_longitude == DRIVER_LOCATION_PAYLOAD["longitude"]
    assert row.last_seen is not None


def test_missing_driver_location_fields(authenticated_driver):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]

    response = client.put(
        "/drivers/location",
        headers=headers,
        json={"latitude": -24.65},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# VEHICLE TESTS
# ---------------------------------------------------------------------------


def test_driver_creates_vehicle(authenticated_driver, db_session):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]

    response = client.post(
        "/vehicles/",
        headers=headers,
        json=VEHICLE_CREATE_PAYLOAD,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["driver_id"] == driver.id
    assert payload["make"] == VEHICLE_CREATE_PAYLOAD["make"]
    assert payload["model"] == VEHICLE_CREATE_PAYLOAD["model"]
    assert payload["year"] == VEHICLE_CREATE_PAYLOAD["year"]
    assert payload["color"] == VEHICLE_CREATE_PAYLOAD["color"]
    assert (
        payload["registration_number"]
        == VEHICLE_CREATE_PAYLOAD["registration_number"]
    )
    assert payload["vehicle_type"] == VEHICLE_CREATE_PAYLOAD["vehicle_type"]

    db_session.expire_all()
    row = db_session.get(Vehicle, payload["id"])
    assert row is not None
    assert row.driver_id == driver.id
    assert row.make == VEHICLE_CREATE_PAYLOAD["make"]
    assert row.model == VEHICLE_CREATE_PAYLOAD["model"]
    assert row.year == VEHICLE_CREATE_PAYLOAD["year"]
    assert row.color == VEHICLE_CREATE_PAYLOAD["color"]
    assert (
        row.registration_number
        == VEHICLE_CREATE_PAYLOAD["registration_number"]
    )
    assert row.vehicle_type == VEHICLE_CREATE_PAYLOAD["vehicle_type"]


def test_driver_retrieves_own_vehicles(authenticated_driver):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]

    created = _create_vehicle_for_driver(client, headers)

    response = client.get("/vehicles/my", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert any(item["id"] == created["id"] for item in payload)


def test_driver_retrieves_own_vehicle_by_id(authenticated_driver):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]

    created = _create_vehicle_for_driver(client, headers)

    response = client.get(
        f"/vehicles/{created['id']}",
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == created["id"]
    assert payload["driver_id"] == driver.id


def test_driver_updates_own_vehicle(authenticated_driver, db_session):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]

    created = _create_vehicle_for_driver(client, headers)

    response = client.put(
        f"/vehicles/{created['id']}",
        headers=headers,
        json=VEHICLE_UPDATE_PAYLOAD,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["make"] == VEHICLE_UPDATE_PAYLOAD["make"]
    assert payload["model"] == VEHICLE_UPDATE_PAYLOAD["model"]
    assert payload["year"] == VEHICLE_UPDATE_PAYLOAD["year"]
    assert payload["color"] == VEHICLE_UPDATE_PAYLOAD["color"]
    assert (
        payload["registration_number"]
        == VEHICLE_UPDATE_PAYLOAD["registration_number"]
    )
    assert payload["vehicle_type"] == VEHICLE_UPDATE_PAYLOAD["vehicle_type"]

    db_session.expire_all()
    row = db_session.get(Vehicle, created["id"])
    assert row is not None
    assert row.make == VEHICLE_UPDATE_PAYLOAD["make"]
    assert row.model == VEHICLE_UPDATE_PAYLOAD["model"]
    assert row.year == VEHICLE_UPDATE_PAYLOAD["year"]
    assert row.color == VEHICLE_UPDATE_PAYLOAD["color"]
    assert (
        row.registration_number
        == VEHICLE_UPDATE_PAYLOAD["registration_number"]
    )
    assert row.vehicle_type == VEHICLE_UPDATE_PAYLOAD["vehicle_type"]


def test_driver_deletes_own_vehicle(authenticated_driver, db_session):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]

    created = _create_vehicle_for_driver(client, headers)
    vehicle_id = created["id"]

    response = client.delete(
        f"/vehicles/{vehicle_id}",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Vehicle deleted successfully"

    db_session.expire_all()
    assert db_session.get(Vehicle, vehicle_id) is None


def test_driver_cannot_access_another_drivers_vehicle(
    authenticated_driver,
    second_driver_vehicle,
):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]

    response = client.get(
        f"/vehicles/{second_driver_vehicle.id}",
        headers=headers,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Vehicle not found"


def test_driver_cannot_update_another_drivers_vehicle(
    authenticated_driver,
    second_driver_vehicle,
    db_session,
):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]
    other = second_driver_vehicle
    before = {
        "make": other.make,
        "model": other.model,
        "year": other.year,
        "color": other.color,
        "registration_number": other.registration_number,
        "vehicle_type": other.vehicle_type,
    }

    response = client.put(
        f"/vehicles/{other.id}",
        headers=headers,
        json=VEHICLE_UPDATE_PAYLOAD,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Vehicle not found"

    db_session.expire_all()
    row = db_session.get(Vehicle, other.id)
    assert row is not None
    assert row.make == before["make"]
    assert row.model == before["model"]
    assert row.year == before["year"]
    assert row.color == before["color"]
    assert row.registration_number == before["registration_number"]
    assert row.vehicle_type == before["vehicle_type"]


def test_driver_cannot_delete_another_drivers_vehicle(
    authenticated_driver,
    second_driver_vehicle,
    db_session,
):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]
    other_id = second_driver_vehicle.id

    response = client.delete(
        f"/vehicles/{other_id}",
        headers=headers,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Vehicle not found"

    db_session.expire_all()
    assert db_session.get(Vehicle, other_id) is not None


def test_unauthenticated_vehicle_access(client: TestClient):
    response = client.get("/vehicles/my")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_missing_required_vehicle_fields(authenticated_driver):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]

    incomplete = {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2022,
        "color": "White",
        # registration_number missing
        "vehicle_type": "sedan",
    }
    response = client.post(
        "/vehicles/",
        headers=headers,
        json=incomplete,
    )
    assert response.status_code == 422
