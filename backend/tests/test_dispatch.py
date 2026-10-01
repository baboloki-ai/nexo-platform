"""
L3.0 marketplace dispatch: broadcast to eligible drivers, no auto-assign.
"""
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.driver_response import DriverResponse
from app.models.ride_request import RideRequest
from app.models.user import User
from app.models.vehicle import Vehicle
from app.services.wallet_service import WalletService
from app.utils.jwt import create_access_token
from app.utils.security import hash_password

PICKUP_LAT = -26.2041
PICKUP_LON = 28.0473
NEAR_LAT = -26.2045
NEAR_LON = 28.0475
FAR_LAT = -26.3000
FAR_LON = 28.1500

RIDE_CREATE_PAYLOAD = {
    "pickup_location": "Sandton City Pickup",
    "pickup_latitude": PICKUP_LAT,
    "pickup_longitude": PICKUP_LON,
    "destination": "OR Tambo Destination",
    "destination_latitude": -26.1330,
    "destination_longitude": 28.2420,
    "proposed_fare": 150.0,
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


def _create_driver(
    db_session: Session,
    *,
    full_name: str,
    phone_number: str,
    email: str,
    availability_status: str = "available",
    current_latitude: float | None = None,
    current_longitude: float | None = None,
) -> User:
    user = User(
        full_name=full_name,
        phone_number=phone_number,
        email=email,
        password=hash_password("TestDriverDispatch123!"),
        role="driver",
        verification_status="approved",
        availability_status=availability_status,
        current_latitude=current_latitude,
        current_longitude=current_longitude,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    WalletService.ensure_wallet(db_session, user.id)
    db_session.add(
        Vehicle(
            driver_id=user.id,
            make="Toyota",
            model="Corolla",
            year=2021,
            color="White",
            registration_number=f"D{user.id:04d}NEX",
            vehicle_type="sedan",
            verification_status="approved",
        )
    )
    db_session.commit()
    return user


def test_create_does_not_auto_assign_nearest_or_farthest(
    authenticated_passenger,
    db_session: Session,
):
    near = _create_driver(
        db_session,
        full_name="Near Eligible Driver",
        phone_number="+15550000101",
        email="near.driver.dispatch@test.nexo",
        current_latitude=NEAR_LAT,
        current_longitude=NEAR_LON,
    )
    far = _create_driver(
        db_session,
        full_name="Far Eligible Driver",
        phone_number="+15550000102",
        email="far.driver.dispatch@test.nexo",
        current_latitude=FAR_LAT,
        current_longitude=FAR_LON,
    )
    with patch(
        "app.services.notification_service.NotificationService.notify_marketplace_request_created"
    ) as broadcast:
        payload = authenticated_passenger["client"].post(
            "/rides/",
            headers=authenticated_passenger["headers"],
            json=RIDE_CREATE_PAYLOAD,
        ).json()
    assert payload["status"] == "pending"
    assert payload["accepted_driver_id"] is None
    notified = {call.kwargs["driver_id"] for call in broadcast.call_args_list}
    assert near.id in notified
    assert far.id in notified
    db_session.expire_all()
    ride = db_session.get(RideRequest, payload["id"])
    assert ride.status == "pending"
    assert ride.accepted_driver_id is None
    assert db_session.query(DriverResponse).filter_by(ride_id=ride.id).count() == 0


def test_driver_without_gps_is_not_broadcast(
    authenticated_passenger,
    db_session: Session,
):
    eligible = _create_driver(
        db_session,
        full_name="GPS Driver",
        phone_number="+15550000103",
        email="gps.driver.dispatch@test.nexo",
        current_latitude=NEAR_LAT,
        current_longitude=NEAR_LON,
    )
    no_gps = _create_driver(
        db_session,
        full_name="No GPS Driver",
        phone_number="+15550000104",
        email="nogps.driver.dispatch@test.nexo",
    )
    with patch(
        "app.services.notification_service.NotificationService.notify_marketplace_request_created"
    ) as broadcast:
        authenticated_passenger["client"].post(
            "/rides/",
            headers=authenticated_passenger["headers"],
            json=RIDE_CREATE_PAYLOAD,
        )
    notified = {call.kwargs["driver_id"] for call in broadcast.call_args_list}
    assert eligible.id in notified
    assert no_gps.id not in notified


def test_offline_and_busy_drivers_are_not_broadcast(
    authenticated_passenger,
    db_session: Session,
):
    available = _create_driver(
        db_session,
        full_name="Available Driver",
        phone_number="+15550000105",
        email="available.driver.dispatch@test.nexo",
        current_latitude=NEAR_LAT,
        current_longitude=NEAR_LON,
    )
    _create_driver(
        db_session,
        full_name="Offline Driver",
        phone_number="+15550000106",
        email="offline.driver.dispatch@test.nexo",
        availability_status="offline",
        current_latitude=NEAR_LAT,
        current_longitude=NEAR_LON,
    )
    _create_driver(
        db_session,
        full_name="Busy Driver",
        phone_number="+15550000107",
        email="busy.driver.dispatch@test.nexo",
        availability_status="busy",
        current_latitude=NEAR_LAT,
        current_longitude=NEAR_LON,
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
    assert notified == {available.id}
    assert payload["status"] == "pending"


def test_no_eligible_driver_leaves_request_open(
    authenticated_passenger,
    db_session: Session,
):
    payload = authenticated_passenger["client"].post(
        "/rides/",
        headers=authenticated_passenger["headers"],
        json=RIDE_CREATE_PAYLOAD,
    ).json()
    assert payload["status"] == "pending"
    assert payload["accepted_driver_id"] is None
    db_session.expire_all()
    ride = db_session.get(RideRequest, payload["id"])
    assert ride.status == "pending"


def test_driver_withdraw_keeps_request_open_for_others(
    authenticated_passenger,
    db_session: Session,
    client: TestClient,
):
    first = _create_driver(
        db_session,
        full_name="First Responder",
        phone_number="+15550000108",
        email="first.responder.dispatch@test.nexo",
        current_latitude=NEAR_LAT,
        current_longitude=NEAR_LON,
    )
    second = _create_driver(
        db_session,
        full_name="Second Responder",
        phone_number="+15550000109",
        email="second.responder.dispatch@test.nexo",
        current_latitude=FAR_LAT,
        current_longitude=FAR_LON,
    )
    payload = authenticated_passenger["client"].post(
        "/rides/",
        headers=authenticated_passenger["headers"],
        json=RIDE_CREATE_PAYLOAD,
    ).json()
    ride_id = payload["id"]
    first_headers = _auth_headers(first)
    second_headers = _auth_headers(second)
    client.put("/drivers/go-online", headers=first_headers)
    client.put("/drivers/go-online", headers=second_headers)
    assert client.put(
        f"/rides/{ride_id}/respond",
        headers=first_headers,
        json={"response_type": "accept_passenger_offer"},
    ).status_code == 200
    assert client.put(
        f"/rides/{ride_id}/reject",
        headers=first_headers,
    ).status_code == 200
    assert client.put(
        f"/rides/{ride_id}/respond",
        headers=second_headers,
        json={"response_type": "accept_passenger_offer"},
    ).status_code == 200
    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride.status == "pending"
    assert ride.accepted_driver_id is None
    statuses = {
        row.driver_id: row.status
        for row in db_session.query(DriverResponse).filter_by(ride_id=ride_id)
    }
    assert statuses[first.id] == "withdrawn"
    assert statuses[second.id] == "open"
