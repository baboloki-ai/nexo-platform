"""
Phase 1.7: passenger profile CRUD and ownership tests.

Covers only behaviors currently enforced by passenger endpoints.
"""
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.passenger import Passenger
from app.models.user import User
from app.utils.jwt import create_access_token
from app.utils.security import hash_password

PASSENGER_CREATE_PAYLOAD = {
    "first_name": "Test",
    "last_name": "Passenger",
    "phone": "70000001",
    "email": "passenger@example.com",
}

PASSENGER_UPDATE_PAYLOAD = {
    "first_name": "Updated",
    "last_name": "Passenger",
    "phone": "70000002",
    "email": "updated@example.com",
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


@pytest.fixture
def authenticated_user_without_passenger_profile(
    client: TestClient,
    passenger_user: User,
) -> dict[str, Any]:
    """Authenticated passenger role user with no Passenger row yet."""
    return {
        "client": client,
        "user": passenger_user,
        "headers": _auth_headers(passenger_user),
    }


@pytest.fixture
def second_passenger_user(db_session: Session) -> User:
    user = User(
        full_name="Phase17 Passenger B",
        phone_number="+15550001701",
        email="phase17.passenger.b@test.nexo",
        password=hash_password("TestPassengerBPhase17!"),
        role="passenger",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def second_passenger_profile(
    db_session: Session,
    second_passenger_user: User,
) -> Passenger:
    profile = Passenger(
        user_id=second_passenger_user.id,
        first_name="Other",
        last_name="Passenger",
        phone="70000999",
        email="other.passenger@example.com",
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)
    return profile


def test_create_passenger_profile(
    authenticated_user_without_passenger_profile,
    db_session,
):
    client = authenticated_user_without_passenger_profile["client"]
    headers = authenticated_user_without_passenger_profile["headers"]
    user = authenticated_user_without_passenger_profile["user"]

    response = client.post(
        "/passengers/",
        headers=headers,
        json=PASSENGER_CREATE_PAYLOAD,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["user_id"] == user.id
    assert payload["first_name"] == PASSENGER_CREATE_PAYLOAD["first_name"]
    assert payload["last_name"] == PASSENGER_CREATE_PAYLOAD["last_name"]
    assert payload["phone"] == PASSENGER_CREATE_PAYLOAD["phone"]
    assert payload["email"] == PASSENGER_CREATE_PAYLOAD["email"]
    assert "id" in payload

    db_session.expire_all()
    row = db_session.get(Passenger, payload["id"])
    assert row is not None
    assert row.user_id == user.id
    assert row.first_name == PASSENGER_CREATE_PAYLOAD["first_name"]
    assert row.last_name == PASSENGER_CREATE_PAYLOAD["last_name"]
    assert row.phone == PASSENGER_CREATE_PAYLOAD["phone"]
    assert row.email == PASSENGER_CREATE_PAYLOAD["email"]


def test_get_own_passenger_profile(authenticated_passenger):
    client = authenticated_passenger["client"]
    headers = authenticated_passenger["headers"]
    passenger = authenticated_passenger["passenger"]
    user = authenticated_passenger["user"]

    my_response = client.get("/passengers/my", headers=headers)
    assert my_response.status_code == 200
    my_payload = my_response.json()
    assert isinstance(my_payload, list)
    assert any(item["id"] == passenger.id for item in my_payload)

    by_id_response = client.get(
        f"/passengers/{passenger.id}",
        headers=headers,
    )
    assert by_id_response.status_code == 200
    by_id_payload = by_id_response.json()
    assert by_id_payload["id"] == passenger.id
    assert by_id_payload["user_id"] == user.id


def test_update_own_passenger_profile(authenticated_passenger, db_session):
    client = authenticated_passenger["client"]
    headers = authenticated_passenger["headers"]
    passenger = authenticated_passenger["passenger"]

    response = client.put(
        f"/passengers/{passenger.id}",
        headers=headers,
        json=PASSENGER_UPDATE_PAYLOAD,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["first_name"] == PASSENGER_UPDATE_PAYLOAD["first_name"]
    assert payload["last_name"] == PASSENGER_UPDATE_PAYLOAD["last_name"]
    assert payload["phone"] == PASSENGER_UPDATE_PAYLOAD["phone"]
    assert payload["email"] == PASSENGER_UPDATE_PAYLOAD["email"]

    db_session.expire_all()
    row = db_session.get(Passenger, passenger.id)
    assert row is not None
    assert row.first_name == PASSENGER_UPDATE_PAYLOAD["first_name"]
    assert row.last_name == PASSENGER_UPDATE_PAYLOAD["last_name"]
    assert row.phone == PASSENGER_UPDATE_PAYLOAD["phone"]
    assert row.email == PASSENGER_UPDATE_PAYLOAD["email"]


def test_delete_own_passenger_profile(authenticated_passenger, db_session):
    client = authenticated_passenger["client"]
    headers = authenticated_passenger["headers"]
    passenger = authenticated_passenger["passenger"]
    passenger_id = passenger.id

    response = client.delete(
        f"/passengers/{passenger_id}",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Passenger deleted successfully"

    db_session.expire_all()
    assert db_session.get(Passenger, passenger_id) is None


def test_cannot_retrieve_another_users_passenger_profile(
    authenticated_passenger,
    second_passenger_profile,
):
    client = authenticated_passenger["client"]
    headers = authenticated_passenger["headers"]

    response = client.get(
        f"/passengers/{second_passenger_profile.id}",
        headers=headers,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Passenger not found"


def test_cannot_update_another_users_passenger_profile(
    authenticated_passenger,
    second_passenger_profile,
    db_session,
):
    client = authenticated_passenger["client"]
    headers = authenticated_passenger["headers"]
    other = second_passenger_profile
    before = {
        "first_name": other.first_name,
        "last_name": other.last_name,
        "phone": other.phone,
        "email": other.email,
    }

    response = client.put(
        f"/passengers/{other.id}",
        headers=headers,
        json=PASSENGER_UPDATE_PAYLOAD,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Passenger not found"

    db_session.expire_all()
    row = db_session.get(Passenger, other.id)
    assert row is not None
    assert row.first_name == before["first_name"]
    assert row.last_name == before["last_name"]
    assert row.phone == before["phone"]
    assert row.email == before["email"]


def test_cannot_delete_another_users_passenger_profile(
    authenticated_passenger,
    second_passenger_profile,
    db_session,
):
    client = authenticated_passenger["client"]
    headers = authenticated_passenger["headers"]
    other_id = second_passenger_profile.id

    response = client.delete(
        f"/passengers/{other_id}",
        headers=headers,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Passenger not found"

    db_session.expire_all()
    assert db_session.get(Passenger, other_id) is not None


def test_unauthenticated_passenger_endpoint(client: TestClient):
    response = client.get("/passengers/my")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_missing_required_passenger_fields(
    authenticated_user_without_passenger_profile,
):
    client = authenticated_user_without_passenger_profile["client"]
    headers = authenticated_user_without_passenger_profile["headers"]

    incomplete = {
        "first_name": "Test",
        "last_name": "Passenger",
        "email": "passenger@example.com",
    }
    response = client.post(
        "/passengers/",
        headers=headers,
        json=incomplete,
    )
    assert response.status_code == 422


def test_duplicate_passenger_profile_currently_allowed(
    authenticated_passenger,
    db_session,
):
    """Current behavior: a second Passenger row for the same user is allowed."""
    client = authenticated_passenger["client"]
    headers = authenticated_passenger["headers"]
    user = authenticated_passenger["user"]
    existing = authenticated_passenger["passenger"]

    response = client.post(
        "/passengers/",
        headers=headers,
        json={
            "first_name": "Second",
            "last_name": "Profile",
            "phone": "70000003",
            "email": "second.passenger@example.com",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["user_id"] == user.id
    assert payload["id"] != existing.id

    db_session.expire_all()
    count = (
        db_session.query(Passenger)
        .filter(Passenger.user_id == user.id)
        .count()
    )
    assert count == 2
