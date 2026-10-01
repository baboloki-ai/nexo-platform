"""
Phase 3.6: legacy /trips surface hardening.

1. GET /trips/{ride_id} requires auth and ownership
   (owning passenger or assigned driver).
2. POST /trips/{ride_id}/accept emits ride_accepted
   after a successful CAS claim (parity with primary accept).
"""
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.passenger import Passenger
from app.models.ride_request import RideRequest
from app.models.user import User
from app.utils.jwt import create_access_token
from app.utils.security import hash_password

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


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(
        data={
            "sub": str(user.id),
            "email": user.email,
            "role": user.role,
        }
    )
    return {"Authorization": f"Bearer {token}"}


def _prepare_driver_online(
    driver_client: TestClient,
    driver_headers: dict[str, str],
) -> None:
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


@pytest.fixture
def second_driver_user(db_session: Session) -> User:
    user = User(
        full_name="Trips Test Driver B",
        phone_number="+15550003604",
        email="trips.driver.b@test.nexo",
        password=hash_password("TestDriverBTrips123!"),
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
        full_name="Trips Test Passenger B",
        phone_number="+15550003605",
        email="trips.passenger.b@test.nexo",
        password=hash_password("TestPassengerBTrips123!"),
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
        first_name="Trips",
        last_name="PassengerB",
        phone="+15550003606",
        email="trips.passenger.b.profile@test.nexo",
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
# PART 1 — GET /trips/{ride_id} auth + ownership
# ---------------------------------------------------------------------------


def test_get_trip_unauthenticated_returns_401(
    client: TestClient,
    authenticated_passenger,
    authenticated_driver,
    driver_user,
):
    ride = _create_assigned_ride(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        driver_user.id,
    )

    response = client.get(f"/trips/{ride['id']}")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_get_trip_other_passenger_returns_403(
    authenticated_passenger,
    authenticated_driver,
    authenticated_second_passenger,
    driver_user,
):
    ride = _create_assigned_ride(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        driver_user.id,
    )

    response = authenticated_second_passenger["client"].get(
        f"/trips/{ride['id']}",
        headers=authenticated_second_passenger["headers"],
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not authorized to view this trip."


def test_get_trip_unassigned_driver_returns_403(
    authenticated_passenger,
    authenticated_driver,
    authenticated_second_driver,
    driver_user,
):
    ride = _create_assigned_ride(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        driver_user.id,
    )

    response = authenticated_second_driver["client"].get(
        f"/trips/{ride['id']}",
        headers=authenticated_second_driver["headers"],
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Not authorized to view this trip."


def test_get_trip_owning_passenger_returns_200(
    authenticated_passenger,
    authenticated_driver,
    driver_user,
):
    ride = _create_assigned_ride(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        driver_user.id,
    )

    response = authenticated_passenger["client"].get(
        f"/trips/{ride['id']}",
        headers=authenticated_passenger["headers"],
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == ride["id"]
    assert payload["passenger_id"] == ride["passenger_id"]
    assert payload["status"] == "accepted"


def test_get_trip_assigned_driver_returns_200(
    authenticated_passenger,
    authenticated_driver,
    driver_user,
):
    ride = _create_assigned_ride(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        driver_user.id,
    )

    response = authenticated_driver["client"].get(
        f"/trips/{ride['id']}",
        headers=authenticated_driver["headers"],
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == ride["id"]
    assert payload["accepted_driver_id"] == driver_user.id


def test_get_trip_missing_returns_404(authenticated_passenger):
    response = authenticated_passenger["client"].get(
        "/trips/999999",
        headers=authenticated_passenger["headers"],
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Trip not found."


# ---------------------------------------------------------------------------
# PART 2 — Legacy accept notification parity
# ---------------------------------------------------------------------------


def test_legacy_trips_accept_records_marketplace_response(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
    driver_user,
):
    """POST /trips/{id}/accept records an open marketplace response."""
    from tests.ride_flow import create_pending_ride, prepare_driver_online
    from app.models.driver_response import DriverResponse

    prepare_driver_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    ride = create_pending_ride(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
    )
    ride_id = ride["id"]

    with patch(
        "app.services.marketplace_service.NotificationService.notify_driver_response_received",
    ) as notify_mock:
        accept_response = authenticated_driver["client"].post(
            f"/trips/{ride_id}/accept",
            headers=authenticated_driver["headers"],
        )

    assert accept_response.status_code == 200
    assert accept_response.json()["status"] == "pending"
    assert accept_response.json()["accepted_driver_id"] is None
    assert notify_mock.called

    db_session.expire_all()
    ride_row = db_session.get(RideRequest, ride_id)
    assert ride_row is not None
    assert ride_row.status == "pending"
    assert (
        db_session.query(DriverResponse)
        .filter(DriverResponse.ride_id == ride_id)
        .count()
        == 1
    )


def test_legacy_trips_accept_failed_cas_does_not_notify(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
    driver_user,
):
    """Failed legacy accept on a closed request must not create a response."""
    from tests.ride_flow import create_pending_ride, prepare_driver_online

    prepare_driver_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    ride = create_pending_ride(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
    )
    ride_id = ride["id"]
    cancel = authenticated_passenger["client"].put(
        f"/rides/{ride_id}/cancel",
        headers=authenticated_passenger["headers"],
    )
    assert cancel.status_code == 200

    with patch(
        "app.services.marketplace_service.NotificationService.notify_driver_response_received",
    ) as notify_mock:
        accept_response = authenticated_driver["client"].post(
            f"/trips/{ride_id}/accept",
            headers=authenticated_driver["headers"],
        )

    assert accept_response.status_code in (400, 404)
    notify_mock.assert_not_called()
    notify_mock.assert_not_called()
