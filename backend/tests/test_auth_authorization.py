"""
Phase 1.6: authentication and authorization tests.

Covers only behaviors currently enforced by production auth and role/assignment checks.
"""
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.passenger import Passenger
from app.models.driver_response import DriverResponse
from app.models.ride_request import RideRequest
from app.models.user import User
from app.utils.jwt import create_access_token
from app.utils.security import hash_password

# Near driver_user fixture GPS (-26.2041, 28.0473) so dispatch selects that driver.
RIDE_CREATE_PAYLOAD = {
    "pickup_location": "Sandton City Pickup",
    "pickup_latitude": -26.2041,
    "pickup_longitude": 28.0473,
    "destination": "OR Tambo Destination",
    "destination_latitude": -26.1330,
    "destination_longitude": 28.2420,
    "proposed_fare": 150.0,
}

DRIVER_LOCATION_PAYLOAD = {
    "latitude": -26.2041,
    "longitude": 28.0473,
}

PASSENGER_LOCATION_PAYLOAD = {
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


def _prepare_driver_online(driver_client: TestClient, driver_headers: dict[str, str]) -> None:
    go_online_response = driver_client.put(
        "/drivers/go-online",
        headers=driver_headers,
    )
    assert go_online_response.status_code == 200

    location_response = driver_client.put(
        "/drivers/location",
        headers=driver_headers,
        json=DRIVER_LOCATION_PAYLOAD,
    )
    assert location_response.status_code == 200


def _create_assigned_ride(
    passenger_client: TestClient,
    passenger_headers: dict[str, str],
    driver_client: TestClient,
    driver_headers: dict[str, str],
    expected_driver_id: int,
) -> dict[str, Any]:
    from tests.ride_flow import advance_to_accepted

    return advance_to_accepted(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        expected_driver_id,
    )


def _snapshot_ride(ride: RideRequest) -> dict[str, Any]:
    return {
        "status": ride.status,
        "accepted_driver_id": ride.accepted_driver_id,
        "passenger_id": ride.passenger_id,
    }


def _assert_ride_unchanged(
    db_session: Session,
    ride_id: int,
    before: dict[str, Any],
) -> None:
    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride is not None
    assert ride.status == before["status"]
    assert ride.accepted_driver_id == before["accepted_driver_id"]
    assert ride.passenger_id == before["passenger_id"]


@pytest.fixture
def second_driver_user(db_session: Session) -> User:
    """Second driver; offline so dispatch never assigns them."""
    user = User(
        full_name="Auth Test Driver B",
        phone_number="+15550000204",
        email="auth.driver.b@test.nexo",
        password=hash_password("TestDriverBAuth123!"),
        role="driver",
        verification_status="approved",
        availability_status="offline",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def authenticated_second_driver(
    client: TestClient,
    second_driver_user: User,
) -> dict[str, Any]:
    return {
        "client": client,
        "user": second_driver_user,
        "headers": _auth_headers(second_driver_user),
    }


@pytest.fixture
def second_passenger_user(db_session: Session) -> User:
    user = User(
        full_name="Auth Test Passenger B",
        phone_number="+15550000205",
        email="auth.passenger.b@test.nexo",
        password=hash_password("TestPassengerBAuth123!"),
        role="passenger",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def second_passenger_profile(
    db_session: Session,
    second_passenger_user: User,
) -> Passenger:
    profile = Passenger(
        user_id=second_passenger_user.id,
        first_name="Auth",
        last_name="PassengerB",
        phone="+15550000206",
        email="auth.passenger.b.profile@test.nexo",
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)
    return profile


@pytest.fixture
def authenticated_second_passenger(
    client: TestClient,
    second_passenger_user: User,
    second_passenger_profile: Passenger,
) -> dict[str, Any]:
    return {
        "client": client,
        "user": second_passenger_user,
        "passenger": second_passenger_profile,
        "headers": _auth_headers(second_passenger_user),
    }


# ---------------------------------------------------------------------------
# TESTS 1–3 — Authentication failures
# ---------------------------------------------------------------------------


def test_missing_authentication_returns_401(client: TestClient):
    response = client.get("/users/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_invalid_jwt_returns_401(client: TestClient):
    response = client.get(
        "/users/me",
        headers={"Authorization": "Bearer not-a-valid-jwt"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"


def test_non_bearer_authorization_scheme_returns_401(client: TestClient):
    response = client.get(
        "/users/me",
        headers={"Authorization": "Basic invalid-token"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


# ---------------------------------------------------------------------------
# TESTS 4–6 — Passenger cannot use driver-only endpoints
# ---------------------------------------------------------------------------


def test_passenger_cannot_go_online(authenticated_passenger):
    client = authenticated_passenger["client"]
    headers = authenticated_passenger["headers"]

    response = client.put("/drivers/go-online", headers=headers)
    assert response.status_code == 403
    assert response.json()["detail"] == "Only drivers can go online."


def test_passenger_cannot_go_offline(authenticated_passenger):
    client = authenticated_passenger["client"]
    headers = authenticated_passenger["headers"]

    response = client.put("/drivers/go-offline", headers=headers)
    assert response.status_code == 403
    assert response.json()["detail"] == "Only drivers can go offline."


def test_passenger_cannot_update_driver_location(
    authenticated_passenger,
    db_session,
    passenger_user,
):
    client = authenticated_passenger["client"]
    headers = authenticated_passenger["headers"]

    db_session.expire_all()
    before = db_session.get(User, passenger_user.id)
    snapshot = {
        "availability_status": before.availability_status,
        "current_latitude": before.current_latitude,
        "current_longitude": before.current_longitude,
        "role": before.role,
        "email": before.email,
    }

    response = client.put(
        "/drivers/location",
        headers=headers,
        json=PASSENGER_LOCATION_PAYLOAD,
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Only drivers can update their location."

    db_session.expire_all()
    after = db_session.get(User, passenger_user.id)
    assert after.availability_status == snapshot["availability_status"]
    assert after.current_latitude == snapshot["current_latitude"]
    assert after.current_longitude == snapshot["current_longitude"]
    assert after.role == snapshot["role"]
    assert after.email == snapshot["email"]


# ---------------------------------------------------------------------------
# TESTS 7–10 — Passenger cannot perform driver ride lifecycle actions
# ---------------------------------------------------------------------------


def test_passenger_cannot_arrive(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]

    ride_payload = _create_assigned_ride(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        expected_driver_id=driver.id,
    )
    ride_id = ride_payload["id"]

    db_session.expire_all()
    before = _snapshot_ride(db_session.get(RideRequest, ride_id))

    response = passenger_client.put(
        f"/rides/{ride_id}/arrive",
        headers=passenger_headers,
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Only drivers can update ride status."
    _assert_ride_unchanged(db_session, ride_id, before)


def test_passenger_cannot_mark_driver_arrived(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]

    ride_payload = _create_assigned_ride(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        expected_driver_id=driver.id,
    )
    ride_id = ride_payload["id"]

    db_session.expire_all()
    before = _snapshot_ride(db_session.get(RideRequest, ride_id))

    response = passenger_client.put(
        f"/rides/{ride_id}/driver-arrived",
        headers=passenger_headers,
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Only drivers can update ride status."
    _assert_ride_unchanged(db_session, ride_id, before)


def test_passenger_cannot_start_ride(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]

    ride_payload = _create_assigned_ride(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        expected_driver_id=driver.id,
    )
    ride_id = ride_payload["id"]

    db_session.expire_all()
    before = _snapshot_ride(db_session.get(RideRequest, ride_id))

    response = passenger_client.put(
        f"/rides/{ride_id}/start",
        headers=passenger_headers,
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Only drivers can start rides."
    _assert_ride_unchanged(db_session, ride_id, before)


def test_passenger_cannot_complete_ride(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]

    ride_payload = _create_assigned_ride(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        expected_driver_id=driver.id,
    )
    ride_id = ride_payload["id"]

    db_session.expire_all()
    before = _snapshot_ride(db_session.get(RideRequest, ride_id))

    response = passenger_client.put(
        f"/rides/{ride_id}/complete",
        headers=passenger_headers,
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Only drivers can complete rides."
    _assert_ride_unchanged(db_session, ride_id, before)


# ---------------------------------------------------------------------------
# TEST 11 — Passenger attempting reject (no role check; assignment miss → 404)
# ---------------------------------------------------------------------------


def test_passenger_reject_returns_not_found(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]

    ride_payload = _create_assigned_ride(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        expected_driver_id=driver.id,
    )
    ride_id = ride_payload["id"]

    db_session.expire_all()
    ride_before = _snapshot_ride(db_session.get(RideRequest, ride_id))
    offer_before = (
        db_session.query(DriverResponse)
        .filter(
            DriverResponse.ride_id == ride_id,
            DriverResponse.driver_id == driver.id,
        )
        .one()
    )
    offer_status_before = offer_before.status
    driver_before = db_session.get(User, driver.id)
    availability_before = driver_before.availability_status

    response = passenger_client.put(
        f"/rides/{ride_id}/reject",
        headers=passenger_headers,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Ride not found or cannot be rejected."

    _assert_ride_unchanged(db_session, ride_id, ride_before)

    db_session.expire_all()
    offer_after = (
        db_session.query(DriverResponse)
        .filter(
            DriverResponse.ride_id == ride_id,
            DriverResponse.driver_id == driver.id,
        )
        .one()
    )
    assert offer_after.status == offer_status_before

    driver_after = db_session.get(User, driver.id)
    assert driver_after.availability_status == availability_before


# ---------------------------------------------------------------------------
# TESTS 12–14 — Wrong driver assignment protection
# ---------------------------------------------------------------------------


def test_wrong_driver_cannot_mark_driver_arrived(
    authenticated_passenger,
    authenticated_driver,
    authenticated_second_driver,
    db_session,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    driver_a_client = authenticated_driver["client"]
    driver_a_headers = authenticated_driver["headers"]
    driver_a = authenticated_driver["user"]

    ride_payload = _create_assigned_ride(
        passenger_client,
        passenger_headers,
        driver_a_client,
        driver_a_headers,
        expected_driver_id=driver_a.id,
    )
    ride_id = ride_payload["id"]

    db_session.expire_all()
    ride_before = _snapshot_ride(db_session.get(RideRequest, ride_id))
    driver_before = db_session.get(User, driver_a.id)
    availability_before = driver_before.availability_status

    driver_b_client = authenticated_second_driver["client"]
    driver_b_headers = authenticated_second_driver["headers"]

    response = driver_b_client.put(
        f"/rides/{ride_id}/driver-arrived",
        headers=driver_b_headers,
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "You are not assigned to this ride."

    _assert_ride_unchanged(db_session, ride_id, ride_before)
    assert ride_before["accepted_driver_id"] == driver_a.id

    db_session.expire_all()
    driver_after = db_session.get(User, driver_a.id)
    assert driver_after.availability_status == availability_before


def test_wrong_driver_cannot_start_ride(
    authenticated_passenger,
    authenticated_driver,
    authenticated_second_driver,
    db_session,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    driver_a_client = authenticated_driver["client"]
    driver_a_headers = authenticated_driver["headers"]
    driver_a = authenticated_driver["user"]

    ride_payload = _create_assigned_ride(
        passenger_client,
        passenger_headers,
        driver_a_client,
        driver_a_headers,
        expected_driver_id=driver_a.id,
    )
    ride_id = ride_payload["id"]

    db_session.expire_all()
    ride_before = _snapshot_ride(db_session.get(RideRequest, ride_id))
    driver_before = db_session.get(User, driver_a.id)
    availability_before = driver_before.availability_status

    driver_b_client = authenticated_second_driver["client"]
    driver_b_headers = authenticated_second_driver["headers"]

    response = driver_b_client.put(
        f"/rides/{ride_id}/start",
        headers=driver_b_headers,
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "You are not assigned to this ride."

    _assert_ride_unchanged(db_session, ride_id, ride_before)
    assert ride_before["accepted_driver_id"] == driver_a.id

    db_session.expire_all()
    driver_after = db_session.get(User, driver_a.id)
    assert driver_after.availability_status == availability_before


def test_wrong_driver_cannot_complete_ride(
    authenticated_passenger,
    authenticated_driver,
    authenticated_second_driver,
    db_session,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    driver_a_client = authenticated_driver["client"]
    driver_a_headers = authenticated_driver["headers"]
    driver_a = authenticated_driver["user"]

    ride_payload = _create_assigned_ride(
        passenger_client,
        passenger_headers,
        driver_a_client,
        driver_a_headers,
        expected_driver_id=driver_a.id,
    )
    ride_id = ride_payload["id"]

    db_session.expire_all()
    ride_before = _snapshot_ride(db_session.get(RideRequest, ride_id))
    driver_before = db_session.get(User, driver_a.id)
    availability_before = driver_before.availability_status

    driver_b_client = authenticated_second_driver["client"]
    driver_b_headers = authenticated_second_driver["headers"]

    response = driver_b_client.put(
        f"/rides/{ride_id}/complete",
        headers=driver_b_headers,
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "You are not assigned to this ride."

    _assert_ride_unchanged(db_session, ride_id, ride_before)
    assert ride_before["accepted_driver_id"] == driver_a.id

    db_session.expire_all()
    driver_after = db_session.get(User, driver_a.id)
    assert driver_after.availability_status == availability_before


# ---------------------------------------------------------------------------
# Driver cannot create passenger-only rides
# ---------------------------------------------------------------------------


def test_driver_cannot_create_ride(
    authenticated_driver,
    authenticated_passenger,
    db_session,
):
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]

    ride_count_before = db_session.query(RideRequest).count()

    denied = driver_client.post(
        "/rides/",
        headers=driver_headers,
        json=RIDE_CREATE_PAYLOAD,
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Only passengers can create ride requests."

    db_session.expire_all()
    assert db_session.query(RideRequest).count() == ride_count_before

    allowed = passenger_client.post(
        "/rides/",
        headers=passenger_headers,
        json=RIDE_CREATE_PAYLOAD,
    )
    assert allowed.status_code == 200
    payload = allowed.json()
    assert payload["passenger_id"] == authenticated_passenger["passenger"].id
    assert payload["status"] == "pending"

    db_session.expire_all()
    assert db_session.query(RideRequest).count() == ride_count_before + 1



def test_driver_without_passenger_profile_cannot_get_ride_history(
    authenticated_driver,
    db_session,
):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]

    ride_count_before = db_session.query(RideRequest).count()

    response = client.get("/rides/my", headers=headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Passenger profile not found."

    db_session.expire_all()
    assert db_session.query(RideRequest).count() == ride_count_before
    assert db_session.query(Passenger).filter(Passenger.user_id == driver.id).count() == 0


# ---------------------------------------------------------------------------
# TESTS 16–18 — Positive authenticated access
# ---------------------------------------------------------------------------


def test_authenticated_user_can_access_me(authenticated_passenger, passenger_user):
    client = authenticated_passenger["client"]
    headers = authenticated_passenger["headers"]

    response = client.get("/users/me", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == passenger_user.id
    assert payload["email"] == passenger_user.email
    assert payload["full_name"] == passenger_user.full_name
    assert payload["phone_number"] == passenger_user.phone_number
    assert payload["role"] == passenger_user.role


def test_authenticated_driver_can_go_online(
    authenticated_driver,
    db_session,
    driver_user,
):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]

    response = client.put("/drivers/go-online", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "available"

    db_session.expire_all()
    driver = db_session.get(User, driver_user.id)
    assert driver.availability_status == "available"


def test_authenticated_passenger_can_access_own_ride_history(
    authenticated_passenger,
    authenticated_second_passenger,
    authenticated_driver,
    db_session,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    passenger = authenticated_passenger["passenger"]

    other_client = authenticated_second_passenger["client"]
    other_headers = authenticated_second_passenger["headers"]
    other_passenger = authenticated_second_passenger["passenger"]

    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]

    own_ride = _create_assigned_ride(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        expected_driver_id=driver.id,
    )

    # Second passenger creates an unassigned ride (driver already assigned/busy for first).
    # Force driver offline so this create stays pending and belongs only to passenger B.
    db_session.expire_all()
    driver_row = db_session.get(User, driver.id)
    driver_row.availability_status = "offline"
    db_session.commit()

    other_create = other_client.post(
        "/rides/",
        headers=other_headers,
        json=RIDE_CREATE_PAYLOAD,
    )
    assert other_create.status_code == 200
    other_ride = other_create.json()
    assert other_ride["passenger_id"] == other_passenger.id

    response = passenger_client.get("/rides/my", headers=passenger_headers)
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) >= 1
    assert all(item["passenger_id"] == passenger.id for item in payload)
    assert all(item["id"] != other_ride["id"] for item in payload)
    assert any(item["id"] == own_ride["id"] for item in payload)
