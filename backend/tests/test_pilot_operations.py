"""
Pilot cancellation rules, cancellation races, and wallet commission invariants.
"""
from __future__ import annotations

import threading
import time
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import text, update
from sqlalchemy.orm import Session, sessionmaker

from app.constants.driver_response import DriverResponseStatus
from app.constants.negotiation import NegotiationAction
from app.constants.ride_status import RideStatus
from app.constants.wallet import WalletEntryType
from app.models.driver_response import DriverResponse
from app.models.driver_wallet import DriverWallet
from app.models.negotiation_event import NegotiationEvent
from app.models.ride_request import RideRequest
from app.models.user import User
from app.models.wallet_ledger_entry import WalletLedgerEntry
from app.services.marketplace_service import MarketplaceService
from app.services.ride_service import RideService
from app.utils.money import LAUNCH_SEED_AMOUNT
from tests.ride_flow import (
    advance_to_accepted,
    driver_accept_passenger_offer,
    list_responses,
    prepare_driver_online,
    create_pending_ride,
)


def _set_wallet(db_session: Session, driver_id: int, amount: Decimal) -> None:
    db_session.expire_all()
    db_session.execute(
        update(DriverWallet)
        .where(DriverWallet.driver_id == driver_id)
        .values(available_balance=amount)
        .execution_options(synchronize_session="fetch")
    )
    db_session.commit()
    db_session.expire_all()


def _commission_count(db_session: Session, ride_id: int | None = None) -> int:
    db_session.expire_all()
    query = db_session.query(WalletLedgerEntry).filter(
        WalletLedgerEntry.entry_type == WalletEntryType.COMMISSION,
    )
    if ride_id is not None:
        query = query.filter(WalletLedgerEntry.ride_id == ride_id)
    return query.count()


def _advance_to(
    passenger,
    driver,
    stage: str,
) -> dict[str, Any]:
    selected = advance_to_accepted(
        passenger["client"],
        passenger["headers"],
        driver["client"],
        driver["headers"],
        driver["user"].id,
    )
    ride_id = selected["id"]
    headers = driver["headers"]
    client = driver["client"]
    if stage == "accepted":
        return selected
    assert client.put(f"/rides/{ride_id}/arrive", headers=headers).status_code == 200
    if stage == "arriving":
        selected["status"] = RideStatus.DRIVER_ARRIVING
        return selected
    assert client.put(
        f"/rides/{ride_id}/driver-arrived",
        headers=headers,
    ).status_code == 200
    if stage == "arrived":
        selected["status"] = RideStatus.DRIVER_ARRIVED
        return selected
    assert client.put(f"/rides/{ride_id}/start", headers=headers).status_code == 200
    if stage == "in_progress":
        selected["status"] = RideStatus.IN_PROGRESS
        return selected
    assert client.put(f"/rides/{ride_id}/complete", headers=headers).status_code == 200
    selected["status"] = RideStatus.COMPLETED
    return selected


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


def _release_blocker_after_waiters(
    session: Session,
    start_barrier: threading.Barrier,
    *,
    minimum: int = 1,
) -> None:
    start_barrier.wait()
    deadline = time.monotonic() + 5.0
    try:
        while time.monotonic() < deadline:
            if _waiting_lock_backends(session) >= minimum:
                break
    except Exception:
        pass
    session.rollback()


# ---------------------------------------------------------------------------
# Passenger cancellation
# ---------------------------------------------------------------------------


