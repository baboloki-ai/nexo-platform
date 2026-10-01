"""
Phase 1.8: stable API input validation and post-lifecycle edge-case tests.

Covers only behaviors currently enforced by production validation / state checks.
Does not duplicate Phases 1.1–1.7 coverage.
"""
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

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

VEHICLE_CREATE_PAYLOAD = {
    "make": "Toyota",
    "model": "Corolla",
    "year": 2022,
    "color": "White",
    "registration_number": "B123ABC",
    "vehicle_type": "sedan",
}

PASSENGER_CREATE_PAYLOAD = {
    "first_name": "Test",
    "last_name": "Passenger",
    "phone": "70000001",
    "email": "passenger@example.com",
}

NONEXISTENT_RIDE_ID = 999_999

REQUIRED_RIDE_FIELDS = (
    "pickup_location",
    "pickup_latitude",
    "pickup_longitude",
    "destination",
    "destination_latitude",
    "destination_longitude",
    "proposed_fare",
)


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(
        data={
            "sub": str(user.id),
            "email": user.email,
            "role": user.role,
        }
    )
    return {"Authorization": f"Bearer {token}"}


def _field_in_validation_loc(response, field: str) -> bool:
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    return any(field in err.get("loc", ()) for err in detail)


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


def _complete_assigned_ride(
    driver_client: TestClient,
    driver_headers: dict[str, str],
    ride_id: int,
) -> None:
    assert driver_client.put(
        f"/rides/{ride_id}/arrive",
        headers=driver_headers,
    ).status_code == 200
    assert driver_client.put(
        f"/rides/{ride_id}/driver-arrived",
        headers=driver_headers,
    ).status_code == 200
    assert driver_client.put(
        f"/rides/{ride_id}/start",
        headers=driver_headers,
    ).status_code == 200
    assert driver_client.put(
        f"/rides/{ride_id}/complete",
        headers=driver_headers,
    ).status_code == 200


def _advance_to_in_progress(
    driver_client: TestClient,
    driver_headers: dict[str, str],
    ride_id: int,
) -> None:
    assert driver_client.put(
        f"/rides/{ride_id}/arrive",
        headers=driver_headers,
    ).status_code == 200
    assert driver_client.put(
        f"/rides/{ride_id}/driver-arrived",
        headers=driver_headers,
    ).status_code == 200
    assert driver_client.put(
        f"/rides/{ride_id}/start",
        headers=driver_headers,
    ).status_code == 200


@pytest.fixture
def authenticated_user_without_passenger_profile(
    client: TestClient,
    db_session: Session,
) -> dict[str, Any]:
    """Authenticated user with no Passenger row (distinct from passenger_user fixture)."""
    user = User(
        full_name="Phase18 No Passenger Profile",
        phone_number="+15550001801",
        email="phase18.no.passenger@test.nexo",
        password=hash_password("TestNoPassengerPhase18!"),
        role="passenger",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return {
        "client": client,
        "user": user,
        "headers": _auth_headers(user),
    }


# ---------------------------------------------------------------------------
# 1. RIDE CREATE VALIDATION — missing required fields
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("missing_field", REQUIRED_RIDE_FIELDS)
def test_create_ride_missing_required_field_returns_422(
    authenticated_passenger,
    missing_field: str,
):
    client = authenticated_passenger["client"]
    headers = authenticated_passenger["headers"]

    payload = {k: v for k, v in RIDE_CREATE_PAYLOAD.items() if k != missing_field}
    response = client.post("/rides/", headers=headers, json=payload)

    assert response.status_code == 422
    assert _field_in_validation_loc(response, missing_field)


# ---------------------------------------------------------------------------
# 2. RIDE NULL / INVALID COORDINATES
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field",
    (
        "pickup_latitude",
        "pickup_longitude",
        "destination_latitude",
        "destination_longitude",
    ),
)
def test_create_ride_null_coordinate_returns_422(
    authenticated_passenger,
    field: str,
):
    client = authenticated_passenger["client"]
    headers = authenticated_passenger["headers"]

    payload = {**RIDE_CREATE_PAYLOAD, field: None}
    response = client.post("/rides/", headers=headers, json=payload)

    assert response.status_code == 422
    assert _field_in_validation_loc(response, field)


