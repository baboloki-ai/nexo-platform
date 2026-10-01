"""
Phase 3.9: HTTP/debug surface security hardening.

Covers debug endpoint removal, user-directory lockdown, secret/JWT logging
removal, and driver-only access to GET /rides/available.
"""
from __future__ import annotations

import importlib
import io
import uuid
from contextlib import redirect_stdout
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.constants.ride_status import RideStatus
from app.models.passenger import Passenger
from app.models.ride_request import RideRequest
from app.models.user import User
from app.utils.jwt import create_access_token
from app.utils.security import hash_password


DEBUG_ENDPOINTS = (
    "/db-info",
    "/db-test",
    "/users-db",
    "/tables",
    "/list-db-tables",
)

SENSITIVE_RESPONSE_MARKERS = (
    "DATABASE_URL",
    "database_url",
    "SECRET_KEY",
    "postgresql://",
    "password",
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


def _assert_not_exposed(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code in (401, 403, 404, 405)
    body = response.text.lower()
    for marker in SENSITIVE_RESPONSE_MARKERS:
        assert marker.lower() not in body


# ---------------------------------------------------------------------------
# Debug / database endpoints
# ---------------------------------------------------------------------------


def test_unauthenticated_db_info_rejected_or_unavailable(client: TestClient):
    _assert_not_exposed(client, "/db-info")


def test_unauthenticated_users_db_rejected_or_unavailable(client: TestClient):
    _assert_not_exposed(client, "/users-db")


def test_unauthenticated_tables_rejected_or_unavailable(client: TestClient):
    _assert_not_exposed(client, "/tables")


def test_unauthenticated_list_db_tables_rejected_or_unavailable(
    client: TestClient,
):
    _assert_not_exposed(client, "/list-db-tables")


def test_sensitive_database_information_not_exposed(client: TestClient):
    for path in DEBUG_ENDPOINTS:
        response = client.get(path)
        assert response.status_code != 200
        body = response.text
        assert "DATABASE_URL" not in body
        assert "database_url" not in body
        assert "postgresql://" not in body.lower()
        # Removed endpoints must not leak table catalogs or user rows.
        if response.status_code == 404:
            assert "users" not in body or "Not Found" in body


# ---------------------------------------------------------------------------
# User directory
# ---------------------------------------------------------------------------


def test_unauthenticated_get_users_rejected(client: TestClient):
    response = client.get("/users/")
    assert response.status_code in (401, 403, 404, 405)
    if response.status_code == 200:
        raise AssertionError("Unauthenticated callers must not receive users.")


def test_authenticated_user_cannot_list_global_directory(
    client: TestClient,
    passenger_user: User,
    driver_user: User,
):
    headers = _auth_headers(passenger_user)
    response = client.get("/users/", headers=headers)
    assert response.status_code in (401, 403, 404, 405)

    if response.status_code == 200:
        raise AssertionError(
            "Authenticated non-admin users must not receive a global directory."
        )

    body = response.text.lower()
    assert driver_user.email.lower() not in body
    assert passenger_user.email.lower() not in body or response.status_code != 200


def test_registration_post_users_still_works(client: TestClient):
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "full_name": "Phase 39 Registrant",
        "phone_number": f"+1555399{suffix[:4]}",
        "email": f"phase39.{suffix}@test.nexo",
        "password": "SecurePass123!",
        "role": "passenger",
    }
    response = client.post("/users/", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == payload["email"]
    assert data["role"] == "passenger"
    assert "password" not in data


# ---------------------------------------------------------------------------
# Secret / token logging
# ---------------------------------------------------------------------------


def test_authentication_does_not_print_raw_jwt(
    client: TestClient,
    passenger_user: User,
    capsys: Any,
):
    headers = _auth_headers(passenger_user)
    token = headers["Authorization"].removeprefix("Bearer ")

    response = client.get("/users/me", headers=headers)
    assert response.status_code == 200

    captured = capsys.readouterr()
    combined = f"{captured.out}\n{captured.err}"
    assert token not in combined
    assert "Received Token:" not in combined
    assert "Decoded Payload:" not in combined


def test_secret_key_not_printed_during_config_startup():
    import app.config as config_module

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        importlib.reload(config_module)

    output = buffer.getvalue()
    secret = config_module.SECRET_KEY
    assert "SECRET_KEY:" not in output
    if secret:
        assert secret not in output


def test_authorization_header_or_token_not_printed(
    client: TestClient,
    passenger_user: User,
    capsys: Any,
):
    headers = _auth_headers(passenger_user)
    auth_header = headers["Authorization"]
    token = auth_header.removeprefix("Bearer ")

    response = client.get("/users/me", headers=headers)
    assert response.status_code == 200

    captured = capsys.readouterr()
    combined = f"{captured.out}\n{captured.err}"
    assert auth_header not in combined
    assert token not in combined
    assert "Bearer " not in combined


# ---------------------------------------------------------------------------
# GET /rides/available
# ---------------------------------------------------------------------------


def test_unauthenticated_available_rides_rejected(client: TestClient):
    response = client.get("/rides/available")
    assert response.status_code == 401


def test_passenger_available_rides_forbidden(
    client: TestClient,
    authenticated_passenger: dict[str, Any],
):
    response = client.get(
        "/rides/available",
        headers=authenticated_passenger["headers"],
    )
    assert response.status_code == 403


def test_driver_available_rides_allowed_and_contract_intact(
    client: TestClient,
    db_session: Session,
    authenticated_driver: dict[str, Any],
    passenger_profile: Passenger,
):
    pending = RideRequest(
        passenger_id=passenger_profile.id,
        pickup_location="Security Test Pickup",
        pickup_latitude=-26.2041,
        pickup_longitude=28.0473,
        destination="Security Test Destination",
        destination_latitude=-26.1330,
        destination_longitude=28.2420,
        proposed_fare=120.0,
        status=RideStatus.PENDING,
    )
    db_session.add(pending)
    db_session.commit()
    db_session.refresh(pending)

    response = client.get(
        "/rides/available",
        headers=authenticated_driver["headers"],
    )
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) >= 1

    match = next(item for item in payload if item["id"] == pending.id)
    assert match["status"] == RideStatus.PENDING
    assert match["pickup_location"] == "Security Test Pickup"
    assert match["pickup_latitude"] == -26.2041
    assert match["pickup_longitude"] == 28.0473
    assert match["destination"] == "Security Test Destination"
    assert match["proposed_fare"] == 120.0
    assert "passenger_id" in match
    assert "requested_at" in match
