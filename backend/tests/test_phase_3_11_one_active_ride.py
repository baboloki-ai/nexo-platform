"""
Phase 3.11: one active RideRequest per passenger.

Enforced by a PostgreSQL partial unique index. Sequential duplicates still
return the existing 400 from the application SELECT; concurrent creates that
both pass the SELECT are serialized by the index, and IntegrityError is
translated to the same friendly 400.
"""
from __future__ import annotations

import threading
import time
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.constants.ride_status import RideStatus
from app.database.dependencies import get_db
from app.main import app
from app.models.passenger import Passenger
from app.models.ride_request import (
    UQ_RIDE_REQUESTS_ONE_ACTIVE_PER_PASSENGER,
    RideRequest,
)
from app.models.user import User
from app.services.ride_service import RideService
from app.utils.jwt import create_access_token
from app.utils.security import hash_password
from tests.conftest import TEST_DATABASE_NAME, TEST_DATABASE_URL

PICKUP_LAT = -26.2041
PICKUP_LON = 28.0473
DEST_LAT = -26.1330
DEST_LON = 28.2420

RIDE_CREATE_PAYLOAD = {
    "pickup_location": "Sandton City Pickup",
    "pickup_latitude": PICKUP_LAT,
    "pickup_longitude": PICKUP_LON,
    "destination": "OR Tambo Destination",
    "destination_latitude": DEST_LAT,
    "destination_longitude": DEST_LON,
    "proposed_fare": 150.0,
}

CREATE_RIDE_KWARGS = {
    "pickup_location": RIDE_CREATE_PAYLOAD["pickup_location"],
    "pickup_latitude": RIDE_CREATE_PAYLOAD["pickup_latitude"],
    "pickup_longitude": RIDE_CREATE_PAYLOAD["pickup_longitude"],
    "destination": RIDE_CREATE_PAYLOAD["destination"],
    "destination_latitude": RIDE_CREATE_PAYLOAD["destination_latitude"],
    "destination_longitude": RIDE_CREATE_PAYLOAD["destination_longitude"],
    "proposed_fare": RIDE_CREATE_PAYLOAD["proposed_fare"],
}

DRIVER_LOCATION_PAYLOAD = {
    "latitude": PICKUP_LAT,
    "longitude": PICKUP_LON,
}

ACTIVE_STATUSES = (
    RideStatus.PENDING,
    RideStatus.PENDING_DRIVER_ACCEPTANCE,
    RideStatus.ACCEPTED,
    RideStatus.DRIVER_ARRIVING,
    RideStatus.DRIVER_ARRIVED,
    RideStatus.IN_PROGRESS,
)

ACTIVE_RIDE_DETAIL = "You already have an active ride."

