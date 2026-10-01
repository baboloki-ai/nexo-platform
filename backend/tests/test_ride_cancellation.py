"""
Phase 2.8 / pilot: passenger and driver ride cancellation.

Passenger may cancel until the trip starts. Assigned driver may cancel
until the trip starts. In-progress and completed rides reject cancel.
"""
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.passenger import Passenger
from app.models.ride_request import RideRequest
from app.models.user import User
from app.utils.jwt import create_access_token
from app.utils.security import hash_password
from tests.ride_flow import list_responses, passenger_select_response

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
    from tests.ride_flow import create_pending_ride, driver_accept_passenger_offer, prepare_driver_online

    prepare_driver_online(driver_client, driver_headers)
    payload = create_pending_ride(passenger_client, passenger_headers)
    driver_accept_passenger_offer(driver_client, driver_headers, payload["id"])
    return payload


def _create_second_passenger(
    db_session: Session,
    client: TestClient,
) -> dict[str, Any]:
    user = User(
        full_name="Cancellation Passenger B",
        phone_number="+15550002801",
        email="cancellation.passenger.b@test.nexo",
        password=hash_password("TestPassengerBCancel123!"),
        role="passenger",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    profile = Passenger(
        user_id=user.id,
        first_name="Cancel",
        last_name="PassengerB",
        phone="+15550002802",
        email="cancellation.passenger.b.profile@test.nexo",
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)

    return {
        "client": client,
        "user": user,
        "passenger": profile,
        "headers": _auth_headers(user),
    }


def test_passenger_can_cancel_pending_ride(
    authenticated_passenger,
    db_session,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    passenger = authenticated_passenger["passenger"]

    # Seed a PENDING ride directly: create+dispatch now terminalizes when
    # no eligible driver remains (Phase 3.5), but PENDING cancel must still
    # work for the soft-wait / pre-terminalize window.
    ride = RideRequest(
        passenger_id=passenger.id,
        pickup_location=RIDE_CREATE_PAYLOAD["pickup_location"],
        pickup_latitude=RIDE_CREATE_PAYLOAD["pickup_latitude"],
        pickup_longitude=RIDE_CREATE_PAYLOAD["pickup_longitude"],
        destination=RIDE_CREATE_PAYLOAD["destination"],
        destination_latitude=RIDE_CREATE_PAYLOAD["destination_latitude"],
        destination_longitude=RIDE_CREATE_PAYLOAD["destination_longitude"],
        proposed_fare=RIDE_CREATE_PAYLOAD["proposed_fare"],
        status="pending",
        accepted_driver_id=None,
    )
    db_session.add(ride)
    db_session.commit()
    db_session.refresh(ride)
    ride_id = ride.id

    cancel_response = passenger_client.put(
        f"/rides/{ride_id}/cancel",
        headers=passenger_headers,
    )
    assert cancel_response.status_code == 200
    cancel_payload = cancel_response.json()
    assert cancel_payload["status"] == "cancelled_by_passenger"
    assert cancel_payload["accepted_driver_id"] is None

    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride is not None
    assert ride.status == "cancelled_by_passenger"
    assert ride.accepted_driver_id is None
    assert ride.passenger_id == passenger.id

    # Cancelled ride must not block creating another ride.
    second_response = passenger_client.post(
        "/rides/",
        headers=passenger_headers,
        json=RIDE_CREATE_PAYLOAD,
    )
    assert second_response.status_code == 200
    second_payload = second_response.json()
    assert second_payload["id"] != ride_id
    assert second_payload["passenger_id"] == passenger.id


def test_passenger_cancel_pending_driver_acceptance_releases_driver(
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
    ride = db_session.get(RideRequest, ride_id)
    assert ride is not None
    assert ride.status == "pending"
    assert ride.accepted_driver_id is None

    driver_row = db_session.get(User, driver.id)
    assert driver_row is not None
    assert driver_row.availability_status == "available"

    from app.models.driver_response import DriverResponse

    response_row = (
        db_session.query(DriverResponse)
        .filter(
            DriverResponse.ride_id == ride_id,
            DriverResponse.driver_id == driver.id,
            DriverResponse.status == "open",
        )
        .one()
    )
    response_id = response_row.id

    cancel_response = passenger_client.put(
        f"/rides/{ride_id}/cancel",
        headers=passenger_headers,
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled_by_passenger"
    assert cancel_response.json()["accepted_driver_id"] is None

    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride is not None
    assert ride.status == "cancelled_by_passenger"
    assert ride.accepted_driver_id is None

    driver_row = db_session.get(User, driver.id)
    assert driver_row is not None
    assert driver_row.availability_status == "available"

    response_row = db_session.get(DriverResponse, response_id)
    assert response_row is not None
    assert response_row.status == "withdrawn"


def test_other_passenger_cannot_cancel_ride(
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

    other = _create_second_passenger(db_session, passenger_client)

    response = other["client"].put(
        f"/rides/{ride_id}/cancel",
        headers=other["headers"],
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "You are not authorized to cancel this ride."

    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride is not None
    assert ride.status == "pending"
    assert ride.accepted_driver_id is None


def test_driver_cannot_cancel_pending_marketplace_request(
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
        f"/rides/{ride_id}/cancel",
        headers=driver_headers,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Ride cannot be cancelled in its current state."

    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride is not None
    assert ride.status == "pending"
    assert ride.accepted_driver_id is None


def test_passenger_can_cancel_accepted_ride_before_start(
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
    responses = list_responses(passenger_client, passenger_headers, ride_id)
    selected = passenger_select_response(
        passenger_client,
        passenger_headers,
        ride_id,
        responses[0]["id"],
    )
    assert selected["status"] == "accepted"

    cancel_response = passenger_client.put(
        f"/rides/{ride_id}/cancel",
        headers=passenger_headers,
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled_by_passenger"

    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride is not None
    assert ride.status == "cancelled_by_passenger"
    assert ride.accepted_driver_id == driver.id

    driver_row = db_session.get(User, driver.id)
    assert driver_row is not None
    assert driver_row.availability_status == "available"


def test_cancel_in_progress_ride_rejected(
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
    responses = list_responses(passenger_client, passenger_headers, ride_id)
    passenger_select_response(
        passenger_client,
        passenger_headers,
        ride_id,
        responses[0]["id"],
    )

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

    db_session.expire_all()
    assert db_session.get(RideRequest, ride_id).status == "in_progress"

    cancel_response = passenger_client.put(
        f"/rides/{ride_id}/cancel",
        headers=passenger_headers,
    )
    assert cancel_response.status_code == 400
    assert (
        cancel_response.json()["detail"]
        == "Ride cannot be cancelled in its current state."
    )

    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride is not None
    assert ride.status == "in_progress"


def test_cancel_completed_ride_rejected(
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
    responses = list_responses(passenger_client, passenger_headers, ride_id)
    passenger_select_response(
        passenger_client,
        passenger_headers,
        ride_id,
        responses[0]["id"],
    )

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

    db_session.expire_all()
    assert db_session.get(RideRequest, ride_id).status == "completed"

    cancel_response = passenger_client.put(
        f"/rides/{ride_id}/cancel",
        headers=passenger_headers,
    )
    assert cancel_response.status_code == 400
    assert (
        cancel_response.json()["detail"]
        == "Ride cannot be cancelled in its current state."
    )

    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride is not None
    assert ride.status == "completed"
