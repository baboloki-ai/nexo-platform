"""
L4.2.1: OS-level Web Push for marketplace ride-request broadcasts.

Push is an additional delivery path beside the existing WebSocket and
GET /drivers/requests polling. It must not accept the ride or change
ride, wallet, vehicle, or availability state.
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.constants.push import PUSH_NOTIFICATION_TYPE, PUSH_TITLE
from app.constants.verification import VerificationStatus
from app.models.driver_push_subscription import DriverPushSubscription
from app.models.driver_response import DriverResponse
from app.models.driver_wallet import DriverWallet
from app.models.ride_request import RideRequest
from app.models.user import User
from app.models.vehicle import Vehicle
from app.services.marketplace_service import MarketplaceService
from app.services.notification_service import NotificationService
from app.config import RIDE_OFFER_TTL_SECONDS
from app.services.push_notification_service import (
    PushNotificationService,
    send_web_push,
)
from app.services.wallet_service import WalletService
from app.utils.jwt import create_access_token
from app.utils.security import hash_password
from tests.ride_flow import (
    advance_to_accepted,
    create_pending_ride,
    prepare_driver_online,
)

TEST_VAPID_PUBLIC_KEY = (
    "BNjykSS5koqp_2RrF5JDAmwqmX4udb2-cQBK5CsQNT9pRfIhAOcP9zl4oGQbHHOn"
    "V28OHqCw8XNpg6eyuwL24sM"
)
TEST_VAPID_PRIVATE_KEY = "N4k6AHUlsdQHOAcN6P50RESIAcjPuKfTLJTrMB6cGdY"

ENDPOINT_A = "https://push.example.test/subscription/driver-a"
ENDPOINT_B = "https://push.example.test/subscription/driver-b"
PUSH_KEYS = {
    "p256dh": "BLTexampleP256dhKeyForTestsOnlyNotARealBrowserKeyxx",
    "auth": "dGVzdEF1dGhLZXkxMjM",
}


@pytest.fixture(autouse=True)
def _configure_vapid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.config.VAPID_PUBLIC_KEY",
        TEST_VAPID_PUBLIC_KEY,
    )
    monkeypatch.setattr(
        "app.config.VAPID_PRIVATE_KEY",
        TEST_VAPID_PRIVATE_KEY,
    )
    monkeypatch.setattr(
        "app.config.VAPID_CLAIM_EMAIL",
        "mailto:nexo-test@localhost",
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


def _subscription_body(endpoint: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "endpoint": endpoint,
        "keys": PUSH_KEYS,
    }
    if extra:
        body.update(extra)
    return body


def _register_push(
    client: TestClient,
    headers: dict[str, str],
    endpoint: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = client.post(
        "/drivers/push/subscriptions",
        headers=headers,
        json=_subscription_body(endpoint, extra),
    )
    assert response.status_code == 200, response.text
    return response.json()


def _snapshot_driver(db_session: Session, driver_id: int) -> dict[str, Any]:
    db_session.expire_all()
    driver = db_session.get(User, driver_id)
    assert driver is not None
    wallet = (
        db_session.query(DriverWallet)
        .filter(DriverWallet.driver_id == driver_id)
        .one()
    )
    vehicle = (
        db_session.query(Vehicle)
        .filter(Vehicle.driver_id == driver_id)
        .first()
    )
    return {
        "availability_status": driver.availability_status,
        "verification_status": driver.verification_status,
        "wallet_balance": wallet.available_balance,
        "vehicle_verification": (
            vehicle.verification_status if vehicle is not None else None
        ),
    }


@pytest.fixture
def second_driver_user(db_session: Session) -> User:
    user = User(
        full_name="Second Push Driver",
        phone_number="+15550002102",
        email="driver.push.two@test.nexo",
        password=hash_password("TestDriverPushTwo123!"),
        role="driver",
        verification_status="approved",
        availability_status="offline",
        current_latitude=-26.2050,
        current_longitude=28.0480,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    WalletService.ensure_wallet(db_session, user.id)
    db_session.commit()
    db_session.expire_all()
    db_session.execute(
        update(DriverWallet)
        .where(DriverWallet.driver_id == user.id)
        .values(available_balance=Decimal("1000.00"))
        .execution_options(synchronize_session="fetch")
    )
    db_session.add(
        Vehicle(
            driver_id=user.id,
            make="Toyota",
            model="Corolla",
            year=2021,
            color="White",
            registration_number="B413PSH",
            vehicle_type="sedan",
            verification_status=VerificationStatus.APPROVED,
        )
    )
    db_session.commit()
    return user


def test_eligible_driver_with_subscription_receives_push(
    authenticated_passenger,
    authenticated_driver,
):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]
    registered = _register_push(client, headers, ENDPOINT_A)
    assert registered["driver_id"] == authenticated_driver["user"].id
    prepare_driver_online(client, headers)

    with patch(
        "app.services.push_notification_service.send_web_push"
    ) as send_push:
        created = create_pending_ride(
            authenticated_passenger["client"],
            authenticated_passenger["headers"],
        )

    assert send_push.call_count == 1
    payload = json.loads(send_push.call_args.kwargs["payload"])
    assert payload["type"] == PUSH_NOTIFICATION_TYPE
    assert payload["ride_id"] == created["id"]
    assert payload["title"] == PUSH_TITLE
    assert send_push.call_args.kwargs["subscription_info"]["endpoint"] == ENDPOINT_A


def test_push_payload_contains_ride_id_and_does_not_accept(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]
    driver_id = authenticated_driver["user"].id
    _register_push(client, headers, ENDPOINT_A)
    prepare_driver_online(client, headers)
    before = _snapshot_driver(db_session, driver_id)

    with patch("app.services.push_notification_service.send_web_push") as send_push:
        created = create_pending_ride(
            authenticated_passenger["client"],
            authenticated_passenger["headers"],
        )

    payload = json.loads(send_push.call_args.kwargs["payload"])
    assert payload["ride_id"] == created["id"]
    assert "accept" not in json.dumps(payload).lower()

    db_session.expire_all()
    ride = db_session.get(RideRequest, created["id"])
    assert ride is not None
    assert ride.status == "pending"
    assert ride.accepted_driver_id is None
    assert ride.agreed_fare is None
    assert (
        db_session.query(DriverResponse)
        .filter(DriverResponse.ride_id == ride.id)
        .count()
        == 0
    )
    after = _snapshot_driver(db_session, driver_id)
    assert after["wallet_balance"] == before["wallet_balance"]
    assert after["vehicle_verification"] == before["vehicle_verification"]
    assert after["availability_status"] == before["availability_status"]
    assert after["verification_status"] == before["verification_status"]


def test_push_failure_does_not_break_websocket_or_ride_creation(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]
    _register_push(client, headers, ENDPOINT_A)
    prepare_driver_online(client, headers)

    with patch.object(
        PushNotificationService,
        "send_ride_request",
        side_effect=RuntimeError("push provider down"),
    ):
        with patch.object(
            NotificationService,
            "_schedule",
            side_effect=lambda coro: coro.close(),
        ) as scheduled:
            created = create_pending_ride(
                authenticated_passenger["client"],
                authenticated_passenger["headers"],
            )

    assert created["status"] == "pending"
    assert created["accepted_driver_id"] is None
    assert scheduled.called
    db_session.expire_all()
    ride = db_session.get(RideRequest, created["id"])
    assert ride is not None
    assert ride.status == "pending"


def test_push_delivery_exception_does_not_prevent_ride_creation(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]
    _register_push(client, headers, ENDPOINT_A)
    prepare_driver_online(client, headers)

    with patch(
        "app.services.push_notification_service.send_web_push",
        side_effect=RuntimeError("fcm timeout"),
    ):
        created = create_pending_ride(
            authenticated_passenger["client"],
            authenticated_passenger["headers"],
        )

    assert created["status"] == "pending"
    db_session.expire_all()
    ride = db_session.get(RideRequest, created["id"])
    assert ride is not None
    assert ride.status == "pending"
    assert ride.accepted_driver_id is None


def test_unregistered_driver_uses_websocket_and_polling_only(
    authenticated_passenger,
    authenticated_driver,
):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]
    prepare_driver_online(client, headers)

    with patch(
        "app.services.push_notification_service.send_web_push"
    ) as send_push:
        with patch.object(
            NotificationService,
            "_schedule",
            side_effect=lambda coro: coro.close(),
        ) as scheduled:
            created = create_pending_ride(
                authenticated_passenger["client"],
                authenticated_passenger["headers"],
            )

    assert send_push.call_count == 0
    assert scheduled.called
    listed = client.get("/drivers/requests", headers=headers)
    assert listed.status_code == 200
    ride_ids = {item["ride_id"] for item in listed.json()}
    assert created["id"] in ride_ids


def test_driver_cannot_register_subscription_for_another_driver(
    authenticated_driver,
    second_driver_user: User,
    db_session: Session,
):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]
    other_headers = _auth_headers(second_driver_user)

    registered = _register_push(
        client,
        headers,
        ENDPOINT_A,
        extra={"driver_id": second_driver_user.id},
    )
    assert registered["driver_id"] == authenticated_driver["user"].id
    assert registered["driver_id"] != second_driver_user.id

    db_session.expire_all()
    row = (
        db_session.query(DriverPushSubscription)
        .filter(DriverPushSubscription.endpoint == ENDPOINT_A)
        .one()
    )
    assert row.driver_id == authenticated_driver["user"].id

    stolen = client.post(
        "/drivers/push/subscriptions",
        headers=other_headers,
        json=_subscription_body(
            ENDPOINT_B,
            extra={"driver_id": authenticated_driver["user"].id},
        ),
    )
    assert stolen.status_code == 200
    assert stolen.json()["driver_id"] == second_driver_user.id

    other_delete = client.request(
        "DELETE",
        "/drivers/push/subscriptions",
        headers=other_headers,
        json={"endpoint": ENDPOINT_A},
    )
    assert other_delete.status_code == 404
    db_session.expire_all()
    remaining = (
        db_session.query(DriverPushSubscription)
        .filter(DriverPushSubscription.endpoint == ENDPOINT_A)
        .one()
    )
    assert remaining.driver_id == authenticated_driver["user"].id


def test_passenger_cannot_register_push_subscription(authenticated_passenger):
    response = authenticated_passenger["client"].post(
        "/drivers/push/subscriptions",
        headers=authenticated_passenger["headers"],
        json=_subscription_body(ENDPOINT_A),
    )
    assert response.status_code == 403


def test_unauthenticated_push_registration_rejected(client: TestClient):
    response = client.post(
        "/drivers/push/subscriptions",
        json=_subscription_body(ENDPOINT_A),
    )
    assert response.status_code == 401


def test_marketplace_eligibility_is_reused_for_push(
    authenticated_passenger,
    authenticated_driver,
    second_driver_user: User,
    db_session: Session,
):
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]
    other_headers = _auth_headers(second_driver_user)
    _register_push(driver_client, driver_headers, ENDPOINT_A)
    _register_push(driver_client, other_headers, ENDPOINT_B)
    prepare_driver_online(driver_client, driver_headers)

    with patch(
        "app.services.marketplace_service.MarketplaceService.eligible_drivers",
        wraps=MarketplaceService.eligible_drivers,
    ) as eligible:
        with patch(
            "app.services.push_notification_service.send_web_push"
        ) as send_push:
            created = create_pending_ride(
                authenticated_passenger["client"],
                authenticated_passenger["headers"],
            )

    assert eligible.called
    notified_endpoints = {
        call.kwargs["subscription_info"]["endpoint"]
        for call in send_push.call_args_list
    }
    assert ENDPOINT_A in notified_endpoints
    assert ENDPOINT_B not in notified_endpoints
    payloads = [
        json.loads(call.kwargs["payload"]) for call in send_push.call_args_list
    ]
    assert all(item["ride_id"] == created["id"] for item in payloads)

    db_session.expire_all()
    other = db_session.get(User, second_driver_user.id)
    assert other is not None
    assert other.availability_status == "offline"


def test_existing_ride_acceptance_still_works_with_push_registered(
    authenticated_passenger,
    authenticated_driver,
):
    client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]
    _register_push(client, headers, ENDPOINT_A)

    with patch("app.services.push_notification_service.send_web_push"):
        selected = advance_to_accepted(
            authenticated_passenger["client"],
            authenticated_passenger["headers"],
            client,
            headers,
            authenticated_driver["user"].id,
        )

    assert selected["status"] == "accepted"
    assert selected["accepted_driver_id"] == authenticated_driver["user"].id
    assert selected["agreed_fare"] is not None


def test_send_web_push_sets_non_zero_ttl_and_high_urgency():
    with patch("pywebpush.webpush") as webpush_fn:
        send_web_push(
            subscription_info={"endpoint": ENDPOINT_A, "keys": PUSH_KEYS},
            payload="{}",
        )

    assert webpush_fn.call_count == 1
    kwargs = webpush_fn.call_args.kwargs
    assert kwargs["ttl"] == RIDE_OFFER_TTL_SECONDS
    assert kwargs["ttl"] > 0
    assert kwargs["headers"]["Urgency"] == "high"
    assert kwargs["vapid_claims"]["sub"] == "mailto:nexo-test@localhost"


def test_vapid_public_key_does_not_expose_private_key(
    authenticated_driver,
):
    response = authenticated_driver["client"].get(
        "/drivers/push/vapid-public-key",
        headers=authenticated_driver["headers"],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["vapid_public_key"] == TEST_VAPID_PUBLIC_KEY
    assert TEST_VAPID_PRIVATE_KEY not in json.dumps(body)
    assert "private" not in json.dumps(body).lower()
