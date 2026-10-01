"""
Phase 3.0: go-online blocked while the driver still has an assigned active ride.

RideRequest status (accepted_driver_id) is the source of truth — not
availability_status alone. With Phase 3.1, busy drivers with an active ride
also cannot go offline; both endpoints stay rejected while the ride is assigned.
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.constants.ride_status import RideStatus
from app.models.ride_request import RideRequest
from app.models.user import User

from tests.ride_flow import (
    DRIVER_LOCATION_PAYLOAD,
    RIDE_CREATE_PAYLOAD,
    advance_to_accepted,
)

ACTIVE_RIDE_STATUSES = [
    RideStatus.PENDING_DRIVER_ACCEPTANCE,
    RideStatus.ACCEPTED,
    RideStatus.DRIVER_ARRIVING,
    RideStatus.DRIVER_ARRIVED,
    RideStatus.IN_PROGRESS,
]

TERMINAL_RIDE_STATUSES = [
    RideStatus.COMPLETED,
    RideStatus.CANCELLED_BY_PASSENGER,
    RideStatus.CANCELLED_BY_DRIVER,
    RideStatus.EXPIRED,
    RideStatus.NO_DRIVER_AVAILABLE,
]


def _seed_assigned_ride(
    db_session: Session,
    *,
    passenger_id: int,
    driver_id: int,
    status: str,
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


def _expected_go_online_detail(status: str) -> str:
    if status == RideStatus.PENDING_DRIVER_ACCEPTANCE:
        return "Driver has a pending ride assignment."
    return "Driver has an active ride."


def test_driver_with_no_active_ride_can_go_online(
    authenticated_driver,
    db_session,
    driver_user,
):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]

    driver_user.availability_status = "offline"
    db_session.commit()

    response = client.put("/drivers/go-online", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "available"
    assert response.json()["message"] == "Driver is now online."

    db_session.expire_all()
    row = db_session.get(User, driver_user.id)
    assert row is not None
    assert row.availability_status == "available"


@pytest.mark.parametrize("ride_status", ACTIVE_RIDE_STATUSES)
def test_active_assigned_ride_blocks_go_online(
    authenticated_driver,
    authenticated_passenger,
    db_session,
    driver_user,
    ride_status,
):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]
    passenger = authenticated_passenger["passenger"]

    driver_user.availability_status = "offline"
    db_session.commit()

    ride = _seed_assigned_ride(
        db_session,
        passenger_id=passenger.id,
        driver_id=driver_user.id,
        status=ride_status,
    )

    response = client.put("/drivers/go-online", headers=headers)
    assert response.status_code == 400
    assert response.json()["detail"] == _expected_go_online_detail(ride_status)

    db_session.expire_all()
    row = db_session.get(User, driver_user.id)
    assert row is not None
    assert row.availability_status == "offline"

    ride_row = db_session.get(RideRequest, ride.id)
    assert ride_row is not None
    assert ride_row.status == ride_status
    assert ride_row.accepted_driver_id == driver_user.id


def test_busy_active_ride_blocks_go_offline_and_go_online(
    authenticated_passenger,
    authenticated_driver,
    db_session,
    driver_user,
):
    """
    Phase 3.0 + 3.1 regression: an assigned active ride blocks both
    go-offline and go-online. Driver stays busy; ride stays assigned.
    """
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]

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

    selected = advance_to_accepted(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        driver_user.id,
    )
    ride_id = selected["id"]
    assert selected["status"] == "accepted"
    assert selected["accepted_driver_id"] == driver_user.id

    db_session.expire_all()
    driver_row = db_session.get(User, driver_user.id)
    assert driver_row is not None
    assert driver_row.availability_status == "busy"

    go_offline_response = driver_client.put(
        "/drivers/go-offline",
        headers=driver_headers,
    )
    assert go_offline_response.status_code == 400
    assert go_offline_response.json()["detail"] == "Driver has an active ride."

    db_session.expire_all()
    driver_row = db_session.get(User, driver_user.id)
    assert driver_row is not None
    assert driver_row.availability_status == "busy"

    ride = db_session.get(RideRequest, ride_id)
    assert ride is not None
    assert ride.status == "accepted"
    assert ride.accepted_driver_id == driver_user.id

    go_online_while_active = driver_client.put(
        "/drivers/go-online",
        headers=driver_headers,
    )
    assert go_online_while_active.status_code == 400
    assert go_online_while_active.json()["detail"] == "Driver has an active ride."

    db_session.expire_all()
    driver_row = db_session.get(User, driver_user.id)
    assert driver_row is not None
    assert driver_row.availability_status == "busy"

    ride = db_session.get(RideRequest, ride_id)
    assert ride is not None
    assert ride.status == "accepted"
    assert ride.accepted_driver_id == driver_user.id


@pytest.mark.parametrize("ride_status", TERMINAL_RIDE_STATUSES)
def test_terminal_assigned_ride_does_not_block_go_online(
    authenticated_driver,
    authenticated_passenger,
    db_session,
    driver_user,
    ride_status,
):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]
    passenger = authenticated_passenger["passenger"]

    driver_user.availability_status = "offline"
    db_session.commit()

    _seed_assigned_ride(
        db_session,
        passenger_id=passenger.id,
        driver_id=driver_user.id,
        status=ride_status,
    )

    response = client.put("/drivers/go-online", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "available"

    db_session.expire_all()
    row = db_session.get(User, driver_user.id)
    assert row is not None
    assert row.availability_status == "available"
