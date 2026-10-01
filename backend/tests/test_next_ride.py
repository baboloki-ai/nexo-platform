"""Next Ride 1.0: one accepted future ride while current is in_progress."""
from __future__ import annotations

import threading
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.constants.ride_status import RideStatus
from app.constants.wallet import WalletEntryType
from app.models.passenger import Passenger
from app.models.ride_request import RideRequest
from app.models.user import User
from app.models.wallet_ledger_entry import WalletLedgerEntry
from app.services.next_ride_service import NextRideService
from app.utils.jwt import create_access_token
from app.utils.money import calculate_commission
from app.utils.security import hash_password
from tests.ride_flow import (
    RIDE_CREATE_PAYLOAD,
    accept_next_ride,
    advance_to_accepted,
    advance_to_in_progress,
    create_pending_ride,
    driver_accept_passenger_offer,
    list_responses,
    passenger_select_response,
    prepare_driver_online,
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


def _create_passenger(
    db_session: Session,
    *,
    full_name: str,
    phone_number: str,
    email: str,
    profile_phone: str,
    profile_email: str,
) -> tuple[User, Passenger, dict[str, str]]:
    user = User(
        full_name=full_name,
        phone_number=phone_number,
        email=email,
        password=hash_password("TestPassengerB123!"),
        role="passenger",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    profile = Passenger(
        user_id=user.id,
        first_name="Next",
        last_name="Passenger",
        phone=profile_phone,
        email=profile_email,
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)
    return user, profile, _auth_headers(user)


def _commission_entries(db_session: Session, driver_id: int) -> list[WalletLedgerEntry]:
    return (
        db_session.query(WalletLedgerEntry)
        .filter(
            WalletLedgerEntry.driver_id == driver_id,
            WalletLedgerEntry.entry_type == WalletEntryType.COMMISSION,
        )
        .all()
    )


def test_in_progress_driver_can_accept_one_next_ride(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
    driver_user: User,
):
    current = advance_to_in_progress(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        driver_user.id,
    )
    _user_b, passenger_b, headers_b = _create_passenger(
        db_session,
        full_name="Passenger B Next",
        phone_number="+15550006101",
        email="next.passenger.b@test.nexo",
        profile_phone="+15550006102",
        profile_email="next.passenger.b.profile@test.nexo",
    )
    pending = create_pending_ride(
        authenticated_passenger["client"],
        headers_b,
    )

    accepted = accept_next_ride(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        pending["id"],
    )

    db_session.expire_all()
    current_row = db_session.get(RideRequest, current["id"])
    next_row = db_session.get(RideRequest, accepted["id"])
    driver_row = db_session.get(User, driver_user.id)

    assert current_row is not None
    assert current_row.status == RideStatus.IN_PROGRESS
    assert current_row.is_next_ride is False
    assert current_row.accepted_driver_id == driver_user.id

    assert next_row is not None
    assert next_row.status == RideStatus.ACCEPTED
    assert next_row.is_next_ride is True
    assert next_row.accepted_driver_id == driver_user.id
    assert next_row.passenger_id == passenger_b.id
    assert next_row.agreed_fare is not None

    assert driver_row.availability_status == "busy"
    assert accepted["status"] == RideStatus.ACCEPTED
    assert accepted["is_next_ride"] is True
    assert _commission_entries(db_session, driver_user.id) == []


def test_driver_cannot_accept_second_next_ride(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
    driver_user: User,
):
    advance_to_in_progress(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        driver_user.id,
    )
    _user_b, _passenger_b, headers_b = _create_passenger(
        db_session,
        full_name="Passenger B Second Next",
        phone_number="+15550006111",
        email="next.passenger.b2@test.nexo",
        profile_phone="+15550006112",
        profile_email="next.passenger.b2.profile@test.nexo",
    )
    _user_c, _passenger_c, headers_c = _create_passenger(
        db_session,
        full_name="Passenger C Second Next",
        phone_number="+15550006113",
        email="next.passenger.c2@test.nexo",
        profile_phone="+15550006114",
        profile_email="next.passenger.c2.profile@test.nexo",
    )
    first_pending = create_pending_ride(
        authenticated_passenger["client"],
        headers_b,
    )
    second_pending = create_pending_ride(
        authenticated_passenger["client"],
        headers_c,
        payload={
            **RIDE_CREATE_PAYLOAD,
            "pickup_location": "Second Next Pickup",
        },
    )
    first = accept_next_ride(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        first_pending["id"],
    )
    second = authenticated_driver["client"].put(
        f"/rides/{second_pending['id']}/accept-next",
        headers=authenticated_driver["headers"],
    )
    assert second.status_code == 400
    assert second.json()["detail"] == "Driver already has a Next Ride."

    db_session.expire_all()
    first_row = db_session.get(RideRequest, first["id"])
    second_row = db_session.get(RideRequest, second_pending["id"])
    assert first_row is not None
    assert first_row.status == RideStatus.ACCEPTED
    assert first_row.is_next_ride is True
    assert first_row.accepted_driver_id == driver_user.id
    assert second_row is not None
    assert second_row.status == RideStatus.PENDING
    assert second_row.accepted_driver_id is None
    assert second_row.is_next_ride is False


def test_concurrent_next_ride_accept_results_in_one(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
    test_session_factory: sessionmaker,
    driver_user: User,
):
    advance_to_in_progress(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        driver_user.id,
    )
    _user_b, _passenger_b, headers_b = _create_passenger(
        db_session,
        full_name="Passenger B Concurrent Next",
        phone_number="+15550006121",
        email="next.passenger.b.conc@test.nexo",
        profile_phone="+15550006122",
        profile_email="next.passenger.b.conc.profile@test.nexo",
    )
    _user_c, _passenger_c, headers_c = _create_passenger(
        db_session,
        full_name="Passenger C Concurrent Next",
        phone_number="+15550006123",
        email="next.passenger.c.conc@test.nexo",
        profile_phone="+15550006124",
        profile_email="next.passenger.c.conc.profile@test.nexo",
    )
    first_pending = create_pending_ride(
        authenticated_passenger["client"],
        headers_b,
    )
    second_pending = create_pending_ride(
        authenticated_passenger["client"],
        headers_c,
        payload={
            **RIDE_CREATE_PAYLOAD,
            "pickup_location": "Concurrent Next Pickup",
        },
    )
    errors: list[Exception] = []
    accepted: list[int] = []

    def _accept(target_ride_id: int) -> None:
        session = test_session_factory()
        try:
            ride = NextRideService.accept_next_ride(
                db=session,
                ride_id=target_ride_id,
                current_user=session.get(User, driver_user.id),
            )
            accepted.append(ride.id)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            session.close()

    threads = [
        threading.Thread(target=_accept, args=(first_pending["id"],)),
        threading.Thread(target=_accept, args=(second_pending["id"],)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(accepted) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], HTTPException)
    assert errors[0].status_code == 400
    assert errors[0].detail == "Driver already has a Next Ride."

    db_session.expire_all()
    next_rows = (
        db_session.query(RideRequest)
        .filter(
            RideRequest.accepted_driver_id == driver_user.id,
            RideRequest.is_next_ride.is_(True),
        )
        .all()
    )
    assert len(next_rows) == 1
    assert next_rows[0].status == RideStatus.ACCEPTED
    assert next_rows[0].id == accepted[0]


def test_driver_without_in_progress_cannot_use_next_ride_flow(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
    driver_user: User,
):
    prepare_driver_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    pending = create_pending_ride(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
    )
    no_current = authenticated_driver["client"].put(
        f"/rides/{pending['id']}/accept-next",
        headers=authenticated_driver["headers"],
    )
    assert no_current.status_code == 400
    assert no_current.json()["detail"] == (
        "Next Ride can only be accepted during an in-progress ride."
    )

    driver_accept_passenger_offer(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        pending["id"],
    )
    responses = list_responses(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        pending["id"],
    )
    match = next(
        item for item in responses
        if item["driver_id"] == driver_user.id and item["status"] == "open"
    )
    assigned = passenger_select_response(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        pending["id"],
        match["id"],
    )
    _user_b, _passenger_b, headers_b = _create_passenger(
        db_session,
        full_name="Passenger B No In Progress",
        phone_number="+15550006131",
        email="next.passenger.b.noip@test.nexo",
        profile_phone="+15550006132",
        profile_email="next.passenger.b.noip.profile@test.nexo",
    )
    future = create_pending_ride(
        authenticated_passenger["client"],
        headers_b,
    )
    accepted_only = authenticated_driver["client"].put(
        f"/rides/{future['id']}/accept-next",
        headers=authenticated_driver["headers"],
    )
    assert accepted_only.status_code == 400
    assert accepted_only.json()["detail"] == (
        "Next Ride can only be accepted during an in-progress ride."
    )

    db_session.expire_all()
    current_row = db_session.get(RideRequest, assigned["id"])
    future_row = db_session.get(RideRequest, future["id"])
    assert current_row.status == RideStatus.ACCEPTED
    assert current_row.is_next_ride is False
    assert future_row.status == RideStatus.PENDING
    assert future_row.accepted_driver_id is None


def test_passenger_b_is_not_started_or_completed_early(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
    driver_user: User,
):
    current = advance_to_in_progress(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        driver_user.id,
    )
    _user_b, passenger_b, headers_b = _create_passenger(
        db_session,
        full_name="Passenger B Visibility",
        phone_number="+15550006141",
        email="next.passenger.b.vis@test.nexo",
        profile_phone="+15550006142",
        profile_email="next.passenger.b.vis.profile@test.nexo",
    )
    pending = create_pending_ride(
        authenticated_passenger["client"],
        headers_b,
    )
    accepted = accept_next_ride(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        pending["id"],
    )

    trip = authenticated_passenger["client"].get(
        f"/trips/{accepted['id']}",
        headers=headers_b,
    )
    assert trip.status_code == 200, trip.text
    body = trip.json()
    assert body["status"] == RideStatus.ACCEPTED
    assert body["is_next_ride"] is True
    assert body["accepted_driver_id"] == driver_user.id
    assert body["passenger_id"] == passenger_b.id
    assert body["status"] not in {
        RideStatus.IN_PROGRESS,
        RideStatus.COMPLETED,
        RideStatus.DRIVER_ARRIVED,
        RideStatus.DRIVER_ARRIVING,
    }

    arrive_next = authenticated_driver["client"].put(
        f"/rides/{accepted['id']}/arrive",
        headers=authenticated_driver["headers"],
    )
    assert arrive_next.status_code == 400

    complete_current = authenticated_driver["client"].put(
        f"/rides/{current['id']}/complete",
        headers=authenticated_driver["headers"],
    )
    assert complete_current.status_code == 200
    assert complete_current.json()["status"] == RideStatus.COMPLETED

    db_session.expire_all()
    next_row = db_session.get(RideRequest, accepted["id"])
    current_row = db_session.get(RideRequest, current["id"])
    assert current_row.status == RideStatus.COMPLETED
    assert next_row.status == RideStatus.ACCEPTED
    assert next_row.is_next_ride is False

    trip_after = authenticated_passenger["client"].get(
        f"/trips/{accepted['id']}",
        headers=headers_b,
    )
    assert trip_after.status_code == 200
    after = trip_after.json()
    assert after["status"] == RideStatus.ACCEPTED
    assert after["is_next_ride"] is False
    assert after["status"] != RideStatus.IN_PROGRESS
    assert after["status"] != RideStatus.COMPLETED


def test_current_completion_commissions_only_current_ride(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
    driver_user: User,
):
    current = advance_to_in_progress(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        driver_user.id,
    )
    _user_b, _passenger_b, headers_b = _create_passenger(
        db_session,
        full_name="Passenger B Commission",
        phone_number="+15550006151",
        email="next.passenger.b.com@test.nexo",
        profile_phone="+15550006152",
        profile_email="next.passenger.b.com.profile@test.nexo",
    )
    pending = create_pending_ride(
        authenticated_passenger["client"],
        headers_b,
    )
    accepted = accept_next_ride(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        pending["id"],
    )
    assert _commission_entries(db_session, driver_user.id) == []

    complete = authenticated_driver["client"].put(
        f"/rides/{current['id']}/complete",
        headers=authenticated_driver["headers"],
    )
    assert complete.status_code == 200
    assert complete.json()["id"] == current["id"]
    assert complete.json()["status"] == RideStatus.COMPLETED

    db_session.expire_all()
    entries = _commission_entries(db_session, driver_user.id)
    assert len(entries) == 1
    assert entries[0].ride_id == current["id"]
    expected = calculate_commission(Decimal(str(RIDE_CREATE_PAYLOAD["proposed_fare"])))
    assert Decimal(str(abs(entries[0].amount))) == expected

    next_row = db_session.get(RideRequest, accepted["id"])
    assert next_row.status == RideStatus.ACCEPTED
    assert next_row.is_next_ride is False
    next_commission = (
        db_session.query(WalletLedgerEntry)
        .filter(
            WalletLedgerEntry.ride_id == accepted["id"],
            WalletLedgerEntry.entry_type == WalletEntryType.COMMISSION,
        )
        .first()
    )
    assert next_commission is None

    driver_row = db_session.get(User, driver_user.id)
    assert driver_row.availability_status == "busy"


def test_normal_acceptance_flow_is_unchanged(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
    driver_user: User,
):
    selected = advance_to_accepted(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        driver_user.id,
    )
    db_session.expire_all()
    ride = db_session.get(RideRequest, selected["id"])
    driver = db_session.get(User, driver_user.id)
    assert ride.status == RideStatus.ACCEPTED
    assert ride.is_next_ride is False
    assert ride.accepted_driver_id == driver_user.id
    assert driver.availability_status == "busy"


def test_driver_cannot_have_more_than_one_accepted_next_ride(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
    driver_user: User,
):
    advance_to_in_progress(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        driver_user.id,
    )
    extras: list[dict[str, Any]] = []
    for index in range(3):
        _user, _profile, headers = _create_passenger(
            db_session,
            full_name=f"Passenger Next Limit {index}",
            phone_number=f"+1555000616{index}",
            email=f"next.limit.{index}@test.nexo",
            profile_phone=f"+1555000617{index}",
            profile_email=f"next.limit.{index}.profile@test.nexo",
        )
        extras.append(
            create_pending_ride(
                authenticated_passenger["client"],
                headers,
                payload={
                    **RIDE_CREATE_PAYLOAD,
                    "pickup_location": f"Limit pickup {index}",
                },
            )
        )

    first = accept_next_ride(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        extras[0]["id"],
    )
    for pending in extras[1:]:
        response = authenticated_driver["client"].put(
            f"/rides/{pending['id']}/accept-next",
            headers=authenticated_driver["headers"],
        )
        assert response.status_code == 400

    db_session.expire_all()
    next_rows = (
        db_session.query(RideRequest)
        .filter(
            RideRequest.accepted_driver_id == driver_user.id,
            RideRequest.is_next_ride.is_(True),
        )
        .all()
    )
    assert [row.id for row in next_rows] == [first["id"]]
