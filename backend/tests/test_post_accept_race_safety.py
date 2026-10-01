"""
Phase 3.7: CAS-safe post-accept ride lifecycle transitions.

Covers arrive / driver_arrived / start / complete conditional updates,
duplicate and concurrent single-winner behavior, and the critical
start_ride vs driver_arrived regression race.
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
from app.models.ride_request import RideRequest
from app.models.user import User
from app.services.ride_service import RideService
from app.utils.jwt import create_access_token
from app.utils.security import hash_password
from tests.ride_flow import advance_to_accepted as _flow_advance_to_accepted

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
    assert driver_client.put(
        "/drivers/go-online",
        headers=driver_headers,
    ).status_code == 200
    assert driver_client.put(
        "/drivers/location",
        headers=driver_headers,
        json=DRIVER_LOCATION_PAYLOAD,
    ).status_code == 200


def _create_assigned_ride(
    passenger_client: TestClient,
    passenger_headers: dict[str, str],
    driver_client: TestClient,
    driver_headers: dict[str, str],
    expected_driver_id: int,
) -> dict[str, Any]:
    return _flow_advance_to_accepted(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        expected_driver_id,
    )


def _accept_ride(
    driver_client: TestClient,
    driver_headers: dict[str, str],
    ride_id: int,
) -> None:
    # Selection now assigns the ride; this helper is unused by post-accept tests.
    assert driver_client.put(
        f"/rides/{ride_id}/accept",
        headers=driver_headers,
    ).status_code == 200


def _arrive(
    driver_client: TestClient,
    driver_headers: dict[str, str],
    ride_id: int,
):
    return driver_client.put(
        f"/rides/{ride_id}/arrive",
        headers=driver_headers,
    )


def _driver_arrived(
    driver_client: TestClient,
    driver_headers: dict[str, str],
    ride_id: int,
):
    return driver_client.put(
        f"/rides/{ride_id}/driver-arrived",
        headers=driver_headers,
    )


def _start(
    driver_client: TestClient,
    driver_headers: dict[str, str],
    ride_id: int,
):
    return driver_client.put(
        f"/rides/{ride_id}/start",
        headers=driver_headers,
    )


def _complete(
    driver_client: TestClient,
    driver_headers: dict[str, str],
    ride_id: int,
):
    return driver_client.put(
        f"/rides/{ride_id}/complete",
        headers=driver_headers,
    )


def _advance_to_accepted(
    passenger_client: TestClient,
    passenger_headers: dict[str, str],
    driver_client: TestClient,
    driver_headers: dict[str, str],
    driver_id: int,
) -> int:
    payload = _create_assigned_ride(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        expected_driver_id=driver_id,
    )
    return payload["id"]


def _advance_to_driver_arriving(
    passenger_client: TestClient,
    passenger_headers: dict[str, str],
    driver_client: TestClient,
    driver_headers: dict[str, str],
    driver_id: int,
) -> int:
    ride_id = _advance_to_accepted(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        driver_id,
    )
    assert _arrive(driver_client, driver_headers, ride_id).status_code == 200
    return ride_id


def _advance_to_driver_arrived(
    passenger_client: TestClient,
    passenger_headers: dict[str, str],
    driver_client: TestClient,
    driver_headers: dict[str, str],
    driver_id: int,
) -> int:
    ride_id = _advance_to_driver_arriving(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        driver_id,
    )
    assert _driver_arrived(driver_client, driver_headers, ride_id).status_code == 200
    return ride_id


def _advance_to_in_progress(
    passenger_client: TestClient,
    passenger_headers: dict[str, str],
    driver_client: TestClient,
    driver_headers: dict[str, str],
    driver_id: int,
) -> int:
    ride_id = _advance_to_driver_arrived(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        driver_id,
    )
    assert _start(driver_client, driver_headers, ride_id).status_code == 200
    return ride_id


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


def _release_blocker_after_waiters(
    session: Session,
    start_barrier: threading.Barrier,
    *,
    minimum: int = 1,
) -> None:
    start_barrier.wait()
    try:
        _wait_for_lock_waiters(session, minimum=minimum)
    except TimeoutError:
        pass
    session.rollback()


@pytest.fixture
def second_driver_user(db_session: Session) -> User:
    user = User(
        full_name="Phase37 Driver B",
        phone_number="+15550003702",
        email="phase37.driver.b@test.nexo",
        password=hash_password("TestDriverBPhase37!"),
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


# ---------------------------------------------------------------------------
# Serial + duplicate lifecycle
# ---------------------------------------------------------------------------


def test_serial_arrive_succeeds(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]

    ride_id = _advance_to_accepted(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        driver.id,
    )

    response = _arrive(driver_client, driver_headers, ride_id)
    assert response.status_code == 200
    assert response.json()["status"] == RideStatus.DRIVER_ARRIVING

    db_session.expire_all()
    assert db_session.get(RideRequest, ride_id).status == RideStatus.DRIVER_ARRIVING


def test_duplicate_arrive_fails(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]

    ride_id = _advance_to_accepted(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        driver.id,
    )
    assert _arrive(driver_client, driver_headers, ride_id).status_code == 200

    second = _arrive(driver_client, driver_headers, ride_id)
    assert second.status_code == 400
    assert second.json()["detail"] == "Ride is not in the accepted state."

    db_session.expire_all()
    assert db_session.get(RideRequest, ride_id).status == RideStatus.DRIVER_ARRIVING


def test_serial_driver_arrived_succeeds(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]

    ride_id = _advance_to_driver_arriving(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        driver.id,
    )

    response = _driver_arrived(driver_client, driver_headers, ride_id)
    assert response.status_code == 200
    assert response.json()["status"] == RideStatus.DRIVER_ARRIVED

    db_session.expire_all()
    assert db_session.get(RideRequest, ride_id).status == RideStatus.DRIVER_ARRIVED


def test_duplicate_driver_arrived_fails(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]

    ride_id = _advance_to_driver_arriving(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        driver.id,
    )
    assert _driver_arrived(driver_client, driver_headers, ride_id).status_code == 200

    second = _driver_arrived(driver_client, driver_headers, ride_id)
    assert second.status_code == 400
    assert second.json()["detail"] == "Ride is not in the driver-arriving state."

    db_session.expire_all()
    assert db_session.get(RideRequest, ride_id).status == RideStatus.DRIVER_ARRIVED


def test_start_from_driver_arriving_succeeds(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]

    ride_id = _advance_to_driver_arriving(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        driver.id,
    )

    response = _start(driver_client, driver_headers, ride_id)
    assert response.status_code == 200
    assert response.json()["status"] == RideStatus.IN_PROGRESS

    db_session.expire_all()
    assert db_session.get(RideRequest, ride_id).status == RideStatus.IN_PROGRESS


def test_start_from_driver_arrived_succeeds(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]

    ride_id = _advance_to_driver_arrived(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        driver.id,
    )

    response = _start(driver_client, driver_headers, ride_id)
    assert response.status_code == 200
    assert response.json()["status"] == RideStatus.IN_PROGRESS

    db_session.expire_all()
    assert db_session.get(RideRequest, ride_id).status == RideStatus.IN_PROGRESS


def test_duplicate_start_fails(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]

    ride_id = _advance_to_driver_arriving(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        driver.id,
    )
    assert _start(driver_client, driver_headers, ride_id).status_code == 200

    second = _start(driver_client, driver_headers, ride_id)
    assert second.status_code == 400
    assert second.json()["detail"] == "Ride is not ready to start."

    db_session.expire_all()
    assert db_session.get(RideRequest, ride_id).status == RideStatus.IN_PROGRESS


def test_serial_complete_succeeds(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]

    ride_id = _advance_to_in_progress(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        driver.id,
    )

    response = _complete(driver_client, driver_headers, ride_id)
    assert response.status_code == 200
    assert response.json()["status"] == RideStatus.COMPLETED

    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride.status == RideStatus.COMPLETED
    assert db_session.get(User, driver.id).availability_status == "available"


def test_duplicate_complete_fails(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]

    ride_id = _advance_to_in_progress(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        driver.id,
    )
    assert _complete(driver_client, driver_headers, ride_id).status_code == 200

    second = _complete(driver_client, driver_headers, ride_id)
    assert second.status_code == 400
    assert second.json()["detail"] == "Ride is not currently in progress."

    db_session.expire_all()
    assert db_session.get(RideRequest, ride_id).status == RideStatus.COMPLETED
    assert db_session.get(User, driver.id).availability_status == "available"


# ---------------------------------------------------------------------------
# Critical concurrency: start vs driver_arrived
# ---------------------------------------------------------------------------


def test_start_then_driver_arrived_cannot_regress(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    """Prove IN_PROGRESS cannot be overwritten by driver_arrived."""
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]

    ride_id = _advance_to_driver_arriving(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        driver.id,
    )

    start_response = _start(driver_client, driver_headers, ride_id)
    assert start_response.status_code == 200
    assert start_response.json()["status"] == RideStatus.IN_PROGRESS

    arrived_response = _driver_arrived(driver_client, driver_headers, ride_id)
    assert arrived_response.status_code == 400
    assert arrived_response.json()["detail"] == (
        "Ride is not in the driver-arriving state."
    )

    db_session.expire_all()
    assert db_session.get(RideRequest, ride_id).status == RideStatus.IN_PROGRESS


def test_concurrent_start_vs_driver_arrived_no_regression(
    authenticated_passenger,
    authenticated_driver,
    db_session,
    test_session_factory: sessionmaker,
):
    """
    Concurrent start_ride vs driver_arrived from DRIVER_ARRIVING.

    Invariant: status never regresses IN_PROGRESS → DRIVER_ARRIVED.
    Final status is IN_PROGRESS or DRIVER_ARRIVED; if start wins the
    DRIVER_ARRIVING claim, arrived must lose.
    """
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]

    ride_id = _advance_to_driver_arriving(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        driver.id,
    )

    start_barrier = threading.Barrier(3)
    outcomes: dict[str, Any] = {
        "start": {"ok": False, "error": None},
        "arrived": {"ok": False, "error": None},
    }
    outcomes_lock = threading.Lock()

    def _blocker() -> None:
        session = test_session_factory()
        try:
            (
                session.query(RideRequest)
                .filter(RideRequest.id == ride_id)
                .with_for_update()
                .one()
            )
            _release_blocker_after_waiters(session, start_barrier)
        finally:
            session.close()

    def _worker(label: str, action) -> None:
        session = test_session_factory()
        try:
            user = session.get(User, driver.id)
            assert user is not None
            start_barrier.wait()
            try:
                action(db=session, ride_id=ride_id, current_user=user)
                with outcomes_lock:
                    outcomes[label]["ok"] = True
            except Exception as exc:  # noqa: BLE001
                with outcomes_lock:
                    outcomes[label]["error"] = exc
                session.rollback()
        finally:
            session.close()

    threads = [
        threading.Thread(target=_blocker, name="start-arrived-blocker"),
        threading.Thread(
            target=_worker,
            args=("start", RideService.start_ride),
            name="start-worker",
        ),
        threading.Thread(
            target=_worker,
            args=("arrived", RideService.driver_arrived),
            name="arrived-worker",
        ),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
        assert not thread.is_alive(), f"Thread {thread.name} did not finish"

    assert outcomes["start"]["ok"] or outcomes["arrived"]["ok"], outcomes

    db_session.expire_all()
    final_status = db_session.get(RideRequest, ride_id).status
    assert final_status in (
        RideStatus.IN_PROGRESS,
        RideStatus.DRIVER_ARRIVED,
    )

    # Critical: start success must never leave the ride as DRIVER_ARRIVED
    if outcomes["start"]["ok"]:
        assert final_status == RideStatus.IN_PROGRESS
    if final_status == RideStatus.DRIVER_ARRIVED:
        assert outcomes["arrived"]["ok"]
        assert not outcomes["start"]["ok"]

    # Losing driver_arrived must surface the existing HTTP error
    if not outcomes["arrived"]["ok"]:
        err = outcomes["arrived"]["error"]
        assert isinstance(err, HTTPException)
        assert err.status_code == 400
        assert err.detail == "Ride is not in the driver-arriving state."


def test_concurrent_duplicate_arrive_one_winner(
    authenticated_passenger,
    authenticated_driver,
    db_session,
    test_session_factory: sessionmaker,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]

    ride_id = _advance_to_accepted(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        driver.id,
    )

    start_barrier = threading.Barrier(3)
    outcomes: dict[str, Any] = {
        "a": {"ok": False, "error": None},
        "b": {"ok": False, "error": None},
    }
    outcomes_lock = threading.Lock()

    def _blocker() -> None:
        session = test_session_factory()
        try:
            (
                session.query(RideRequest)
                .filter(RideRequest.id == ride_id)
                .with_for_update()
                .one()
            )
            _release_blocker_after_waiters(session, start_barrier)
        finally:
            session.close()

    def _worker(label: str) -> None:
        session = test_session_factory()
        try:
            user = session.get(User, driver.id)
            assert user is not None
            start_barrier.wait()
            try:
                RideService.arrive_at_pickup(
                    db=session,
                    ride_id=ride_id,
                    current_user=user,
                )
                with outcomes_lock:
                    outcomes[label]["ok"] = True
            except Exception as exc:  # noqa: BLE001
                with outcomes_lock:
                    outcomes[label]["error"] = exc
                session.rollback()
        finally:
            session.close()

    threads = [
        threading.Thread(target=_blocker, name="arrive-arrive-blocker"),
        threading.Thread(target=_worker, args=("a",), name="arrive-a"),
        threading.Thread(target=_worker, args=("b",), name="arrive-b"),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
        assert not thread.is_alive(), f"Thread {thread.name} did not finish"

    wins = int(outcomes["a"]["ok"]) + int(outcomes["b"]["ok"])
    assert wins == 1, outcomes

    loser = "b" if outcomes["a"]["ok"] else "a"
    err = outcomes[loser]["error"]
    assert isinstance(err, HTTPException)
    assert err.status_code == 400
    assert err.detail == "Ride is not in the accepted state."

    db_session.expire_all()
    assert db_session.get(RideRequest, ride_id).status == RideStatus.DRIVER_ARRIVING


def test_concurrent_duplicate_complete_one_winner(
    authenticated_passenger,
    authenticated_driver,
    db_session,
    test_session_factory: sessionmaker,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]

    ride_id = _advance_to_in_progress(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        driver.id,
    )

    start_barrier = threading.Barrier(3)
    outcomes: dict[str, Any] = {
        "a": {"ok": False, "error": None},
        "b": {"ok": False, "error": None},
    }
    outcomes_lock = threading.Lock()

    def _blocker() -> None:
        session = test_session_factory()
        try:
            (
                session.query(RideRequest)
                .filter(RideRequest.id == ride_id)
                .with_for_update()
                .one()
            )
            _release_blocker_after_waiters(session, start_barrier)
        finally:
            session.close()

    def _worker(label: str) -> None:
        session = test_session_factory()
        try:
            user = session.get(User, driver.id)
            assert user is not None
            start_barrier.wait()
            try:
                RideService.complete_ride(
                    db=session,
                    ride_id=ride_id,
                    current_user=user,
                )
                with outcomes_lock:
                    outcomes[label]["ok"] = True
            except Exception as exc:  # noqa: BLE001
                with outcomes_lock:
                    outcomes[label]["error"] = exc
                session.rollback()
        finally:
            session.close()

    threads = [
        threading.Thread(target=_blocker, name="complete-complete-blocker"),
        threading.Thread(target=_worker, args=("a",), name="complete-a"),
        threading.Thread(target=_worker, args=("b",), name="complete-b"),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
        assert not thread.is_alive(), f"Thread {thread.name} did not finish"

    wins = int(outcomes["a"]["ok"]) + int(outcomes["b"]["ok"])
    assert wins == 1, outcomes

    loser = "b" if outcomes["a"]["ok"] else "a"
    err = outcomes[loser]["error"]
    assert isinstance(err, HTTPException)
    assert err.status_code == 400
    assert err.detail == "Ride is not currently in progress."

    db_session.expire_all()
    assert db_session.get(RideRequest, ride_id).status == RideStatus.COMPLETED
    assert db_session.get(User, driver.id).availability_status == "available"


# ---------------------------------------------------------------------------
# Notifications + authorization + terminal protection
# ---------------------------------------------------------------------------


def test_failed_cas_produces_no_notification(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]

    ride_id = _advance_to_accepted(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        driver.id,
    )
    assert _arrive(driver_client, driver_headers, ride_id).status_code == 200

    with patch(
        "app.services.ride_service.NotificationService.notify_passenger"
    ) as notify_mock:
        second = _arrive(driver_client, driver_headers, ride_id)
        assert second.status_code == 400
        notify_mock.assert_not_called()

    # Also cover start-after-start and complete-after-complete
    assert _start(driver_client, driver_headers, ride_id).status_code == 200
    with patch(
        "app.services.ride_service.NotificationService.notify_passenger"
    ) as notify_mock:
        assert _start(driver_client, driver_headers, ride_id).status_code == 400
        notify_mock.assert_not_called()

    assert _complete(driver_client, driver_headers, ride_id).status_code == 200
    with patch(
        "app.services.ride_service.NotificationService.notify_passenger"
    ) as notify_mock:
        assert _complete(driver_client, driver_headers, ride_id).status_code == 400
        notify_mock.assert_not_called()

    db_session.expire_all()
    assert db_session.get(RideRequest, ride_id).status == RideStatus.COMPLETED


def test_wrong_driver_remains_rejected(
    authenticated_passenger,
    authenticated_driver,
    authenticated_second_driver,
    db_session,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]
    other_client = authenticated_second_driver["client"]
    other_headers = authenticated_second_driver["headers"]

    ride_id = _advance_to_accepted(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        driver.id,
    )

    for path in ("arrive", "driver-arrived", "start", "complete"):
        response = other_client.put(
            f"/rides/{ride_id}/{path}",
            headers=other_headers,
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "You are not assigned to this ride."

    db_session.expire_all()
    assert db_session.get(RideRequest, ride_id).status == RideStatus.ACCEPTED


def test_terminal_completed_ride_remains_protected(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]

    ride_id = _advance_to_in_progress(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        driver.id,
    )
    assert _complete(driver_client, driver_headers, ride_id).status_code == 200

    arrive = _arrive(driver_client, driver_headers, ride_id)
    assert arrive.status_code == 400
    assert arrive.json()["detail"] == "Ride is not in the accepted state."

    arrived = _driver_arrived(driver_client, driver_headers, ride_id)
    assert arrived.status_code == 400
    assert arrived.json()["detail"] == "Ride is not in the driver-arriving state."

    start = _start(driver_client, driver_headers, ride_id)
    assert start.status_code == 400
    assert start.json()["detail"] == "Ride is not ready to start."

    complete = _complete(driver_client, driver_headers, ride_id)
    assert complete.status_code == 400
    assert complete.json()["detail"] == "Ride is not currently in progress."

    db_session.expire_all()
    assert db_session.get(RideRequest, ride_id).status == RideStatus.COMPLETED