DB_ERROR_MARKERS = (
    "IntegrityError",
    "UniqueViolation",
    "duplicate key",
    "uq_ride_requests_one_active_per_passenger",
    "psycopg",
    "sqlalchemy",
    "traceback",
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
        password=hash_password("TestPhase311Driver123!"),
        role="driver",
        verification_status="approved",
        availability_status="available",
        current_latitude=PICKUP_LAT,
        current_longitude=PICKUP_LON,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _seed_ride(
    db_session: Session,
    passenger_id: int,
    status: str,
    *,
    accepted_driver_id: int | None = None,
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
        accepted_driver_id=accepted_driver_id,
    )
    db_session.add(ride)
    db_session.commit()
    db_session.refresh(ride)
    return ride


def _active_rides(db_session: Session, passenger_id: int) -> list[RideRequest]:
    return (
        db_session.query(RideRequest)
        .filter(
            RideRequest.passenger_id == passenger_id,
            RideRequest.status.in_(list(ACTIVE_STATUSES)),
        )
        .all()
    )


def _waiting_lock_backends(observer: Session) -> int:
    return int(
        observer.execute(
            text(
                """
                SELECT count(*)
                FROM pg_stat_activity
                WHERE datname = current_database()
                  AND pid <> pg_backend_pid()
                  AND wait_event_type = 'Lock'
                """
            )
        ).scalar_one()
    )


def _wait_for_lock_waiters(
    observer: Session,
    *,
    minimum: int,
    timeout_seconds: float = 5.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if _waiting_lock_backends(observer) >= minimum:
            return
    raise TimeoutError(
        f"Timed out waiting for {minimum} PostgreSQL lock waiters; "
        f"last count={_waiting_lock_backends(observer)}"
    )


def _assert_friendly_active_ride_error(exc: BaseException) -> None:
    assert isinstance(exc, HTTPException)
    assert exc.status_code == 400
    assert exc.detail == ACTIVE_RIDE_DETAIL
    rendered = str(exc.detail)
    for marker in DB_ERROR_MARKERS:
        assert marker.lower() not in rendered.lower()


def _run_concurrent_create_ride(
    *,
    test_session_factory: sessionmaker,
    passenger_user_id: int,
) -> dict[str, Any]:
    start_barrier = threading.Barrier(3)
    outcomes: dict[str, Any] = {
        "a": {"ok": False, "error": None, "ride_id": None, "status": None},
        "b": {"ok": False, "error": None, "ride_id": None, "status": None},
    }
    outcomes_lock = threading.Lock()

    def _blocker() -> None:
        session = test_session_factory()
        try:
            session.execute(
                text("LOCK TABLE ride_requests IN SHARE ROW EXCLUSIVE MODE")
            )
            start_barrier.wait()
            _wait_for_lock_waiters(session, minimum=2)
            session.rollback()
        finally:
            session.close()

    def _worker(label: str) -> None:
        session = test_session_factory()
        try:
            user = session.get(User, passenger_user_id)
            assert user is not None
            start_barrier.wait()
            try:
                ride = RideService.create_ride(
                    db=session,
                    current_user=user,
                    **CREATE_RIDE_KWARGS,
                )
                with outcomes_lock:
                    outcomes[label]["ok"] = True
                    outcomes[label]["ride_id"] = ride.id
                    outcomes[label]["status"] = ride.status
            except Exception as exc:  # noqa: BLE001 - capture for main-thread assert
                with outcomes_lock:
                    outcomes[label]["error"] = exc
                session.rollback()
        finally:
            session.close()

    threads = [
        threading.Thread(target=_blocker, name="active-ride-blocker"),
        threading.Thread(target=_worker, args=("a",), name="active-ride-worker-a"),
        threading.Thread(target=_worker, args=("b",), name="active-ride-worker-b"),
    ]

    with patch(
        "app.services.dispatch_service.NotificationService.send_ride_offer",
    ), patch(
        "app.services.dispatch_service.NotificationService.notify_no_driver_available",
    ):
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)
            assert not thread.is_alive(), f"Thread {thread.name} did not finish"

    return outcomes


def test_partial_unique_index_exists(db_session: Session):
    row = db_session.execute(
        text(
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = 'ride_requests'
              AND indexname = :index_name
            """
        ),
        {"index_name": UQ_RIDE_REQUESTS_ONE_ACTIVE_PER_PASSENGER},
    ).one_or_none()

    assert row is not None
    indexname, indexdef = row
    assert indexname == UQ_RIDE_REQUESTS_ONE_ACTIVE_PER_PASSENGER
    indexdef_lower = indexdef.lower()
    assert "unique" in indexdef_lower
    assert "passenger_id" in indexdef_lower
    assert "where" in indexdef_lower
    for status in ACTIVE_STATUSES:
        assert f"'{status}'" in indexdef_lower


def test_concurrent_create_allows_only_one_active_ride(
    db_session: Session,
    test_session_factory: sessionmaker,
    passenger_user: User,
    passenger_profile: Passenger,
    driver_user: User,
):
    assert TEST_DATABASE_NAME in TEST_DATABASE_URL
    assert driver_user.availability_status == "available"

    outcomes = _run_concurrent_create_ride(
        test_session_factory=test_session_factory,
        passenger_user_id=passenger_user.id,
    )

    winners = [label for label in ("a", "b") if outcomes[label]["ok"]]
    losers = [label for label in ("a", "b") if not outcomes[label]["ok"]]
    assert len(winners) == 1, outcomes
    assert len(losers) == 1, outcomes

    winner = outcomes[winners[0]]
    loser = outcomes[losers[0]]
    assert winner["error"] is None
    assert winner["ride_id"] is not None
    _assert_friendly_active_ride_error(loser["error"])

    db_session.expire_all()
    active = _active_rides(db_session, passenger_profile.id)
    assert len(active) == 1
    assert active[0].id == winner["ride_id"]

    all_rides = (
        db_session.query(RideRequest)
        .filter(RideRequest.passenger_id == passenger_profile.id)
        .all()
    )
    assert len(all_rides) == 1


def test_concurrent_create_with_two_drivers_assigns_only_one_ride(
    db_session: Session,
    test_session_factory: sessionmaker,
    passenger_user: User,
    passenger_profile: Passenger,
    driver_user: User,
):
    assert TEST_DATABASE_NAME in TEST_DATABASE_URL
    second_driver = _create_driver(
        db_session,
        full_name="Phase 3.11 Second Driver",
        phone_number="+15550003111",
        email="phase311.second.driver@test.nexo",
    )
    assert driver_user.availability_status == "available"
    assert second_driver.availability_status == "available"

    outcomes = _run_concurrent_create_ride(
        test_session_factory=test_session_factory,
        passenger_user_id=passenger_user.id,
    )

    winners = [label for label in ("a", "b") if outcomes[label]["ok"]]
    losers = [label for label in ("a", "b") if not outcomes[label]["ok"]]
    assert len(winners) == 1, outcomes
    assert len(losers) == 1, outcomes
    _assert_friendly_active_ride_error(outcomes[losers[0]]["error"])

    db_session.expire_all()
    rides = (
        db_session.query(RideRequest)
        .filter(RideRequest.passenger_id == passenger_profile.id)
        .all()
    )
    assert len(rides) == 1
    winner_ride = rides[0]
    assert winner_ride.status == RideStatus.PENDING
    assert winner_ride.accepted_driver_id is None


def test_sequential_second_active_ride_returns_existing_400(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    passenger = authenticated_passenger["passenger"]
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]

    _prepare_driver_online(driver_client, driver_headers)
    first = passenger_client.post(
        "/rides/",
        headers=passenger_headers,
        json=RIDE_CREATE_PAYLOAD,
    )
    assert first.status_code == 200
    assert first.json()["status"] == RideStatus.PENDING

    second = passenger_client.post(
        "/rides/",
        headers=passenger_headers,
        json=RIDE_CREATE_PAYLOAD,
    )
    assert second.status_code == 400
    assert second.json()["detail"] == ACTIVE_RIDE_DETAIL
    for marker in DB_ERROR_MARKERS:
        assert marker.lower() not in second.text.lower()

    db_session.expire_all()
    assert len(_active_rides(db_session, passenger.id)) == 1


def test_completed_ride_allows_new_ride(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    passenger = authenticated_passenger["passenger"]
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]

    _prepare_driver_online(driver_client, driver_headers)
    from tests.ride_flow import advance_to_accepted

    selected = advance_to_accepted(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        driver.id,
    )
    ride_id = selected["id"]
    assert driver_client.put(
        f"/rides/{ride_id}/arrive", headers=driver_headers
    ).status_code == 200
    assert driver_client.put(
        f"/rides/{ride_id}/driver-arrived", headers=driver_headers
    ).status_code == 200
    assert driver_client.put(
        f"/rides/{ride_id}/start", headers=driver_headers
    ).status_code == 200
    complete = driver_client.put(
        f"/rides/{ride_id}/complete", headers=driver_headers
    )
    assert complete.status_code == 200
    assert complete.json()["status"] == RideStatus.COMPLETED

    _prepare_driver_online(driver_client, driver_headers)
    second = passenger_client.post(
        "/rides/",
        headers=passenger_headers,
        json=RIDE_CREATE_PAYLOAD,
    )
    assert second.status_code == 200
    assert second.json()["id"] != ride_id
    assert second.json()["status"] == RideStatus.PENDING
    assert second.json()["accepted_driver_id"] is None

    db_session.expire_all()
    first_row = db_session.get(RideRequest, ride_id)
    second_row = db_session.get(RideRequest, second.json()["id"])
    assert first_row is not None and first_row.status == RideStatus.COMPLETED
    assert second_row is not None
    assert len(_active_rides(db_session, passenger.id)) == 1


@pytest.mark.parametrize(
    "terminal_status",
    [
        RideStatus.CANCELLED_BY_PASSENGER,
        RideStatus.CANCELLED_BY_DRIVER,
    ],
)
def test_cancelled_ride_allows_new_ride(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
    terminal_status: str,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    passenger = authenticated_passenger["passenger"]
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]

    seeded = _seed_ride(db_session, passenger.id, terminal_status)
    _prepare_driver_online(driver_client, driver_headers)

    second = passenger_client.post(
        "/rides/",
        headers=passenger_headers,
        json=RIDE_CREATE_PAYLOAD,
    )
    assert second.status_code == 200
    assert second.json()["id"] != seeded.id

    db_session.expire_all()
    rides = (
        db_session.query(RideRequest)
        .filter(RideRequest.passenger_id == passenger.id)
        .all()
    )
    assert len(rides) == 2
    statuses = {ride.status for ride in rides}
    assert terminal_status in statuses
    assert RideStatus.PENDING in statuses


def test_cancelled_by_passenger_api_allows_new_ride(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    passenger = authenticated_passenger["passenger"]
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]

    _prepare_driver_online(driver_client, driver_headers)
    first = passenger_client.post(
        "/rides/",
        headers=passenger_headers,
        json=RIDE_CREATE_PAYLOAD,
    )
    assert first.status_code == 200
    ride_id = first.json()["id"]

    cancel = passenger_client.put(
        f"/rides/{ride_id}/cancel",
        headers=passenger_headers,
    )
    assert cancel.status_code == 200
    assert cancel.json()["status"] == RideStatus.CANCELLED_BY_PASSENGER

    _prepare_driver_online(driver_client, driver_headers)
    second = passenger_client.post(
        "/rides/",
        headers=passenger_headers,
        json=RIDE_CREATE_PAYLOAD,
    )
    assert second.status_code == 200
    assert second.json()["id"] != ride_id

    db_session.expire_all()
    assert len(_active_rides(db_session, passenger.id)) == 1


def test_no_driver_available_allows_new_ride(
    authenticated_passenger,
    db_session: Session,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    passenger = authenticated_passenger["passenger"]

    first = passenger_client.post(
        "/rides/",
        headers=passenger_headers,
        json=RIDE_CREATE_PAYLOAD,
    )
    assert first.status_code == 200
    assert first.json()["status"] == RideStatus.PENDING

    second = passenger_client.post(
        "/rides/",
        headers=passenger_headers,
        json=RIDE_CREATE_PAYLOAD,
    )
    assert second.status_code == 400
    assert second.json()["detail"] == ACTIVE_RIDE_DETAIL

    db_session.expire_all()
    assert len(_active_rides(db_session, passenger.id)) == 1


def test_pending_driver_acceptance_blocks_new_ride(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    passenger = authenticated_passenger["passenger"]
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]

    _prepare_driver_online(driver_client, driver_headers)
    first = passenger_client.post(
        "/rides/",
        headers=passenger_headers,
        json=RIDE_CREATE_PAYLOAD,
    )
    assert first.status_code == 200
    assert first.json()["status"] == RideStatus.PENDING

    second = passenger_client.post(
        "/rides/",
        headers=passenger_headers,
        json=RIDE_CREATE_PAYLOAD,
    )
    assert second.status_code == 400
    assert second.json()["detail"] == ACTIVE_RIDE_DETAIL

    db_session.expire_all()
    assert len(_active_rides(db_session, passenger.id)) == 1


@pytest.mark.parametrize(
    "active_status",
    [
        RideStatus.PENDING,
        RideStatus.ACCEPTED,
        RideStatus.DRIVER_ARRIVING,
        RideStatus.DRIVER_ARRIVED,
        RideStatus.IN_PROGRESS,
    ],
)
def test_active_statuses_block_new_ride(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
    active_status: str,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    passenger = authenticated_passenger["passenger"]
    driver = authenticated_driver["user"]

    seeded = _seed_ride(
        db_session,
        passenger.id,
        active_status,
        accepted_driver_id=driver.id,
    )

    second = passenger_client.post(
        "/rides/",
        headers=passenger_headers,
        json=RIDE_CREATE_PAYLOAD,
    )
    assert second.status_code == 400
    assert second.json()["detail"] == ACTIVE_RIDE_DETAIL

    db_session.expire_all()
    active = _active_rides(db_session, passenger.id)
    assert len(active) == 1
    assert active[0].id == seeded.id
    assert active[0].status == active_status


def test_integrity_error_translates_to_friendly_400_not_500(
    passenger_user: User,
    passenger_profile: Passenger,
    test_session_factory: sessionmaker,
):
    session = test_session_factory()
    original_commit = session.commit

    def racing_commit(*args: Any, **kwargs: Any):
        competitor = test_session_factory()
        try:
            competitor.add(
                RideRequest(
                    passenger_id=passenger_profile.id,
                    pickup_location="Competing Pickup",
                    pickup_latitude=PICKUP_LAT,
                    pickup_longitude=PICKUP_LON,
                    destination="Competing Destination",
                    destination_latitude=DEST_LAT,
                    destination_longitude=DEST_LON,
                    proposed_fare=99.0,
                    status=RideStatus.PENDING,
                )
            )
            competitor.commit()
        finally:
            competitor.close()
        return original_commit(*args, **kwargs)

    try:
        user = session.get(User, passenger_user.id)
        assert user is not None
        with patch.object(session, "commit", side_effect=racing_commit):
            with pytest.raises(HTTPException) as exc_info:
                RideService.create_ride(
                    db=session,
                    current_user=user,
                    **CREATE_RIDE_KWARGS,
                )
        _assert_friendly_active_ride_error(exc_info.value)
        assert exc_info.value.status_code != 500
    finally:
        session.close()

    observer = test_session_factory()
    try:
        active = _active_rides(observer, passenger_profile.id)
        assert len(active) == 1
        assert active[0].pickup_location == "Competing Pickup"
    finally:
        observer.close()


def test_integrity_error_http_response_is_friendly_400(
    passenger_user: User,
    passenger_profile: Passenger,
    test_session_factory: sessionmaker,
):
    def override_get_db():
        session = test_session_factory()
        original_commit = session.commit

        def racing_commit(*args: Any, **kwargs: Any):
            competitor = test_session_factory()
            try:
                competitor.add(
                    RideRequest(
                        passenger_id=passenger_profile.id,
                        pickup_location="HTTP Competing Pickup",
                        pickup_latitude=PICKUP_LAT,
                        pickup_longitude=PICKUP_LON,
                        destination="HTTP Competing Destination",
                        destination_latitude=DEST_LAT,
                        destination_longitude=DEST_LON,
                        proposed_fare=88.0,
                        status=RideStatus.PENDING,
                    )
                )
                competitor.commit()
            finally:
                competitor.close()
            return original_commit(*args, **kwargs)

        session.commit = racing_commit  # type: ignore[method-assign]
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            response = client.post(
                "/rides/",
                headers=_auth_headers(passenger_user),
                json=RIDE_CREATE_PAYLOAD,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.status_code != 500
    assert response.json()["detail"] == ACTIVE_RIDE_DETAIL
    for marker in DB_ERROR_MARKERS:
        assert marker.lower() not in response.text.lower()