@pytest.mark.parametrize(
    "invalid_value",
    ("not-a-number", ""),
)
def test_create_ride_invalid_coordinate_type_returns_422(
    authenticated_passenger,
    invalid_value,
):
    client = authenticated_passenger["client"]
    headers = authenticated_passenger["headers"]

    payload = {**RIDE_CREATE_PAYLOAD, "pickup_latitude": invalid_value}
    response = client.post("/rides/", headers=headers, json=payload)

    assert response.status_code == 422
    assert _field_in_validation_loc(response, "pickup_latitude")


# ---------------------------------------------------------------------------
# 3. INVALID RIDE ID FORMAT
# ---------------------------------------------------------------------------


def test_invalid_ride_id_format_returns_422(authenticated_driver, db_session):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]

    ride_count_before = db_session.query(RideRequest).count()

    response = client.put(
        "/rides/not-an-integer/accept",
        headers=headers,
    )
    assert response.status_code == 422

    db_session.expire_all()
    assert db_session.query(RideRequest).count() == ride_count_before


# ---------------------------------------------------------------------------
# 4. NON-EXISTENT RIDE IDS (lifecycle endpoints not covered in Phase 1.3)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("endpoint", "detail"),
    (
        ("arrive", "Ride not found."),
        ("start", "Ride not found."),
        ("complete", "Ride not found."),
        ("reject", "Ride not found or cannot be rejected."),
    ),
)
def test_nonexistent_ride_lifecycle_endpoints(
    authenticated_driver,
    endpoint: str,
    detail: str,
):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]

    response = client.put(
        f"/rides/{NONEXISTENT_RIDE_ID}/{endpoint}",
        headers=headers,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == detail


# ---------------------------------------------------------------------------
# 5. POST-LIFECYCLE STATE EDGE CASES
# ---------------------------------------------------------------------------


def test_post_lifecycle_actions_on_completed_ride(
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
    _complete_assigned_ride(driver_client, driver_headers, ride_id)

    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride is not None
    assert ride.status == "completed"
    driver_row = db_session.get(User, driver.id)
    assert driver_row.availability_status == "available"

    # A. Complete an already completed ride
    complete_again = driver_client.put(
        f"/rides/{ride_id}/complete",
        headers=driver_headers,
    )
    assert complete_again.status_code == 400
    assert complete_again.json()["detail"] == "Ride is not currently in progress."

    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride.status == "completed"
    driver_row = db_session.get(User, driver.id)
    assert driver_row.availability_status == "available"

    # B. Arrive after completion
    arrive_after = driver_client.put(
        f"/rides/{ride_id}/arrive",
        headers=driver_headers,
    )
    assert arrive_after.status_code == 400
    assert arrive_after.json()["detail"] == "Ride is not in the accepted state."

    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride.status == "completed"

    # C. Start after completion
    start_after = driver_client.put(
        f"/rides/{ride_id}/start",
        headers=driver_headers,
    )
    assert start_after.status_code == 400
    assert start_after.json()["detail"] == "Ride is not ready to start."

    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride.status == "completed"


# ---------------------------------------------------------------------------
# 6. START TWICE
# ---------------------------------------------------------------------------


def test_start_ride_twice_returns_400(
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
    _advance_to_in_progress(driver_client, driver_headers, ride_id)

    db_session.expire_all()
    assert db_session.get(RideRequest, ride_id).status == "in_progress"

    second_start = driver_client.put(
        f"/rides/{ride_id}/start",
        headers=driver_headers,
    )
    assert second_start.status_code == 400
    assert second_start.json()["detail"] == "Ride is not ready to start."

    db_session.expire_all()
    assert db_session.get(RideRequest, ride_id).status == "in_progress"


# ---------------------------------------------------------------------------
# 7. REJECT ALREADY REJECTED RIDE
# ---------------------------------------------------------------------------


def test_reject_already_rejected_ride_returns_404(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    from tests.ride_flow import (
        create_pending_ride,
        driver_accept_passenger_offer,
        prepare_driver_online,
    )

    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]

    prepare_driver_online(driver_client, driver_headers)
    ride_payload = create_pending_ride(passenger_client, passenger_headers)
    ride_id = ride_payload["id"]
    driver_accept_passenger_offer(driver_client, driver_headers, ride_id)

    first_reject = driver_client.put(
        f"/rides/{ride_id}/reject",
        headers=driver_headers,
    )
    assert first_reject.status_code == 200

    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride is not None
    assert ride.status == "pending"
    assert ride.accepted_driver_id is None
    assert ride.accepted_driver_id != driver.id

    second_reject = driver_client.put(
        f"/rides/{ride_id}/reject",
        headers=driver_headers,
    )
    assert second_reject.status_code == 404
    assert second_reject.json()["detail"] == "Ride not found or cannot be rejected."


# ---------------------------------------------------------------------------
# 8. DRIVER LOCATION NULL / INVALID TYPE
# ---------------------------------------------------------------------------


def test_driver_location_null_latitude_returns_422(authenticated_driver):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]

    response = client.put(
        "/drivers/location",
        headers=headers,
        json={"latitude": None, "longitude": 25.91},
    )
    assert response.status_code == 422
    assert _field_in_validation_loc(response, "latitude")


def test_driver_location_invalid_coordinate_type_returns_422(authenticated_driver):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]

    response = client.put(
        "/drivers/location",
        headers=headers,
        json={"latitude": "not-a-number", "longitude": 25.91},
    )
    assert response.status_code == 422
    assert _field_in_validation_loc(response, "latitude")


# ---------------------------------------------------------------------------
# 9. VEHICLE INVALID YEAR / NULL
# ---------------------------------------------------------------------------


def test_vehicle_year_float_returns_422(authenticated_driver):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]

    payload = {**VEHICLE_CREATE_PAYLOAD, "year": 2022.5}
    response = client.post("/vehicles/", headers=headers, json=payload)
    assert response.status_code == 422
    assert _field_in_validation_loc(response, "year")


