"""
Phase 3.1: go-offline blocked while the driver has a post-accept active ride.

PENDING_DRIVER_ACCEPTANCE (reserved) must still allow go-offline.
RideRequest status is the source of truth — rejection must not mutate
availability_status or the assigned ride.
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.constants.ride_status import RideStatus
from app.models.ride_request import RideRequest
from app.models.user import User
from tests.test_go_online_active_ride import (
    TERMINAL_RIDE_STATUSES,
    _seed_assigned_ride,
)

POST_ACCEPT_ACTIVE_STATUSES = [
    RideStatus.ACCEPTED,
    RideStatus.DRIVER_ARRIVING,
    RideStatus.DRIVER_ARRIVED,
    RideStatus.IN_PROGRESS,
]


def test_idle_driver_can_go_offline(
    authenticated_driver,
    db_session,
    driver_user,
):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]

    driver_user.availability_status = "available"
    db_session.commit()

    response = client.put("/drivers/go-offline", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "offline"
    assert response.json()["message"] == "Driver is now offline."

    db_session.expire_all()
    row = db_session.get(User, driver_user.id)
    assert row is not None
    assert row.availability_status == "offline"


def test_passenger_cannot_go_offline(authenticated_passenger):
    client = authenticated_passenger["client"]
    headers = authenticated_passenger["headers"]

    response = client.put("/drivers/go-offline", headers=headers)
    assert response.status_code == 403
    assert response.json()["detail"] == "Only drivers can go offline."


@pytest.mark.parametrize("ride_status", POST_ACCEPT_ACTIVE_STATUSES)
def test_post_accept_active_ride_blocks_go_offline(
    authenticated_driver,
    authenticated_passenger,
    db_session,
    driver_user,
    ride_status,
):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]
    passenger = authenticated_passenger["passenger"]

    driver_user.availability_status = "busy"
    db_session.commit()

    ride = _seed_assigned_ride(
        db_session,
        passenger_id=passenger.id,
        driver_id=driver_user.id,
        status=ride_status,
    )

    response = client.put("/drivers/go-offline", headers=headers)
    assert response.status_code == 400
    assert response.json()["detail"] == "Driver has an active ride."

    db_session.expire_all()
    row = db_session.get(User, driver_user.id)
    assert row is not None
    assert row.availability_status == "busy"

    ride_row = db_session.get(RideRequest, ride.id)
    assert ride_row is not None
    assert ride_row.status == ride_status
    assert ride_row.accepted_driver_id == driver_user.id


def test_pending_driver_acceptance_allows_go_offline(
    authenticated_driver,
    authenticated_passenger,
    db_session,
    driver_user,
):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]
    passenger = authenticated_passenger["passenger"]

    driver_user.availability_status = "reserved"
    db_session.commit()

    ride = _seed_assigned_ride(
        db_session,
        passenger_id=passenger.id,
        driver_id=driver_user.id,
        status=RideStatus.PENDING_DRIVER_ACCEPTANCE,
    )

    response = client.put("/drivers/go-offline", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "offline"
    assert response.json()["message"] == "Driver is now offline."

    db_session.expire_all()
    row = db_session.get(User, driver_user.id)
    assert row is not None
    assert row.availability_status == "offline"

    ride_row = db_session.get(RideRequest, ride.id)
    assert ride_row is not None
    assert ride_row.status == RideStatus.PENDING_DRIVER_ACCEPTANCE
    assert ride_row.accepted_driver_id == driver_user.id


@pytest.mark.parametrize("ride_status", TERMINAL_RIDE_STATUSES)
def test_terminal_assigned_ride_does_not_block_go_offline(
    authenticated_driver,
    authenticated_passenger,
    db_session,
    driver_user,
    ride_status,
):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]
    passenger = authenticated_passenger["passenger"]

    driver_user.availability_status = "available"
    db_session.commit()

    _seed_assigned_ride(
        db_session,
        passenger_id=passenger.id,
        driver_id=driver_user.id,
        status=ride_status,
    )

    response = client.put("/drivers/go-offline", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "offline"

    db_session.expire_all()
    row = db_session.get(User, driver_user.id)
    assert row is not None
    assert row.availability_status == "offline"
