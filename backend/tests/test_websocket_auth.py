"""
Phase 3.8: WebSocket handshake authentication + identity binding.

- /ws/driver/{driver_id} requires a driver JWT whose user id matches the path.
- /ws/passenger/{passenger_id} requires a passenger JWT whose profile id matches.
- Failed handshakes must not register with ConnectionManager.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect

from app.models.passenger import Passenger
from app.models.user import User
from app.services.notification_service import NotificationService
from app.utils.jwt import create_access_token
from app.utils.security import hash_password
from app.websocket.manager import manager


def _token_for(user: User) -> str:
    return create_access_token(
        data={
            "sub": str(user.id),
            "email": user.email,
            "role": user.role,
        }
    )


def _push_json(websocket: Any, send_coro: Any) -> dict[str, Any]:
    """
    Deliver one message on the app event loop, then receive it.

    Avoids depending on NotificationService scheduling from sync HTTP handlers,
    which can race/hang under TestClient after many lifespan cycles.
    """
    loop = NotificationService._event_loop
    assert loop is not None, "NotificationService event loop was not bound"
    assert loop.is_running(), "NotificationService event loop is not running"

    future = asyncio.run_coroutine_threadsafe(send_coro, loop)
    future.result(timeout=5)
    return websocket.receive_json()


@pytest.fixture(autouse=True)
def _clear_websocket_manager() -> None:
    manager.driver_connections.clear()
    manager.passenger_connections.clear()
    yield
    manager.driver_connections.clear()
    manager.passenger_connections.clear()


@pytest.fixture
def second_driver_user(db_session: Session) -> User:
    user = User(
        full_name="WS Test Driver B",
        phone_number="+15550003802",
        email="ws.driver.b@test.nexo",
        password=hash_password("TestDriverBWs123!"),
        role="driver",
        verification_status="approved",
        availability_status="available",
        current_latitude=-26.2041,
        current_longitude=28.0473,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def second_passenger(
    db_session: Session,
) -> dict[str, Any]:
    user = User(
        full_name="WS Test Passenger B",
        phone_number="+15550003803",
        email="ws.passenger.b@test.nexo",
        password=hash_password("TestPassengerBWs123!"),
        role="passenger",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    profile = Passenger(
        user_id=user.id,
        first_name="WS",
        last_name="PassengerB",
        phone="+15550003804",
        email="ws.passenger.b.profile@test.nexo",
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)
    return {"user": user, "passenger": profile}


def _expect_rejected(client: TestClient, path: str, **kwargs: Any) -> None:
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(path, **kwargs):
            pass
    assert exc_info.value.code == 1008


# ---------------------------------------------------------------------------
# Driver channel
# ---------------------------------------------------------------------------


def test_driver_ws_rejects_missing_token(authenticated_driver):
    client = authenticated_driver["client"]
    driver = authenticated_driver["user"]

    _expect_rejected(client, f"/ws/driver/{driver.id}")
    assert driver.id not in manager.driver_connections


def test_driver_ws_rejects_invalid_token(authenticated_driver):
    client = authenticated_driver["client"]
    driver = authenticated_driver["user"]

    _expect_rejected(
        client,
        f"/ws/driver/{driver.id}?token=not-a-valid-jwt",
    )
    assert driver.id not in manager.driver_connections


def test_driver_ws_rejects_passenger_token(authenticated_driver, authenticated_passenger):
    client = authenticated_driver["client"]
    driver = authenticated_driver["user"]
    passenger_token = _token_for(authenticated_passenger["user"])

    _expect_rejected(
        client,
        f"/ws/driver/{driver.id}?token={passenger_token}",
    )
    assert driver.id not in manager.driver_connections


def test_driver_ws_rejects_cross_driver_hijack(
    authenticated_driver,
    second_driver_user,
):
    client = authenticated_driver["client"]
    driver_a = authenticated_driver["user"]
    driver_b = second_driver_user
    token_a = _token_for(driver_a)

    _expect_rejected(
        client,
        f"/ws/driver/{driver_b.id}?token={token_a}",
    )
    assert driver_b.id not in manager.driver_connections
    assert driver_a.id not in manager.driver_connections


def test_driver_ws_accepts_matching_token_query(authenticated_driver):
    client = authenticated_driver["client"]
    driver = authenticated_driver["user"]
    token = _token_for(driver)

    with client.websocket_connect(
        f"/ws/driver/{driver.id}?token={token}"
    ) as websocket:
        message = websocket.receive_json()
        assert message["event"] == "connected"
        assert driver.id in manager.driver_connections


def test_driver_ws_accepts_matching_token_header(authenticated_driver):
    client = authenticated_driver["client"]
    driver = authenticated_driver["user"]
    token = _token_for(driver)

    with client.websocket_connect(
        f"/ws/driver/{driver.id}",
        headers={"Authorization": f"Bearer {token}"},
    ) as websocket:
        message = websocket.receive_json()
        assert message["event"] == "connected"
        assert driver.id in manager.driver_connections


def test_authorized_driver_receives_ride_offer(authenticated_driver):
    client = authenticated_driver["client"]
    driver = authenticated_driver["user"]
    token = _token_for(driver)

    with client.websocket_connect(
        f"/ws/driver/{driver.id}?token={token}"
    ) as websocket:
        assert websocket.receive_json()["event"] == "connected"
        assert driver.id in manager.driver_connections

        offer = _push_json(
            websocket,
            manager.send_to_driver(
                driver.id,
                {
                    "event": "ride_offer",
                    "ride_id": 42,
                    "pickup": "Sandton",
                    "destination": "OR Tambo",
                    "fare": 150.0,
                },
            ),
        )
        assert offer["event"] == "ride_offer"
        assert offer["ride_id"] == 42


# ---------------------------------------------------------------------------
# Passenger channel
# ---------------------------------------------------------------------------


def test_passenger_ws_rejects_missing_token(authenticated_passenger):
    client = authenticated_passenger["client"]
    passenger = authenticated_passenger["passenger"]

    _expect_rejected(client, f"/ws/passenger/{passenger.id}")
    assert passenger.id not in manager.passenger_connections


def test_passenger_ws_rejects_invalid_token(authenticated_passenger):
    client = authenticated_passenger["client"]
    passenger = authenticated_passenger["passenger"]

    _expect_rejected(
        client,
        f"/ws/passenger/{passenger.id}?token=not-a-valid-jwt",
    )
    assert passenger.id not in manager.passenger_connections


def test_passenger_ws_rejects_driver_token(authenticated_passenger, authenticated_driver):
    client = authenticated_passenger["client"]
    passenger = authenticated_passenger["passenger"]
    driver_token = _token_for(authenticated_driver["user"])

    _expect_rejected(
        client,
        f"/ws/passenger/{passenger.id}?token={driver_token}",
    )
    assert passenger.id not in manager.passenger_connections


def test_passenger_ws_rejects_cross_passenger_hijack(
    authenticated_passenger,
    second_passenger,
):
    client = authenticated_passenger["client"]
    passenger_a = authenticated_passenger["passenger"]
    passenger_b = second_passenger["passenger"]
    token_a = _token_for(authenticated_passenger["user"])

    _expect_rejected(
        client,
        f"/ws/passenger/{passenger_b.id}?token={token_a}",
    )
    assert passenger_b.id not in manager.passenger_connections
    assert passenger_a.id not in manager.passenger_connections


def test_passenger_ws_rejects_user_id_as_path_id(client: TestClient, db_session: Session):
    """Path must be passengers.id, not users.id (ids often diverge across tables)."""
    decoy = User(
        full_name="WS Decoy User",
        phone_number="+15550003810",
        email="ws.decoy@test.nexo",
        password=hash_password("TestDecoyWs123!"),
        role="passenger",
    )
    db_session.add(decoy)
    db_session.commit()

    user = User(
        full_name="WS Path-Id Passenger",
        phone_number="+15550003811",
        email="ws.path.passenger@test.nexo",
        password=hash_password("TestPathPassengerWs123!"),
        role="passenger",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    profile = Passenger(
        user_id=user.id,
        first_name="Path",
        last_name="Passenger",
        phone="+15550003812",
        email="ws.path.passenger.profile@test.nexo",
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)

    assert user.id != profile.id
    token = _token_for(user)

    _expect_rejected(
        client,
        f"/ws/passenger/{user.id}?token={token}",
    )
    assert user.id not in manager.passenger_connections

    with client.websocket_connect(
        f"/ws/passenger/{profile.id}?token={token}"
    ) as websocket:
        assert websocket.receive_json()["event"] == "connected"


def test_passenger_ws_accepts_matching_token_query(authenticated_passenger):
    client = authenticated_passenger["client"]
    passenger = authenticated_passenger["passenger"]
    token = _token_for(authenticated_passenger["user"])

    with client.websocket_connect(
        f"/ws/passenger/{passenger.id}?token={token}"
    ) as websocket:
        message = websocket.receive_json()
        assert message["event"] == "connected"
        assert passenger.id in manager.passenger_connections


def test_passenger_ws_accepts_matching_token_header(authenticated_passenger):
    client = authenticated_passenger["client"]
    passenger = authenticated_passenger["passenger"]
    token = _token_for(authenticated_passenger["user"])

    with client.websocket_connect(
        f"/ws/passenger/{passenger.id}",
        headers={"Authorization": f"Bearer {token}"},
    ) as websocket:
        message = websocket.receive_json()
        assert message["event"] == "connected"
        assert passenger.id in manager.passenger_connections


def test_authorized_passenger_receives_ride_accepted(authenticated_passenger):
    client = authenticated_passenger["client"]
    passenger = authenticated_passenger["passenger"]
    token = _token_for(authenticated_passenger["user"])

    with client.websocket_connect(
        f"/ws/passenger/{passenger.id}?token={token}"
    ) as websocket:
        assert websocket.receive_json()["event"] == "connected"
        assert passenger.id in manager.passenger_connections

        event = _push_json(
            websocket,
            manager.send_to_passenger(
                passenger.id,
                {
                    "event": "ride_accepted",
                    "ride_id": 7,
                    "driver_id": 2,
                    "message": "Your driver has accepted the ride.",
                },
            ),
        )
        assert event["event"] == "ride_accepted"
        assert event["ride_id"] == 7
        assert event["driver_id"] == 2


def test_unauthorized_passenger_socket_does_not_receive_events(
    authenticated_passenger,
    second_passenger,
):
    """Hijack attempt must fail; only the identity-bound socket is registered."""
    client = authenticated_passenger["client"]
    passenger = authenticated_passenger["passenger"]
    passenger_token = _token_for(authenticated_passenger["user"])
    hijacker_token = _token_for(second_passenger["user"])

    _expect_rejected(
        client,
        f"/ws/passenger/{passenger.id}?token={hijacker_token}",
    )
    assert passenger.id not in manager.passenger_connections

    with client.websocket_connect(
        f"/ws/passenger/{passenger.id}?token={passenger_token}"
    ) as websocket:
        assert websocket.receive_json()["event"] == "connected"
        assert passenger.id in manager.passenger_connections

        event = _push_json(
            websocket,
            manager.send_to_passenger(
                passenger.id,
                {
                    "event": "driver_location",
                    "driver_id": 2,
                    "latitude": -26.2,
                    "longitude": 28.0,
                },
            ),
        )
        assert event["event"] == "driver_location"
        assert event["driver_id"] == 2
