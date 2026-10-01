"""
Phase 1.3: ride lifecycle failure and validation tests.

Covers only behaviors currently enforced by production ride services.
"""
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

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

NONEXISTENT_RIDE_ID = 999_999


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
    from tests.ride_flow import (
        create_pending_ride,
        driver_accept_passenger_offer,
        prepare_driver_online,
    )

    prepare_driver_online(driver_client, driver_headers)
    payload = create_pending_ride(passenger_client, passenger_headers)
    driver_accept_passenger_offer(driver_client, driver_headers, payload["id"])
    return payload


def _select_driver(
    passenger_client: TestClient,
    passenger_headers: dict[str, str],
    ride_id: int,
) -> dict[str, Any]:
    from tests.ride_flow import list_responses, passenger_select_response

    responses = list_responses(passenger_client, passenger_headers, ride_id)
    return passenger_select_response(
        passenger_client,
        passenger_headers,
        ride_id,
        responses[0]["id"],
    )


@pytest.fixture
def second_driver_user(db_session: Session) -> User:
    """Second driver; offline so dispatch never assigns them."""
    user = User(
        full_name="Test Driver B User",
        phone_number="+15550000004",
        email="driver.b.user@test.nexo",
        password=hash_password("TestDriverB123!"),
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
def user_without_passenger_profile(db_session: Session) -> User:
    user = User(
        full_name="User Without Passenger Profile",
        phone_number="+15550000010",
        email="no.passenger.profile@test.nexo",
        password=hash_password("TestNoPassenger123!"),
        role="passenger",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def authenticated_user_without_passenger_profile(
    client: TestClient,
    user_without_passenger_profile: User,
) -> dict[str, Any]:
    return {
        "client": client,
        "user": user_without_passenger_profile,
        "headers": _auth_headers(user_without_passenger_profile),
    }


def test_passenger_cannot_create_second_active_ride(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    passenger = authenticated_passenger["passenger"]
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]

    first = _create_assigned_ride(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        expected_driver_id=driver.id,
    )

    second_response = passenger_client.post(
        "/rides/",
        headers=passenger_headers,
        json=RIDE_CREATE_PAYLOAD,
    )
    assert second_response.status_code == 400
    assert second_response.json()["detail"] == "You already have an active ride."

    db_session.expire_all()
    ride_count = (
        db_session.query(RideRequest)
        .filter(RideRequest.passenger_id == passenger.id)
        .count()
    )
    assert ride_count == 1
    assert db_session.get(RideRequest, first["id"]) is not None


def test_user_without_passenger_profile_cannot_create_ride(
    authenticated_user_without_passenger_profile,
    db_session,
):
    client = authenticated_user_without_passenger_profile["client"]
    headers = authenticated_user_without_passenger_profile["headers"]

    response = client.post(
        "/rides/",
        headers=headers,
        json=RIDE_CREATE_PAYLOAD,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Passenger profile not found."

    db_session.expire_all()
    assert db_session.query(RideRequest).count() == 0


def test_create_ride_with_no_suitable_driver_stays_pending(
    authenticated_passenger,
    db_session,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    passenger = authenticated_passenger["passenger"]

    response = passenger_client.post(
        "/rides/",
        headers=passenger_headers,
        json=RIDE_CREATE_PAYLOAD,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["accepted_driver_id"] is None

    db_session.expire_all()
    ride = db_session.get(RideRequest, payload["id"])
    assert ride is not None
    assert ride.status == "pending"
    assert ride.accepted_driver_id is None
    assert ride.passenger_id == passenger.id
    assert (
        db_session.query(DriverResponse)
        .filter(DriverResponse.ride_id == ride.id)
        .count()
        == 0
    )


def test_wrong_driver_cannot_accept_assigned_ride(
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

    driver_b_client = authenticated_second_driver["client"]
    driver_b_headers = authenticated_second_driver["headers"]

    response = driver_b_client.put(
        f"/rides/{ride_id}/respond",
        headers=driver_b_headers,
        json={"response_type": "accept_passenger_offer"},
    )
    assert response.status_code in (400, 403)

    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride is not None
    assert ride.status == "pending"
    assert ride.accepted_driver_id is None


def test_driver_cannot_accept_ride_no_longer_pending_acceptance(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]

    from tests.ride_flow import list_responses, passenger_select_response

    ride_payload = _create_assigned_ride(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        expected_driver_id=driver.id,
    )
    ride_id = ride_payload["id"]
    responses = list_responses(passenger_client, passenger_headers, ride_id)
    passenger_select_response(
        passenger_client,
        passenger_headers,
        ride_id,
        responses[0]["id"],
    )

    second_accept = driver_client.put(
        f"/rides/{ride_id}/accept",
        headers=driver_headers,
    )
    assert second_accept.status_code == 400

    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride is not None
    assert ride.status == "accepted"


def test_driver_cannot_arrive_before_accepting(
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

    response = driver_client.put(
        f"/rides/{ride_id}/arrive",
        headers=driver_headers,
    )
    # Marketplace: responding is not assignment. Arrive requires the passenger
    # to have selected this driver (accepted_driver_id).
    assert response.status_code == 403
    assert response.json()["detail"] == "You are not assigned to this ride."

    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride is not None
    assert ride.status == "pending"


def test_driver_cannot_mark_arrived_before_driver_arriving(
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

    _select_driver(passenger_client, passenger_headers, ride_id)

    response = driver_client.put(
        f"/rides/{ride_id}/driver-arrived",
        headers=driver_headers,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Ride is not in the driver-arriving state."

    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride is not None
    assert ride.status == "accepted"


def test_driver_cannot_start_before_ride_ready(
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

    _select_driver(passenger_client, passenger_headers, ride_id)

    response = driver_client.put(
        f"/rides/{ride_id}/start",
        headers=driver_headers,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Ride is not ready to start."

    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride is not None
    assert ride.status == "accepted"


def test_driver_cannot_complete_before_in_progress(
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

    _select_driver(passenger_client, passenger_headers, ride_id)
    assert driver_client.put(
        f"/rides/{ride_id}/arrive",
        headers=driver_headers,
    ).status_code == 200
    assert driver_client.put(
        f"/rides/{ride_id}/driver-arrived",
        headers=driver_headers,
    ).status_code == 200

    db_session.expire_all()
    driver_before = db_session.get(User, driver.id)
    availability_before = driver_before.availability_status

    response = driver_client.put(
        f"/rides/{ride_id}/complete",
        headers=driver_headers,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Ride is not currently in progress."

    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride is not None
    assert ride.status == "driver_arrived"

    driver_after = db_session.get(User, driver.id)
    assert driver_after.availability_status == availability_before


def test_passenger_cannot_accept_ride(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    passenger = authenticated_passenger["passenger"]
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
    ride_before = db_session.get(RideRequest, ride_id)
    status_before = ride_before.status
    assigned_before = ride_before.accepted_driver_id
    response_count_before = (
        db_session.query(DriverResponse)
        .filter(DriverResponse.ride_id == ride_id)
        .count()
    )
    driver_before = db_session.get(User, driver.id)
    availability_before = driver_before.availability_status

    response = passenger_client.put(
        f"/rides/{ride_id}/accept",
        headers=passenger_headers,
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Only drivers can accept rides."

    db_session.expire_all()
    ride_after = db_session.get(RideRequest, ride_id)
    assert ride_after.status == status_before
    assert ride_after.accepted_driver_id == assigned_before
    assert ride_after.passenger_id == passenger.id
    assert (
        db_session.query(DriverResponse)
        .filter(DriverResponse.ride_id == ride_id)
        .count()
        == response_count_before
    )
    driver_after = db_session.get(User, driver.id)
    assert driver_after.availability_status == availability_before


def test_wrong_driver_cannot_arrive_on_accepted_ride(
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

    _select_driver(passenger_client, passenger_headers, ride_id)

    db_session.expire_all()
    ride_before = db_session.get(RideRequest, ride_id)
    status_before = ride_before.status
    assigned_before = ride_before.accepted_driver_id
    driver_before = db_session.get(User, driver_a.id)
    availability_before = driver_before.availability_status

    driver_b_client = authenticated_second_driver["client"]
    driver_b_headers = authenticated_second_driver["headers"]

    response = driver_b_client.put(
        f"/rides/{ride_id}/arrive",
        headers=driver_b_headers,
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "You are not assigned to this ride."

    db_session.expire_all()
    ride_after = db_session.get(RideRequest, ride_id)
    assert ride_after.status == status_before
    assert ride_after.status == "accepted"
    assert ride_after.accepted_driver_id == assigned_before
    assert ride_after.accepted_driver_id == driver_a.id
    driver_after = db_session.get(User, driver_a.id)
    assert driver_after.availability_status == availability_before


def test_accept_nonexistent_ride_returns_not_found(
    authenticated_driver,
):
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]

    response = driver_client.put(
        f"/rides/{NONEXISTENT_RIDE_ID}/accept",
        headers=driver_headers,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Ride not found."
