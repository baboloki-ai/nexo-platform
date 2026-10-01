"""
L1: driver operations, identity, verification, history, and security.
"""
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.ride_request import RideRequest
from app.models.user import User
from app.models.vehicle import Vehicle
from app.utils.jwt import create_access_token
from app.utils.security import hash_password

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

VEHICLE_PAYLOAD = {
    "make": "Toyota",
    "model": "Corolla",
    "year": 2021,
    "color": "White",
    "registration_number": "B123NEX",
    "vehicle_type": "sedan",
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
    verification_status: str | None,
    availability_status: str = "available",
    current_latitude: float | None = -26.2041,
    current_longitude: float | None = 28.0473,
) -> User:
    user = User(
        full_name=full_name,
        phone_number=phone_number,
        email=email,
        password=hash_password("TestDriverL1!"),
        role="driver",
        verification_status=verification_status,
        availability_status=availability_status,
        current_latitude=current_latitude,
        current_longitude=current_longitude,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _add_vehicle(
    db_session: Session,
    driver_id: int,
    plate: str,
    verification_status: str = "pending",
) -> Vehicle:
    vehicle = Vehicle(
        driver_id=driver_id,
        make="Toyota",
        model="Corolla",
        year=2021,
        color="White",
        registration_number=plate,
        vehicle_type="sedan",
        verification_status=verification_status,
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)
    return vehicle


def _prepare_driver_online(
    driver_client: TestClient,
    driver_headers: dict[str, str],
) -> None:
    go_online = driver_client.put("/drivers/go-online", headers=driver_headers)
    assert go_online.status_code == 200
    location = driver_client.put(
        "/drivers/location",
        headers=driver_headers,
        json=DRIVER_LOCATION_PAYLOAD,
    )
    assert location.status_code == 200


def _complete_assigned_ride(
    passenger_client: TestClient,
    passenger_headers: dict[str, str],
    driver_client: TestClient,
    driver_headers: dict[str, str],
    expected_driver_id: int,
) -> dict[str, Any]:
    from tests.ride_flow import advance_to_accepted

    selected = advance_to_accepted(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        expected_driver_id,
    )
    ride_id = selected["id"]
    assert driver_client.put(
        f"/rides/{ride_id}/arrive",
        headers=driver_headers,
    ).status_code == 200
    assert driver_client.put(
        f"/rides/{ride_id}/driver-arrived",
        headers=driver_headers,
    ).status_code == 200
    assert driver_client.put(
        f"/rides/{ride_id}/start",
        headers=driver_headers,
    ).status_code == 200
    complete = driver_client.put(
        f"/rides/{ride_id}/complete",
        headers=driver_headers,
    )
    assert complete.status_code == 200
    return complete.json()


# ---------------------------------------------------------------------------
# Registration / profile
# ---------------------------------------------------------------------------


def test_new_driver_defaults_to_pending(client: TestClient):
    response = client.post(
        "/users/",
        json={
            "full_name": "Pending Driver",
            "phone_number": "+15550004101",
            "email": "pending.driver.l1@test.nexo",
            "password": "SecurePass123!",
            "role": "driver",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["verification_status"] == "pending"
    assert payload["role"] == "driver"
    assert "password" not in payload


def test_driver_profile_uses_user_fields(
    authenticated_driver,
    db_session,
):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]
    existing = (
        db_session.query(Vehicle)
        .filter(Vehicle.driver_id == driver.id)
        .all()
    )
    for row in existing:
        db_session.delete(row)
    db_session.commit()
    _add_vehicle(db_session, driver.id, "B111L1A")

    response = client.get("/drivers/me", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == driver.id
    assert payload["display_name"] == driver.full_name
    assert payload["phone_number"] == driver.phone_number
    assert payload["verification_status"] == "approved"
    assert payload["vehicle"]["registration_number"] == "B111L1A"
    assert payload["vehicle"]["color"] == "White"


def test_driver_can_update_own_profile(authenticated_driver, db_session):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]

    response = client.patch(
        "/drivers/me",
        headers=headers,
        json={
            "display_name": "Kabelo Molefe",
            "phone_number": "+26771100001",
            "profile_photo_url": "https://cdn.example/drivers/kabelo.jpg",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["display_name"] == "Kabelo Molefe"
    assert payload["phone_number"] == "+26771100001"
    assert payload["profile_photo_url"].endswith("kabelo.jpg")
    assert payload["verification_status"] == "approved"

    db_session.expire_all()
    row = db_session.get(User, driver.id)
    assert row.full_name == "Kabelo Molefe"
    assert row.phone_number == "+26771100001"


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------


def test_passenger_cannot_view_driver_profile(authenticated_passenger):
    client = authenticated_passenger["client"]
    headers = authenticated_passenger["headers"]
    response = client.get("/drivers/me", headers=headers)
    assert response.status_code == 403


def test_passenger_cannot_modify_driver_profile(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    driver = authenticated_driver["user"]
    before_name = driver.full_name

    response = passenger_client.patch(
        "/drivers/me",
        headers=passenger_headers,
        json={"display_name": "Hijacked Name"},
    )
    assert response.status_code == 403

    db_session.expire_all()
    row = db_session.get(User, driver.id)
    assert row.full_name == before_name


def test_driver_cannot_modify_another_driver(
    authenticated_driver,
    db_session,
):
    other = _create_driver(
        db_session,
        full_name="Other Driver",
        phone_number="+15550004102",
        email="other.driver.l1@test.nexo",
        verification_status="approved",
        availability_status="offline",
    )
    original_name = other.full_name

    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]
    response = client.patch(
        "/drivers/me",
        headers=headers,
        json={"display_name": "Should Only Update Self"},
    )
    assert response.status_code == 200
    assert response.json()["id"] == authenticated_driver["user"].id
    assert response.json()["display_name"] == "Should Only Update Self"

    db_session.expire_all()
    row = db_session.get(User, other.id)
    assert row.full_name == original_name


def test_no_public_self_approve_endpoint(authenticated_driver):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]
    for path in (
        "/drivers/approve",
        "/drivers/me/approve",
        "/drivers/verification",
    ):
        response = client.post(path, headers=headers, json={"status": "approved"})
        assert response.status_code in (404, 405)


def test_internal_routes_hidden_from_openapi(client: TestClient):
    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    paths = spec.json().get("paths") or {}
    assert all(not path.startswith("/internal") for path in paths)


def test_internal_verification_hidden_without_secret(
    authenticated_driver,
    monkeypatch,
):
    monkeypatch.setattr("app.config.INTERNAL_VERIFY_SECRET", None)
    client = authenticated_driver["client"]
    driver = authenticated_driver["user"]
    response = client.post(
        f"/internal/drivers/{driver.id}/verification",
        json={"status": "approved"},
    )
    assert response.status_code == 404


def test_internal_verification_approves_with_secret(
    authenticated_driver,
    db_session,
    monkeypatch,
):
    monkeypatch.setattr("app.config.INTERNAL_VERIFY_SECRET", "l1-test-secret")
    client = authenticated_driver["client"]
    driver = authenticated_driver["user"]

    db_session.expire_all()
    row = db_session.get(User, driver.id)
    row.verification_status = "pending"
    db_session.commit()

    denied = client.post(
        f"/internal/drivers/{driver.id}/verification",
        json={"status": "approved"},
        headers={"X-NEXO-INTERNAL-SECRET": "wrong"},
    )
    assert denied.status_code == 401

    approved = client.post(
        f"/internal/drivers/{driver.id}/verification",
        json={"status": "approved"},
        headers={"X-NEXO-INTERNAL-SECRET": "l1-test-secret"},
    )
    assert approved.status_code == 200
    assert approved.json()["verification_status"] == "approved"

    db_session.expire_all()
    assert db_session.get(User, driver.id).verification_status == "approved"


# ---------------------------------------------------------------------------
# Go online / dispatch
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "detail"),
    [
        ("pending", "Driver account is not approved."),
        ("rejected", "Driver account is not approved."),
        ("suspended", "Driver account is suspended."),
    ],
)
def test_unapproved_driver_cannot_go_online(
    authenticated_driver,
    db_session,
    status,
    detail,
):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]

    db_session.expire_all()
    row = db_session.get(User, driver.id)
    row.verification_status = status
    row.availability_status = "offline"
    db_session.commit()

    response = client.put("/drivers/go-online", headers=headers)
    assert response.status_code == 403
    assert response.json()["detail"] == detail

    db_session.expire_all()
    assert db_session.get(User, driver.id).availability_status == "offline"


