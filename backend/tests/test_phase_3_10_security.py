"""
Phase 3.10: Remove unauthenticated GET /db-test debug endpoint.

Confirms the route is gone, database error text is not exposed through it,
and the existing health endpoint remains functional.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.models.user import User
from app.utils.jwt import create_access_token


DB_ERROR_MARKERS = (
    "DATABASE_URL",
    "database_url",
    "SECRET_KEY",
    "postgresql://",
    "password",
    "OperationalError",
    "sqlalchemy",
    "psycopg",
    "connection refused",
    "could not connect",
    "server closed the connection",
    "FATAL:",
    "traceback",
    "Connected successfully!",
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


def _assert_db_test_unavailable(response) -> None:
    assert response.status_code in (401, 403, 404, 405)
    assert response.status_code != 200
    body = response.text
    body_lower = body.lower()
    for marker in DB_ERROR_MARKERS:
        assert marker.lower() not in body_lower
    assert "Connected successfully!" not in body
    payload = response.json()
    assert "error" not in payload
    assert "database" not in payload


def test_unauthenticated_db_test_unavailable(client: TestClient):
    _assert_db_test_unavailable(client.get("/db-test"))


def test_authenticated_db_test_unavailable(
    client: TestClient,
    passenger_user: User,
    driver_user: User,
):
    _assert_db_test_unavailable(
        client.get("/db-test", headers=_auth_headers(passenger_user))
    )
    _assert_db_test_unavailable(
        client.get("/db-test", headers=_auth_headers(driver_user))
    )


def test_db_test_does_not_expose_database_error_text(client: TestClient):
    response = client.get("/db-test")
    _assert_db_test_unavailable(response)
    if response.status_code == 404:
        assert response.json() == {"detail": "Not Found"}


def test_health_endpoint_remains_functional(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "OK"}