def test_passenger_cancel_pending_marketplace(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    prepare_driver_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    created = create_pending_ride(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
    )
    driver_accept_passenger_offer(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        created["id"],
    )
    before = (
        db_session.query(NegotiationEvent)
        .filter(NegotiationEvent.ride_id == created["id"])
        .count()
    )

    cancelled = authenticated_passenger["client"].put(
        f"/rides/{created['id']}/cancel",
        headers=authenticated_passenger["headers"],
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == RideStatus.CANCELLED_BY_PASSENGER

    db_session.expire_all()
    ride = db_session.get(RideRequest, created["id"])
    assert ride.status == RideStatus.CANCELLED_BY_PASSENGER
    open_count = (
        db_session.query(DriverResponse)
        .filter(
            DriverResponse.ride_id == created["id"],
            DriverResponse.status == DriverResponseStatus.OPEN,
        )
        .count()
    )
    assert open_count == 0
    withdrawn = (
        db_session.query(DriverResponse)
        .filter(
            DriverResponse.ride_id == created["id"],
            DriverResponse.status == DriverResponseStatus.WITHDRAWN,
        )
        .count()
    )
    assert withdrawn == 1
    assert _commission_count(db_session, created["id"]) == 0
    after = (
        db_session.query(NegotiationEvent)
        .filter(NegotiationEvent.ride_id == created["id"])
        .count()
    )
    assert after > before
    assert (
        db_session.query(NegotiationEvent)
        .filter(
            NegotiationEvent.ride_id == created["id"],
            NegotiationEvent.action == NegotiationAction.REQUEST_CANCELLED,
        )
        .count()
        == 1
    )

    second = authenticated_passenger["client"].post(
        "/rides/",
        headers=authenticated_passenger["headers"],
        json={
            "pickup_location": "Main Mall",
            "pickup_latitude": -24.6545,
            "pickup_longitude": 25.9086,
            "destination": "Airport Junction",
            "destination_latitude": -24.6278,
            "destination_longitude": 25.9059,
            "proposed_fare": 40.0,
        },
    )
    assert second.status_code == 200


def test_passenger_cancel_after_selection_before_start(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    selected = _advance_to(authenticated_passenger, authenticated_driver, "accepted")
    cancelled = authenticated_passenger["client"].put(
        f"/rides/{selected['id']}/cancel",
        headers=authenticated_passenger["headers"],
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == RideStatus.CANCELLED_BY_PASSENGER

    db_session.expire_all()
    ride = db_session.get(RideRequest, selected["id"])
    assert ride.status == RideStatus.CANCELLED_BY_PASSENGER
    assert ride.accepted_driver_id == authenticated_driver["user"].id
    driver = db_session.get(User, authenticated_driver["user"].id)
    assert driver.availability_status == "available"
    assert _commission_count(db_session, selected["id"]) == 0

    events = (
        db_session.query(NegotiationEvent)
        .filter(NegotiationEvent.ride_id == selected["id"])
        .order_by(NegotiationEvent.id.asc())
        .all()
    )
    assert any(
        event.action == NegotiationAction.FARE_AGREED for event in events
    )
    assert events[-1].action == NegotiationAction.REQUEST_CANCELLED


def test_passenger_cannot_cancel_after_start(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    selected = _advance_to(authenticated_passenger, authenticated_driver, "in_progress")
    cancelled = authenticated_passenger["client"].put(
        f"/rides/{selected['id']}/cancel",
        headers=authenticated_passenger["headers"],
    )
    assert cancelled.status_code == 400
    db_session.expire_all()
    assert (
        db_session.get(RideRequest, selected["id"]).status
        == RideStatus.IN_PROGRESS
    )
    assert _commission_count(db_session, selected["id"]) == 0


def test_passenger_cannot_cancel_completed_ride(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    selected = _advance_to(authenticated_passenger, authenticated_driver, "completed")
    cancelled = authenticated_passenger["client"].put(
        f"/rides/{selected['id']}/cancel",
        headers=authenticated_passenger["headers"],
    )
    assert cancelled.status_code == 400
    db_session.expire_all()
    assert (
        db_session.get(RideRequest, selected["id"]).status
        == RideStatus.COMPLETED
    )


# ---------------------------------------------------------------------------
# Driver withdraw / cancel
# ---------------------------------------------------------------------------


def test_driver_withdraw_pending_response(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    prepare_driver_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    created = create_pending_ride(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
    )
    driver_accept_passenger_offer(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        created["id"],
    )
    withdrawn = authenticated_driver["client"].put(
        f"/rides/{created['id']}/reject",
        headers=authenticated_driver["headers"],
    )
    assert withdrawn.status_code == 200

    db_session.expire_all()
    ride = db_session.get(RideRequest, created["id"])
    assert ride.status == RideStatus.PENDING
    response = (
        db_session.query(DriverResponse)
        .filter(
            DriverResponse.ride_id == created["id"],
            DriverResponse.driver_id == authenticated_driver["user"].id,
        )
        .one()
    )
    assert response.status == DriverResponseStatus.WITHDRAWN
    assert _commission_count(db_session, created["id"]) == 0


def test_driver_cancel_selected_ride_before_start(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    selected = _advance_to(authenticated_passenger, authenticated_driver, "accepted")
    cancelled = authenticated_driver["client"].put(
        f"/rides/{selected['id']}/cancel",
        headers=authenticated_driver["headers"],
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == RideStatus.CANCELLED_BY_DRIVER

    db_session.expire_all()
    ride = db_session.get(RideRequest, selected["id"])
    assert ride.status == RideStatus.CANCELLED_BY_DRIVER
    assert ride.accepted_driver_id == authenticated_driver["user"].id
    driver = db_session.get(User, authenticated_driver["user"].id)
    assert driver.availability_status == "available"
    assert _commission_count(db_session, selected["id"]) == 0

    history = authenticated_driver["client"].get(
        "/drivers/rides",
        headers=authenticated_driver["headers"],
    )
    assert history.status_code == 200
    assert any(item["id"] == selected["id"] for item in history.json())


def test_driver_cannot_cancel_after_start(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    selected = _advance_to(authenticated_passenger, authenticated_driver, "in_progress")
    cancelled = authenticated_driver["client"].put(
        f"/rides/{selected['id']}/cancel",
        headers=authenticated_driver["headers"],
    )
    assert cancelled.status_code == 400
    db_session.expire_all()
    assert (
        db_session.get(RideRequest, selected["id"]).status
        == RideStatus.IN_PROGRESS
    )


def test_driver_cannot_cancel_completed_ride(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    selected = _advance_to(authenticated_passenger, authenticated_driver, "completed")
    cancelled = authenticated_driver["client"].put(
        f"/rides/{selected['id']}/cancel",
        headers=authenticated_driver["headers"],
    )
    assert cancelled.status_code == 400
    db_session.expire_all()
    assert (
        db_session.get(RideRequest, selected["id"]).status
        == RideStatus.COMPLETED
    )


def test_passenger_and_driver_can_cancel_arriving_and_arrived(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    arriving = _advance_to(authenticated_passenger, authenticated_driver, "arriving")
    cancelled = authenticated_passenger["client"].put(
        f"/rides/{arriving['id']}/cancel",
        headers=authenticated_passenger["headers"],
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == RideStatus.CANCELLED_BY_PASSENGER
    assert _commission_count(db_session, arriving["id"]) == 0

    arrived = _advance_to(authenticated_passenger, authenticated_driver, "arrived")
    cancelled = authenticated_driver["client"].put(
        f"/rides/{arrived['id']}/cancel",
        headers=authenticated_driver["headers"],
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == RideStatus.CANCELLED_BY_DRIVER
    assert _commission_count(db_session, arrived["id"]) == 0


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


def test_selection_vs_cancellation_one_terminal_winner(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
    test_session_factory: sessionmaker,
):
    prepare_driver_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    created = create_pending_ride(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
    )
    driver_accept_passenger_offer(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        created["id"],
    )
    responses = list_responses(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        created["id"],
    )
    response_id = responses[0]["id"]
    ride_id = created["id"]
    passenger_id = authenticated_passenger["user"].id

    start_barrier = threading.Barrier(3)
    outcomes: dict[str, Any] = {
        "select": {"ok": False, "error": None},
        "cancel": {"ok": False, "error": None},
    }
    lock = threading.Lock()

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

    def _select() -> None:
        session = test_session_factory()
        try:
            user = session.get(User, passenger_id)
            start_barrier.wait()
            try:
                MarketplaceService.select_driver(
                    db=session,
                    ride_id=ride_id,
                    current_user=user,
                    response_id=response_id,
                )
                with lock:
                    outcomes["select"]["ok"] = True
            except Exception as exc:  # noqa: BLE001
                with lock:
                    outcomes["select"]["error"] = exc
                session.rollback()
        finally:
            session.close()

    def _cancel() -> None:
        session = test_session_factory()
        try:
            user = session.get(User, passenger_id)
            start_barrier.wait()
            try:
                RideService.cancel_ride(
                    db=session,
                    ride_id=ride_id,
                    current_user=user,
                )
                with lock:
                    outcomes["cancel"]["ok"] = True
            except Exception as exc:  # noqa: BLE001
                with lock:
                    outcomes["cancel"]["error"] = exc
                session.rollback()
        finally:
            session.close()

    threads = [
        threading.Thread(target=_blocker),
        threading.Thread(target=_select),
        threading.Thread(target=_cancel),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
        assert not thread.is_alive()

    assert outcomes["select"]["ok"] or outcomes["cancel"]["ok"], outcomes
    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride.status in (
        RideStatus.CANCELLED_BY_PASSENGER,
        RideStatus.ACCEPTED,
    )
    if outcomes["cancel"]["ok"]:
        assert ride.status == RideStatus.CANCELLED_BY_PASSENGER
    if ride.status == RideStatus.ACCEPTED:
        assert outcomes["select"]["ok"]
        assert not outcomes["cancel"]["ok"]
    assert _commission_count(db_session, ride_id) == 0
    if not outcomes["select"]["ok"]:
        err = outcomes["select"]["error"]
        assert isinstance(err, HTTPException)
        assert err.status_code == 400
    if not outcomes["cancel"]["ok"]:
        err = outcomes["cancel"]["error"]
        assert isinstance(err, HTTPException)
        assert err.status_code == 400


def test_cancellation_vs_start_one_terminal_winner(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
    test_session_factory: sessionmaker,
):
    selected = _advance_to(authenticated_passenger, authenticated_driver, "arrived")
    ride_id = selected["id"]
    passenger_id = authenticated_passenger["user"].id
    driver_id = authenticated_driver["user"].id

    start_barrier = threading.Barrier(3)
    outcomes: dict[str, Any] = {
        "start": {"ok": False, "error": None},
        "cancel": {"ok": False, "error": None},
    }
    lock = threading.Lock()

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

    def _worker(label: str, user_id: int, action) -> None:
        session = test_session_factory()
        try:
            user = session.get(User, user_id)
            start_barrier.wait()
            try:
                action(db=session, ride_id=ride_id, current_user=user)
                with lock:
                    outcomes[label]["ok"] = True
            except Exception as exc:  # noqa: BLE001
                with lock:
                    outcomes[label]["error"] = exc
                session.rollback()
        finally:
            session.close()

    threads = [
        threading.Thread(target=_blocker),
        threading.Thread(
            target=_worker,
            args=("start", driver_id, RideService.start_ride),
        ),
        threading.Thread(
            target=_worker,
            args=("cancel", passenger_id, RideService.cancel_ride),
        ),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
        assert not thread.is_alive()

    assert outcomes["start"]["ok"] or outcomes["cancel"]["ok"], outcomes
    db_session.expire_all()
    final = db_session.get(RideRequest, ride_id).status
    assert final in (RideStatus.IN_PROGRESS, RideStatus.CANCELLED_BY_PASSENGER)
    if outcomes["start"]["ok"]:
        assert final == RideStatus.IN_PROGRESS
        assert not outcomes["cancel"]["ok"]
    if outcomes["cancel"]["ok"]:
        assert final == RideStatus.CANCELLED_BY_PASSENGER
        assert not outcomes["start"]["ok"]
    assert _commission_count(db_session, ride_id) == 0


def test_cancellation_vs_completion_complete_wins(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
    test_session_factory: sessionmaker,
):
    selected = _advance_to(authenticated_passenger, authenticated_driver, "in_progress")
    ride_id = selected["id"]
    passenger_id = authenticated_passenger["user"].id
    driver_id = authenticated_driver["user"].id

    start_barrier = threading.Barrier(3)
    outcomes: dict[str, Any] = {
        "complete": {"ok": False, "error": None},
        "cancel": {"ok": False, "error": None},
    }
    lock = threading.Lock()

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

    def _worker(label: str, user_id: int, action) -> None:
        session = test_session_factory()
        try:
            user = session.get(User, user_id)
            start_barrier.wait()
            try:
                action(db=session, ride_id=ride_id, current_user=user)
                with lock:
                    outcomes[label]["ok"] = True
            except Exception as exc:  # noqa: BLE001
                with lock:
                    outcomes[label]["error"] = exc
                session.rollback()
        finally:
            session.close()

    threads = [
        threading.Thread(target=_blocker),
        threading.Thread(
            target=_worker,
            args=("complete", driver_id, RideService.complete_ride),
        ),
        threading.Thread(
            target=_worker,
            args=("cancel", passenger_id, RideService.cancel_ride),
        ),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
        assert not thread.is_alive()

    assert outcomes["complete"]["ok"]
    assert not outcomes["cancel"]["ok"]
    err = outcomes["cancel"]["error"]
    assert isinstance(err, HTTPException)
    assert err.status_code == 400

    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride.status == RideStatus.COMPLETED
    assert _commission_count(db_session, ride_id) == 1


# ---------------------------------------------------------------------------
# Wallet
# ---------------------------------------------------------------------------


def test_cancellation_creates_no_commission_after_selection(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    _set_wallet(db_session, authenticated_driver["user"].id, Decimal("40.00"))
    selected = _advance_to(authenticated_passenger, authenticated_driver, "accepted")
    cancelled = authenticated_passenger["client"].put(
        f"/rides/{selected['id']}/cancel",
        headers=authenticated_passenger["headers"],
    )
    assert cancelled.status_code == 200
    db_session.expire_all()
    assert _commission_count(db_session, selected["id"]) == 0
    wallet = (
        db_session.query(DriverWallet)
        .filter(DriverWallet.driver_id == authenticated_driver["user"].id)
        .one()
    )
    assert Decimal(str(wallet.available_balance)) == LAUNCH_SEED_AMOUNT


def test_incomplete_ride_creates_no_commission(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    selected = _advance_to(authenticated_passenger, authenticated_driver, "in_progress")
    db_session.expire_all()
    assert (
        db_session.get(RideRequest, selected["id"]).status
        == RideStatus.IN_PROGRESS
    )
    assert _commission_count(db_session, selected["id"]) == 0


def test_completed_ride_creates_exactly_one_eight_percent_commission(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    _set_wallet(db_session, authenticated_driver["user"].id, Decimal("40.00"))
    selected = advance_to_accepted(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        authenticated_driver["user"].id,
        payload={
            "pickup_location": "Main Mall",
            "pickup_latitude": -24.6545,
            "pickup_longitude": 25.9086,
            "destination": "Airport Junction",
            "destination_latitude": -24.6278,
            "destination_longitude": 25.9059,
            "proposed_fare": 40.0,
        },
    )
    _advance_lifecycle_from_accepted(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        selected["id"],
        complete=True,
    )
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


def test_wallet_can_fall_after_commission_and_still_operate_when_positive(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    _set_wallet(db_session, authenticated_driver["user"].id, Decimal("40.00"))
    selected = advance_to_accepted(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        authenticated_driver["user"].id,
        payload={
            "pickup_location": "Main Mall",
            "pickup_latitude": -24.6545,
            "pickup_longitude": 25.9086,
            "destination": "Airport Junction",
            "destination_latitude": -24.6278,
            "destination_longitude": 25.9059,
            "proposed_fare": 40.0,
        },
    )
    _advance_lifecycle_from_accepted(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        selected["id"],
        complete=True,
    )
    db_session.expire_all()
    wallet = (
        db_session.query(DriverWallet)
        .filter(DriverWallet.driver_id == authenticated_driver["user"].id)
        .one()
    )
    assert Decimal(str(wallet.available_balance)) == Decimal("36.80")
    assert (
        db_session.get(RideRequest, selected["id"]).status
        == RideStatus.COMPLETED
    )
    assert (
        db_session.get(User, authenticated_driver["user"].id).availability_status
        == "available"
    )

    blocked = authenticated_driver["client"].put(
        "/drivers/go-online",
        headers=authenticated_driver["headers"],
    )
    assert blocked.status_code == 200, blocked.text


def _advance_lifecycle_from_accepted(client, headers, ride_id: int, complete: bool) -> None:
    assert client.put(f"/rides/{ride_id}/arrive", headers=headers).status_code == 200
    assert client.put(
        f"/rides/{ride_id}/driver-arrived",
        headers=headers,
    ).status_code == 200
    assert client.put(f"/rides/{ride_id}/start", headers=headers).status_code == 200
    if complete:
        assert client.put(
            f"/rides/{ride_id}/complete",
            headers=headers,
        ).status_code == 200
