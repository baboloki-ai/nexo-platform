"""
L4.1.1: restore the driver's assigned active ride from the server after login.

GET /drivers/rides is the source of truth. A client sessionStorage cache
(nexo.driver.current_ride_id) must not decide which ride is restored.
"""
from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.constants.ride_status import RideStatus
from app.models.passenger import Passenger
from app.models.ride_request import RideRequest
from app.models.user import User
from app.utils.security import hash_password

from tests.ride_flow import RIDE_CREATE_PAYLOAD, advance_to_accepted

DRIVER_PASSWORD = "TestDriver123!"

ACTIVE_ASSIGNED_STATUSES = (
    RideStatus.ACCEPTED,
    RideStatus.DRIVER_ARRIVING,
    RideStatus.DRIVER_ARRIVED,
    RideStatus.IN_PROGRESS,
)

TERMINAL_STATUSES = (
    RideStatus.COMPLETED,
    RideStatus.CANCELLED_BY_PASSENGER,
    RideStatus.CANCELLED_BY_DRIVER,
    RideStatus.EXPIRED,
    RideStatus.NO_DRIVER_AVAILABLE,
)


def _login_headers(client: TestClient, email: str, password: str = DRIVER_PASSWORD) -> dict[str, str]:
    response = client.post(
        "/users/login",
        data={"username": email, "password": password},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    assert token
    return {"Authorization": f"Bearer {token}"}


def _relogin(client: TestClient, email: str) -> dict[str, str]:
    return _login_headers(client, email)


def select_active_assigned_ride(
    rides: list[dict[str, Any]],
    driver_id: int,
    session_storage_ride_id: int | None = None,
) -> dict[str, Any] | None:
    """Mirror the frontend L4.1.1 selector. session_storage_ride_id is ignored."""
    del session_storage_ride_id
    for ride in rides:
        if (
            ride["status"] in ACTIVE_ASSIGNED_STATUSES
            and ride.get("accepted_driver_id") == driver_id
        ):
            return ride
    return None


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


def _create_driver(
    db_session: Session,
    *,
    full_name: str,
    phone_number: str,
    email: str,
) -> User:
    user = User(
        full_name=full_name,
        phone_number=phone_number,
        email=email,
        password=hash_password(DRIVER_PASSWORD),
        role="driver",
        verification_status="approved",
        availability_status="offline",
        current_latitude=-26.2041,
        current_longitude=28.0473,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _create_passenger(
    db_session: Session,
    *,
    full_name: str,
    phone_number: str,
    email: str,
) -> tuple[User, Passenger]:
    user = User(
        full_name=full_name,
        phone_number=phone_number,
        email=email,
        password=hash_password("TestPassenger123!"),
        role="passenger",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    profile = Passenger(
        user_id=user.id,
        first_name="Other",
        last_name="Passenger",
        phone=phone_number,
        email=email,
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)
    return user, profile


def _driver_rides_after_login(
    client: TestClient,
    email: str,
) -> list[dict[str, Any]]:
    headers = _relogin(client, email)
    response = client.get("/drivers/rides", headers=headers)
    assert response.status_code == 200, response.text
    rows = response.json()
    assert isinstance(rows, list)
    return rows


def test_relogin_restores_active_ride_when_session_storage_is_empty(
    authenticated_passenger,
    authenticated_driver,
    client,
    driver_user,
):
    assigned = advance_to_accepted(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        driver_user.id,
    )

    rows = _driver_rides_after_login(client, driver_user.email)
    restored = select_active_assigned_ride(rows, driver_user.id, None)

    assert restored is not None
    assert restored["id"] == assigned["id"]
    assert restored["status"] == RideStatus.ACCEPTED
    assert restored["accepted_driver_id"] == driver_user.id


def test_relogin_restores_active_ride_when_session_storage_has_ride_id(
    authenticated_passenger,
    authenticated_driver,
    client,
    driver_user,
):
    assigned = advance_to_accepted(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        driver_user.id,
    )

    rows = _driver_rides_after_login(client, driver_user.email)
    restored = select_active_assigned_ride(rows, driver_user.id, assigned["id"])

    assert restored is not None
    assert restored["id"] == assigned["id"]
    assert restored["status"] == RideStatus.ACCEPTED
    assert restored["accepted_driver_id"] == driver_user.id


def test_relogin_restores_each_active_assigned_status(
    client,
    driver_user,
    passenger_profile,
    db_session,
):
    for status in ACTIVE_ASSIGNED_STATUSES:
        ride = _seed_assigned_ride(
            db_session,
            passenger_id=passenger_profile.id,
            driver_id=driver_user.id,
            status=status,
        )
        rows = _driver_rides_after_login(client, driver_user.email)
        restored_empty = select_active_assigned_ride(rows, driver_user.id, None)
        restored_cached = select_active_assigned_ride(
            rows,
            driver_user.id,
            ride.id,
        )
        assert restored_empty is not None
        assert restored_empty["id"] == ride.id
        assert restored_empty["status"] == status
        assert restored_cached == restored_empty
        db_session.delete(ride)
        db_session.commit()


def test_relogin_does_not_restore_completed_ride(
    authenticated_passenger,
    authenticated_driver,
    client,
    driver_user,
):
    assigned = advance_to_accepted(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        driver_user.id,
    )
    ride_id = assigned["id"]
    headers = authenticated_driver["headers"]
    assert authenticated_driver["client"].put(
        f"/rides/{ride_id}/arrive",
        headers=headers,
    ).status_code == 200
    assert authenticated_driver["client"].put(
        f"/rides/{ride_id}/driver-arrived",
        headers=headers,
    ).status_code == 200
    assert authenticated_driver["client"].put(
        f"/rides/{ride_id}/start",
        headers=headers,
    ).status_code == 200
    complete = authenticated_driver["client"].put(
        f"/rides/{ride_id}/complete",
        headers=headers,
    )
    assert complete.status_code == 200
    assert complete.json()["status"] == RideStatus.COMPLETED

    rows = _driver_rides_after_login(client, driver_user.email)
    assert any(item["id"] == ride_id for item in rows)
    restored = select_active_assigned_ride(rows, driver_user.id, ride_id)
    assert restored is None


def test_relogin_does_not_restore_terminal_or_unassigned_statuses(
    client,
    driver_user,
    passenger_profile,
    db_session,
):
    for status in (
        RideStatus.PENDING_DRIVER_ACCEPTANCE,
        *TERMINAL_STATUSES,
    ):
        ride = _seed_assigned_ride(
            db_session,
            passenger_id=passenger_profile.id,
            driver_id=driver_user.id,
            status=status,
        )
        rows = _driver_rides_after_login(client, driver_user.email)
        restored = select_active_assigned_ride(rows, driver_user.id, ride.id)
        assert restored is None
        db_session.delete(ride)
        db_session.commit()


def test_relogin_never_restores_another_drivers_ride(
    client,
    driver_user,
    passenger_profile,
    db_session,
):
    other_driver = _create_driver(
        db_session,
        full_name="Other Restoration Driver",
        phone_number="+15550004151",
        email="restore.other.driver@test.nexo",
    )
    _other_user, other_passenger = _create_passenger(
        db_session,
        full_name="Other Restoration Passenger",
        phone_number="+15550004152",
        email="restore.other.passenger@test.nexo",
    )
    own_ride = _seed_assigned_ride(
        db_session,
        passenger_id=passenger_profile.id,
        driver_id=driver_user.id,
        status=RideStatus.ACCEPTED,
    )
    other_ride = _seed_assigned_ride(
        db_session,
        passenger_id=other_passenger.id,
        driver_id=other_driver.id,
        status=RideStatus.IN_PROGRESS,
    )

    own_rows = _driver_rides_after_login(client, driver_user.email)
    own_ids = {item["id"] for item in own_rows}
    assert own_ride.id in own_ids
    assert other_ride.id not in own_ids
    assert select_active_assigned_ride(
        own_rows,
        driver_user.id,
        other_ride.id,
    )["id"] == own_ride.id

    other_rows = _driver_rides_after_login(client, other_driver.email)
    other_ids = {item["id"] for item in other_rows}
    assert other_ride.id in other_ids
    assert own_ride.id not in other_ids
    assert select_active_assigned_ride(
        other_rows,
        other_driver.id,
        own_ride.id,
    )["id"] == other_ride.id
    assert select_active_assigned_ride(
        other_rows,
        driver_user.id,
        own_ride.id,
    ) is None
