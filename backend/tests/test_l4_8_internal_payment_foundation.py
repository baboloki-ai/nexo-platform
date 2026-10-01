"""
L4.8 Internal payment foundation: cash payment row at fare lock,
driver confirm-cash, independent of ride completion and 8% commission.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.constants.payment import (
    PaymentMethod,
    PaymentProviderName,
    PaymentStatus,
    SettlementStatus,
)
from app.constants.ride_status import RideStatus
from app.constants.verification import VerificationStatus
from app.constants.wallet import WalletEntryType
from app.models.driver_wallet import DriverWallet
from app.models.payment import Payment
from app.models.ride_request import RideRequest
from app.models.user import User
from app.models.vehicle import Vehicle
from app.models.wallet_ledger_entry import WalletLedgerEntry
from app.services.notification_service import NotificationService
from app.services.wallet_service import WalletService
from app.utils.jwt import create_access_token
from app.utils.security import hash_password
from app.websocket.manager import manager
from tests.ride_flow import advance_to_accepted

FARE_P40 = {
    "pickup_location": "Main Mall",
    "pickup_latitude": -24.6545,
    "pickup_longitude": 25.9086,
    "destination": "Airport Junction",
    "destination_latitude": -24.6278,
    "destination_longitude": 25.9059,
    "proposed_fare": 40.0,
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
def second_driver_user(db_session: Session) -> User:
    user = User(
        full_name="Payment Test Driver B",
        phone_number="+15550008002",
        email="driver.payment.b@test.nexo",
        password=hash_password("TestDriverPaymentB123!"),
        role="driver",
        verification_status=VerificationStatus.APPROVED,
        availability_status="available",
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
            make="Honda",
            model="Fit",
            year=2020,
            color="Blue",
            registration_number="B413PAY",
            vehicle_type="sedan",
            verification_status=VerificationStatus.APPROVED,
        )
    )
    db_session.commit()
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


def _select_ride(authenticated_passenger, authenticated_driver, payload=None):
    return advance_to_accepted(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        authenticated_driver["user"].id,
        payload=payload,
    )


def _confirm(client: TestClient, headers: dict[str, str], payment_id: int):
    return client.post(
        f"/payments/{payment_id}/confirm-cash",
        headers=headers,
    )


def _complete_selected_ride(client, headers, ride_id: int):
    assert client.put(f"/rides/{ride_id}/arrive", headers=headers).status_code == 200
    assert client.put(
        f"/rides/{ride_id}/driver-arrived",
        headers=headers,
    ).status_code == 200
    assert client.put(f"/rides/{ride_id}/start", headers=headers).status_code == 200
    complete = client.put(f"/rides/{ride_id}/complete", headers=headers)
    assert complete.status_code == 200, complete.text
    return complete.json()


def test_payment_created_when_driver_is_selected(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    selected = _select_ride(authenticated_passenger, authenticated_driver)
    payment = selected.get("payment")
    assert payment is not None
    assert payment["ride_id"] == selected["id"]

    db_session.expire_all()
    rows = db_session.query(Payment).filter(Payment.ride_id == selected["id"]).all()
    assert len(rows) == 1


def test_payment_amount_equals_agreed_fare(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    selected = _select_ride(
        authenticated_passenger,
        authenticated_driver,
        payload={**FARE_P40, "proposed_fare": 155.0},
    )
    assert selected["agreed_fare"] == 155.0
    payment = selected["payment"]
    assert payment["amount"] == selected["agreed_fare"]
    assert payment["amount"] == 155.0

    db_session.expire_all()
    row = db_session.query(Payment).filter(Payment.ride_id == selected["id"]).one()
    assert Decimal(str(row.amount)) == Decimal(str(selected["agreed_fare"]))


def test_initial_payment_is_pending_cash(
    authenticated_passenger,
    authenticated_driver,
):
    selected = _select_ride(authenticated_passenger, authenticated_driver)
    payment = selected["payment"]
    assert payment["method"] == PaymentMethod.CASH
    assert payment["status"] == PaymentStatus.PENDING
    assert payment["paid_at"] is None
    assert payment["currency"] == "BWP"
    assert payment["settlement_status"] == SettlementStatus.DRIVER_COLLECTED
    assert "idempotency_key" not in payment
    assert "failure_code" not in payment
    assert "failure_message" not in payment
    assert "provider_reference" not in payment
    assert "cash_confirmed_by_user_id" not in payment


def test_initial_payment_provider_is_nexo_cash(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    selected = _select_ride(authenticated_passenger, authenticated_driver)
    db_session.expire_all()
    row = db_session.query(Payment).filter(Payment.ride_id == selected["id"]).one()
    assert row.provider == PaymentProviderName.NEXO_CASH
    assert row.method == PaymentMethod.CASH
    assert row.status == PaymentStatus.PENDING


def test_assigned_driver_can_confirm_cash(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    selected = _select_ride(authenticated_passenger, authenticated_driver)
    payment_id = selected["payment"]["id"]
    response = _confirm(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        payment_id,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == PaymentStatus.PAID
    assert body["paid_at"] is not None
    assert body["settlement_status"] == SettlementStatus.DRIVER_COLLECTED

    db_session.expire_all()
    row = db_session.get(Payment, payment_id)
    assert row.status == PaymentStatus.PAID
    assert row.cash_confirmed_by_user_id == authenticated_driver["user"].id
    assert row.paid_at is not None
    assert row.cash_confirmed_at is not None


def test_passenger_cannot_confirm_cash(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    selected = _select_ride(authenticated_passenger, authenticated_driver)
    payment_id = selected["payment"]["id"]
    response = _confirm(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        payment_id,
    )
    assert response.status_code == 403

    db_session.expire_all()
    row = db_session.get(Payment, payment_id)
    assert row.status == PaymentStatus.PENDING
    assert row.paid_at is None


def test_unrelated_driver_cannot_confirm_cash(
    authenticated_passenger,
    authenticated_driver,
    authenticated_second_driver,
    db_session: Session,
):
    selected = _select_ride(authenticated_passenger, authenticated_driver)
    payment_id = selected["payment"]["id"]
    response = _confirm(
        authenticated_second_driver["client"],
        authenticated_second_driver["headers"],
        payment_id,
    )
    assert response.status_code == 403

    db_session.expire_all()
    row = db_session.get(Payment, payment_id)
    assert row.status == PaymentStatus.PENDING
    assert row.paid_at is None


def test_duplicate_confirmation_is_safe(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    selected = _select_ride(authenticated_passenger, authenticated_driver)
    payment_id = selected["payment"]["id"]
    first = _confirm(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        payment_id,
    )
    assert first.status_code == 200, first.text
    first_paid_at = first.json()["paid_at"]

    second = _confirm(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        payment_id,
    )
    assert second.status_code == 200, second.text
    assert second.json()["status"] == PaymentStatus.PAID
    assert second.json()["paid_at"] == first_paid_at

    db_session.expire_all()
    assert (
        db_session.query(Payment)
        .filter(
            Payment.ride_id == selected["id"],
            Payment.status == PaymentStatus.PAID,
        )
        .count()
        == 1
    )


def test_already_paid_payment_cannot_be_paid_twice(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    selected = _select_ride(authenticated_passenger, authenticated_driver)
    payment_id = selected["payment"]["id"]
    assert _confirm(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        payment_id,
    ).status_code == 200

    db_session.expire_all()
    original = db_session.get(Payment, payment_id)
    original_paid_at = original.paid_at
    original_confirmed_at = original.cash_confirmed_at

    again = _confirm(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        payment_id,
    )
    assert again.status_code == 200
    db_session.expire_all()
    row = db_session.get(Payment, payment_id)
    assert row.paid_at == original_paid_at
    assert row.cash_confirmed_at == original_confirmed_at
    assert (
        db_session.query(Payment)
        .filter(Payment.ride_id == selected["id"])
        .count()
        == 1
    )


def test_amount_mismatch_is_rejected(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    selected = _select_ride(authenticated_passenger, authenticated_driver)
    payment_id = selected["payment"]["id"]

    db_session.expire_all()
    db_session.execute(
        update(Payment)
        .where(Payment.id == payment_id)
        .values(amount=Decimal("99.00"))
        .execution_options(synchronize_session="fetch")
    )
    db_session.commit()

    response = _confirm(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        payment_id,
    )
    assert response.status_code == 400

    db_session.expire_all()
    row = db_session.get(Payment, payment_id)
    assert row.status != PaymentStatus.PAID
    assert row.paid_at is None


def test_ride_completion_does_not_automatically_mark_cash_paid(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    selected = _select_ride(authenticated_passenger, authenticated_driver)
    body = _complete_selected_ride(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        selected["id"],
    )
    assert body["status"] == "completed"
    payment = body["payment"]
    assert payment is not None
    assert payment["status"] == PaymentStatus.PENDING
    assert payment["method"] == PaymentMethod.CASH
    assert payment["paid_at"] is None

    db_session.expire_all()
    row = (
        db_session.query(Payment)
        .filter(Payment.ride_id == selected["id"])
        .one()
    )
    assert row.status == PaymentStatus.PENDING
    assert row.paid_at is None


def test_commission_posted_at_completion_unchanged(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    db_session.expire_all()
    db_session.execute(
        update(DriverWallet)
        .where(DriverWallet.driver_id == authenticated_driver["user"].id)
        .values(available_balance=Decimal("40.00"))
        .execution_options(synchronize_session="fetch")
    )
    db_session.commit()

    selected = _select_ride(
        authenticated_passenger,
        authenticated_driver,
        payload=FARE_P40,
    )
    body = _complete_selected_ride(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        selected["id"],
    )
    assert body["status"] == "completed"
    assert body["agreed_fare"] == 40.0
    assert body["payment"]["status"] == PaymentStatus.PENDING

    db_session.expire_all()
    entries = (
        db_session.query(WalletLedgerEntry)
        .filter(
            WalletLedgerEntry.ride_id == selected["id"],
            WalletLedgerEntry.entry_type == WalletEntryType.COMMISSION,
        )
        .all()
    )
    assert len(entries) == 1
    assert Decimal(str(entries[0].amount)) == Decimal("-3.20")
    wallet = (
        db_session.query(DriverWallet)
        .filter(DriverWallet.driver_id == authenticated_driver["user"].id)
        .one()
    )
    assert Decimal(str(wallet.available_balance)) == Decimal("36.80")

    payment = db_session.query(Payment).filter(Payment.ride_id == selected["id"]).one()
    assert payment.status == PaymentStatus.PENDING
    assert payment.paid_at is None


def _cancel_assigned(client: TestClient, headers: dict[str, str], ride_id: int):
    response = client.put(f"/rides/{ride_id}/cancel", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _commission_entries(db_session: Session, ride_id: int):
    return (
        db_session.query(WalletLedgerEntry)
        .filter(
            WalletLedgerEntry.ride_id == ride_id,
            WalletLedgerEntry.entry_type == WalletEntryType.COMMISSION,
        )
        .all()
    )


def test_assigned_driver_cannot_confirm_cash_after_cancellation(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    selected = _select_ride(authenticated_passenger, authenticated_driver)
    payment_id = selected["payment"]["id"]
    _cancel_assigned(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        selected["id"],
    )

    response = _confirm(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        payment_id,
    )
    assert response.status_code == 400

    db_session.expire_all()
    row = db_session.get(Payment, payment_id)
    assert row.status == PaymentStatus.CANCELLED
    assert row.paid_at is None
    assert row.cash_confirmed_at is None
    assert row.cash_confirmed_by_user_id is None


def test_assigned_driver_cannot_confirm_cash_after_ride_expired(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    selected = _select_ride(authenticated_passenger, authenticated_driver)
    payment_id = selected["payment"]["id"]

    db_session.expire_all()
    db_session.execute(
        update(RideRequest)
        .where(RideRequest.id == selected["id"])
        .values(status=RideStatus.EXPIRED)
        .execution_options(synchronize_session="fetch")
    )
    db_session.commit()

    response = _confirm(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        payment_id,
    )
    assert response.status_code == 400

    db_session.expire_all()
    row = db_session.get(Payment, payment_id)
    assert row.status == PaymentStatus.PENDING
    assert row.paid_at is None
    assert row.cash_confirmed_at is None


def test_cancelled_ride_changes_pending_payment_to_cancelled(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    selected = _select_ride(authenticated_passenger, authenticated_driver)
    payment_id = selected["payment"]["id"]
    body = _cancel_assigned(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        selected["id"],
    )
    assert body["status"] == RideStatus.CANCELLED_BY_PASSENGER
    assert body["payment"] is not None
    assert body["payment"]["id"] == payment_id
    assert body["payment"]["status"] == PaymentStatus.CANCELLED
    assert body["payment"]["paid_at"] is None

    db_session.expire_all()
    rows = db_session.query(Payment).filter(Payment.ride_id == selected["id"]).all()
    assert len(rows) == 1
    assert rows[0].id == payment_id
    assert rows[0].status == PaymentStatus.CANCELLED
    assert rows[0].paid_at is None


def test_cancelled_ride_changes_processing_payment_to_cancelled(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    selected = _select_ride(authenticated_passenger, authenticated_driver)
    payment_id = selected["payment"]["id"]

    db_session.expire_all()
    db_session.execute(
        update(Payment)
        .where(Payment.id == payment_id)
        .values(status=PaymentStatus.PROCESSING)
        .execution_options(synchronize_session="fetch")
    )
    db_session.commit()

    body = _cancel_assigned(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        selected["id"],
    )
    assert body["payment"]["status"] == PaymentStatus.CANCELLED

    db_session.expire_all()
    row = db_session.get(Payment, payment_id)
    assert row.status == PaymentStatus.CANCELLED
    assert row.paid_at is None
    assert (
        db_session.query(Payment)
        .filter(Payment.ride_id == selected["id"])
        .count()
        == 1
    )


def test_already_paid_payment_is_not_changed_by_cancellation(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    selected = _select_ride(authenticated_passenger, authenticated_driver)
    payment_id = selected["payment"]["id"]
    assert _confirm(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        payment_id,
    ).status_code == 200

    db_session.expire_all()
    original = db_session.get(Payment, payment_id)
    original_paid_at = original.paid_at
    original_confirmed_at = original.cash_confirmed_at
    original_confirmed_by = original.cash_confirmed_by_user_id

    body = _cancel_assigned(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        selected["id"],
    )
    assert body["payment"]["status"] == PaymentStatus.PAID
    assert body["payment"]["paid_at"] is not None

    db_session.expire_all()
    row = db_session.get(Payment, payment_id)
    assert row.status == PaymentStatus.PAID
    assert row.paid_at == original_paid_at
    assert row.cash_confirmed_at == original_confirmed_at
    assert row.cash_confirmed_by_user_id == original_confirmed_by
    assert (
        db_session.query(Payment)
        .filter(Payment.ride_id == selected["id"])
        .count()
        == 1
    )


def test_passenger_cannot_confirm_cancelled_cash_payment(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    selected = _select_ride(authenticated_passenger, authenticated_driver)
    payment_id = selected["payment"]["id"]
    _cancel_assigned(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        selected["id"],
    )

    response = _confirm(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        payment_id,
    )
    assert response.status_code == 403

    db_session.expire_all()
    row = db_session.get(Payment, payment_id)
    assert row.status == PaymentStatus.CANCELLED
    assert row.paid_at is None


def test_payment_websocket_reports_cancelled_status(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    selected = _select_ride(authenticated_passenger, authenticated_driver)
    payment_id = selected["payment"]["id"]
    ride_id = selected["id"]
    passenger = authenticated_passenger["passenger"]
    token = create_access_token(
        data={
            "sub": str(authenticated_passenger["user"].id),
            "email": authenticated_passenger["user"].email,
            "role": authenticated_passenger["user"].role,
        }
    )

    manager.driver_connections.clear()
    manager.passenger_connections.clear()
    captured: list[dict[str, Any]] = []
    original = NotificationService.notify_payment_updated

    def _capture(**kwargs: Any) -> None:
        captured.append(kwargs)
        original(**kwargs)

    NotificationService.notify_payment_updated = staticmethod(_capture)  # type: ignore[method-assign]
    try:
        with authenticated_passenger["client"].websocket_connect(
            f"/ws/passenger/{passenger.id}?token={token}"
        ) as websocket:
            assert websocket.receive_json()["event"] == "connected"
            body = _cancel_assigned(
                authenticated_passenger["client"],
                authenticated_passenger["headers"],
                ride_id,
            )
            assert body["payment"]["status"] == PaymentStatus.CANCELLED

            event = None
            for _ in range(8):
                message = websocket.receive_json()
                if message.get("event") == "payment_updated":
                    event = message
                    break
            assert event is not None
            assert event["ride_id"] == ride_id
            assert event["payment_id"] == payment_id
            assert event["status"] == PaymentStatus.CANCELLED
    finally:
        NotificationService.notify_payment_updated = original  # type: ignore[method-assign]
        manager.driver_connections.clear()
        manager.passenger_connections.clear()

    assert captured
    assert captured[-1]["ride_id"] == ride_id
    assert captured[-1]["payment_id"] == payment_id
    assert captured[-1]["status"] == PaymentStatus.CANCELLED

    db_session.expire_all()
    row = db_session.get(Payment, payment_id)
    assert row.status == PaymentStatus.CANCELLED


def test_confirm_cash_does_not_change_commission(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    db_session.expire_all()
    db_session.execute(
        update(DriverWallet)
        .where(DriverWallet.driver_id == authenticated_driver["user"].id)
        .values(available_balance=Decimal("40.00"))
        .execution_options(synchronize_session="fetch")
    )
    db_session.commit()

    selected = _select_ride(
        authenticated_passenger,
        authenticated_driver,
        payload=FARE_P40,
    )
    body = _complete_selected_ride(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        selected["id"],
    )
    assert body["status"] == "completed"
    payment_id = body["payment"]["id"]

    confirmed = _confirm(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        payment_id,
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == PaymentStatus.PAID

    db_session.expire_all()
    entries = _commission_entries(db_session, selected["id"])
    assert len(entries) == 1
    assert Decimal(str(entries[0].amount)) == Decimal("-3.20")
    wallet = (
        db_session.query(DriverWallet)
        .filter(DriverWallet.driver_id == authenticated_driver["user"].id)
        .one()
    )
    assert Decimal(str(wallet.available_balance)) == Decimal("36.80")