def test_vehicle_year_null_returns_422(authenticated_driver):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]

    payload = {**VEHICLE_CREATE_PAYLOAD, "year": None}
    response = client.post("/vehicles/", headers=headers, json=payload)
    assert response.status_code == 422
    assert _field_in_validation_loc(response, "year")


# ---------------------------------------------------------------------------
# 10. PASSENGER NULL REQUIRED FIELD
# ---------------------------------------------------------------------------


def test_create_passenger_null_required_field_returns_422(
    authenticated_user_without_passenger_profile,
):
    client = authenticated_user_without_passenger_profile["client"]
    headers = authenticated_user_without_passenger_profile["headers"]

    payload = {**PASSENGER_CREATE_PAYLOAD, "phone": None}
    response = client.post("/passengers/", headers=headers, json=payload)
    assert response.status_code == 422
    assert _field_in_validation_loc(response, "phone")


# ---------------------------------------------------------------------------
# 11. CREATE RIDE AFTER PREVIOUS RIDE COMPLETES
# ---------------------------------------------------------------------------


def test_create_ride_after_previous_completes(
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
    first_ride_id = first["id"]
    _complete_assigned_ride(driver_client, driver_headers, first_ride_id)

    db_session.expire_all()
    first_ride = db_session.get(RideRequest, first_ride_id)
    assert first_ride is not None
    assert first_ride.status == "completed"

    # Driver is available again after completion; prepare for second assignment.
    _prepare_driver_online(driver_client, driver_headers)

    second_response = passenger_client.post(
        "/rides/",
        headers=passenger_headers,
        json=RIDE_CREATE_PAYLOAD,
    )
    assert second_response.status_code == 200
    second = second_response.json()
    second_ride_id = second["id"]

    assert second_ride_id != first_ride_id
    assert second["passenger_id"] == passenger.id

    db_session.expire_all()
    first_ride = db_session.get(RideRequest, first_ride_id)
    assert first_ride is not None
    assert first_ride.status == "completed"

    second_ride = db_session.get(RideRequest, second_ride_id)
    assert second_ride is not None
    assert second_ride.id != first_ride_id
    assert second_ride.passenger_id == passenger.id
    assert (
        db_session.query(RideRequest)
        .filter(RideRequest.passenger_id == passenger.id)
        .count()
        == 2
    )