def test_unapproved_driver_cannot_receive_offers(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    driver = authenticated_driver["user"]
    db_session.expire_all()
    row = db_session.get(User, driver.id)
    row.verification_status = "pending"
    row.availability_status = "available"
    db_session.commit()

    response = authenticated_passenger["client"].post(
        "/rides/",
        headers=authenticated_passenger["headers"],
        json=RIDE_CREATE_PAYLOAD,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["accepted_driver_id"] is None
    assert payload["assigned_driver"] is None


def test_suspended_driver_cannot_receive_offers(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    driver = authenticated_driver["user"]
    db_session.expire_all()
    row = db_session.get(User, driver.id)
    row.verification_status = "suspended"
    row.availability_status = "available"
    db_session.commit()

    response = authenticated_passenger["client"].post(
        "/rides/",
        headers=authenticated_passenger["headers"],
        json=RIDE_CREATE_PAYLOAD,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert response.json()["accepted_driver_id"] is None


def test_dispatch_skips_pending_and_selects_approved(
    authenticated_passenger,
    db_session,
):
    pending = _create_driver(
        db_session,
        full_name="Pending Near Driver",
        phone_number="+15550004103",
        email="pending.near.l1@test.nexo",
        verification_status="pending",
        current_latitude=-26.2041,
        current_longitude=28.0473,
    )
    approved = _create_driver(
        db_session,
        full_name="Approved Far Driver",
        phone_number="+15550004104",
        email="approved.far.l1@test.nexo",
        verification_status="approved",
        current_latitude=-26.2100,
        current_longitude=28.0550,
    )
    _add_vehicle(db_session, approved.id, "B444L1D", "approved")

    response = authenticated_passenger["client"].post(
        "/rides/",
        headers=authenticated_passenger["headers"],
        json=RIDE_CREATE_PAYLOAD,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["accepted_driver_id"] is None
    assert payload["assigned_driver"] is None

    pending_headers = _auth_headers(pending)
    approved_headers = _auth_headers(approved)
    ride_id = payload["id"]
    pending_respond = authenticated_passenger["client"].put(
        f"/rides/{ride_id}/respond",
        headers=pending_headers,
        json={"response_type": "accept_passenger_offer"},
    )
    assert pending_respond.status_code in (400, 403)
    approved_online = authenticated_passenger["client"].put(
        "/drivers/go-online",
        headers=approved_headers,
    )
    # go-online uses passenger client with driver token — TestClient shares app
    assert approved_online.status_code == 200
    approved_respond = authenticated_passenger["client"].put(
        f"/rides/{ride_id}/respond",
        headers=approved_headers,
        json={"response_type": "accept_passenger_offer"},
    )
    assert approved_respond.status_code == 200
    assert approved_respond.json()["status"] == "pending"
    assert approved_respond.json()["accepted_driver_id"] is None


# ---------------------------------------------------------------------------
# Passenger identity
# ---------------------------------------------------------------------------


def test_passenger_sees_assigned_driver_public_identity(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    driver = authenticated_driver["user"]
    vehicle = (
        db_session.query(Vehicle)
        .filter(Vehicle.driver_id == driver.id)
        .order_by(Vehicle.id.asc())
        .first()
    )
    assert vehicle is not None

    _prepare_driver_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    vehicle.verification_status = "pending"
    vehicle.registration_number = "B222L1B"
    db_session.commit()
    created = authenticated_passenger["client"].post(
        "/rides/",
        headers=authenticated_passenger["headers"],
        json=RIDE_CREATE_PAYLOAD,
    )
    assert created.status_code == 200
    ride_id = created.json()["id"]

    from tests.ride_flow import (
        driver_accept_passenger_offer,
        list_responses,
        passenger_select_response,
    )

    driver_accept_passenger_offer(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        ride_id,
    )
    responses = list_responses(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        ride_id,
    )
    passenger_select_response(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        ride_id,
        responses[0]["id"],
    )

    trip = authenticated_passenger["client"].get(
        f"/trips/{ride_id}",
        headers=authenticated_passenger["headers"],
    )
    assert trip.status_code == 200
    payload = trip.json()
    identity = payload["assigned_driver"]
    assert identity["display_name"] == driver.full_name
    assert identity["verification_status"] == "approved"
    assert identity["vehicle"]["make"] == "Toyota"
    assert identity["vehicle"]["model"] == "Corolla"
    assert identity["vehicle"]["color"] == "White"
    assert identity["vehicle"]["registration_number"] == "B222L1B"
    assert identity["vehicle"]["verification_status"] == "pending"
    assert identity["verification_status"] != identity["vehicle"]["verification_status"]
    assert "phone_number" not in identity
    assert "email" not in identity
    assert "password" not in identity
    assert "access_token" not in payload
    body = trip.text.lower()
    assert "bearer " not in body
    assert driver.email.lower() not in body
    assert driver.phone_number not in trip.text


def test_passenger_identity_stays_same_driver_throughout_ride(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    driver = authenticated_driver["user"]
    _prepare_driver_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    created = authenticated_passenger["client"].post(
        "/rides/",
        headers=authenticated_passenger["headers"],
        json=RIDE_CREATE_PAYLOAD,
    )
    ride_id = created.json()["id"]
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]
    passenger_headers = authenticated_passenger["headers"]
    passenger_client = authenticated_passenger["client"]

    from tests.ride_flow import (
        driver_accept_passenger_offer,
        list_responses,
        passenger_select_response,
    )

    driver_accept_passenger_offer(driver_client, driver_headers, ride_id)
    responses = list_responses(passenger_client, passenger_headers, ride_id)
    passenger_select_response(
        passenger_client,
        passenger_headers,
        ride_id,
        responses[0]["id"],
    )

    names = []
    ids = []
    trip = passenger_client.get(
        f"/trips/{ride_id}",
        headers=passenger_headers,
    )
    assert trip.status_code == 200
    payload = trip.json()
    names.append(payload["assigned_driver"]["display_name"])
    ids.append(payload["accepted_driver_id"])
    for path in (
        f"/rides/{ride_id}/arrive",
        f"/rides/{ride_id}/driver-arrived",
        f"/rides/{ride_id}/start",
    ):
        assert driver_client.put(path, headers=driver_headers).status_code == 200
        trip = passenger_client.get(
            f"/trips/{ride_id}",
            headers=passenger_headers,
        )
        assert trip.status_code == 200
        payload = trip.json()
        names.append(payload["assigned_driver"]["display_name"])
        ids.append(payload["accepted_driver_id"])

    assert set(ids) == {driver.id}
    assert set(names) == {driver.full_name}


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


def test_driver_history_is_persistent_and_scoped(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    driver = authenticated_driver["user"]
    completed = _complete_assigned_ride(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        driver.id,
    )

    history = authenticated_driver["client"].get(
        "/drivers/rides",
        headers=authenticated_driver["headers"],
    )
    assert history.status_code == 200
    rows = history.json()
    assert any(item["id"] == completed["id"] for item in rows)
    match = next(item for item in rows if item["id"] == completed["id"])
    assert match["status"] == "completed"
    assert match["proposed_fare"] == RIDE_CREATE_PAYLOAD["proposed_fare"]
    assert match["accepted_driver_id"] == driver.id

    other = _create_driver(
        db_session,
        full_name="History Other Driver",
        phone_number="+15550004105",
        email="history.other.l1@test.nexo",
        verification_status="approved",
        availability_status="offline",
    )
    other_headers = _auth_headers(other)
    other_history = authenticated_driver["client"].get(
        "/drivers/rides",
        headers=other_headers,
    )
    assert other_history.status_code == 200
    assert other_history.json() == []


def test_passenger_cannot_view_driver_history(authenticated_passenger):
    response = authenticated_passenger["client"].get(
        "/drivers/rides",
        headers=authenticated_passenger["headers"],
    )
    assert response.status_code == 403


def test_driver_history_does_not_include_other_driver_rides(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    driver = authenticated_driver["user"]
    completed = _complete_assigned_ride(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        driver.id,
    )
    other = _create_driver(
        db_session,
        full_name="Second History Driver",
        phone_number="+15550004106",
        email="history.second.l1@test.nexo",
        verification_status="approved",
        availability_status="offline",
    )
    other_headers = _auth_headers(other)
    response = authenticated_driver["client"].get(
        "/drivers/rides",
        headers=other_headers,
    )
    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert completed["id"] not in ids

    db_session.expire_all()
    ride = db_session.get(RideRequest, completed["id"])
    assert ride.accepted_driver_id == driver.id
    assert ride.accepted_driver_id != other.id
