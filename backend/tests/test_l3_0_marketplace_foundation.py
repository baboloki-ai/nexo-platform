"""
L3.0 Marketplace Foundation: passenger offers, driver responses,
negotiation history, agreed fare, CAS, and WebSocket contracts.
"""
from __future__ import annotations

import threading
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker

from app.constants.driver_response import DriverResponseStatus, DriverResponseType
from app.constants.negotiation import NegotiationAction
from app.constants.ride_messages import DRIVER_ON_THE_WAY
from app.constants.ride_status import RideStatus
from app.models.driver_response import DriverResponse
from app.models.driver_wallet import DriverWallet
from app.models.negotiation_event import NegotiationEvent
from app.models.ride_request import RideRequest
from app.models.user import User
from app.models.vehicle import Vehicle
from app.services.marketplace_service import MarketplaceService
from app.services.wallet_service import WalletService
from app.utils.jwt import create_access_token
from app.utils.money import generate_counter_offer_amounts
from app.utils.security import hash_password
from tests.ride_flow import (
    DRIVER_LOCATION_PAYLOAD,
    RIDE_CREATE_PAYLOAD,
    advance_to_accepted,
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


@pytest.fixture
def second_driver_user(db_session: Session) -> User:
    user = User(
        full_name="Second Marketplace Driver",
        phone_number="+15550001002",
        email="driver.two@test.nexo",
        password=hash_password("TestDriverTwo123!"),
        role="driver",
        verification_status="approved",
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
            make="Toyota",
            model="Corolla",
            year=2021,
            color="White",
            registration_number="B413SEC",
            vehicle_type="sedan",
            verification_status="approved",
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


def _open_request(
    authenticated_passenger,
    authenticated_driver,
    payload=None,
):
    prepare_driver_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    return create_pending_ride(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        payload=payload,
    )


def test_minimum_offer_p20_rejected_below(authenticated_passenger):
    payload = {**RIDE_CREATE_PAYLOAD, "proposed_fare": 19.99}
    response = authenticated_passenger["client"].post(
        "/rides/",
        headers=authenticated_passenger["headers"],
        json=payload,
    )
    assert response.status_code in (400, 422)


def test_minimum_offer_p20_accepted_at_floor(
    authenticated_passenger,
    authenticated_driver,
):
    payload = {**RIDE_CREATE_PAYLOAD, "proposed_fare": 20.00}
    created = _open_request(
        authenticated_passenger,
        authenticated_driver,
        payload=payload,
    )
    assert created["status"] == "pending"
    assert created["passenger_current_offer"] == 20.0
    assert created["proposed_fare"] == 20.0
    assert created["agreed_fare"] is None
    assert created["accepted_driver_id"] is None
    assert created["passenger_offer_version"] == 1


def test_no_maximum_fare(
    authenticated_passenger,
    authenticated_driver,
):
    payload = {**RIDE_CREATE_PAYLOAD, "proposed_fare": 500.00}
    created = _open_request(
        authenticated_passenger,
        authenticated_driver,
        payload=payload,
    )
    assert created["passenger_current_offer"] == 500.0


def test_create_does_not_auto_assign_nearest_driver(
    authenticated_passenger,
    authenticated_driver,
    authenticated_second_driver,
    db_session,
):
    prepare_driver_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    prepare_driver_online(
        authenticated_second_driver["client"],
        authenticated_second_driver["headers"],
    )
    created = create_pending_ride(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
    )
    db_session.expire_all()
    ride = db_session.get(RideRequest, created["id"])
    assert ride.status == RideStatus.PENDING
    assert ride.accepted_driver_id is None
    assert db_session.query(DriverResponse).filter_by(ride_id=ride.id).count() == 0


def test_passenger_increase_and_maintain(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    created = _open_request(authenticated_passenger, authenticated_driver)
    ride_id = created["id"]
    client = authenticated_passenger["client"]
    headers = authenticated_passenger["headers"]

    increased = client.put(
        f"/rides/{ride_id}/offer",
        headers=headers,
        json={"action": "increase", "amount": 160.0},
    )
    assert increased.status_code == 200
    body = increased.json()
    assert body["passenger_current_offer"] == 160.0
    assert body["passenger_offer_version"] == 2
    assert body["proposed_fare"] == 160.0

    decrease = client.put(
        f"/rides/{ride_id}/offer",
        headers=headers,
        json={"action": "increase", "amount": 155.0},
    )
    assert decrease.status_code == 400

    maintained = client.put(
        f"/rides/{ride_id}/offer",
        headers=headers,
        json={"action": "maintain"},
    )
    assert maintained.status_code == 200
    assert maintained.json()["passenger_current_offer"] == 160.0
    assert maintained.json()["passenger_offer_version"] == 3

    db_session.expire_all()
    events = (
        db_session.query(NegotiationEvent)
        .filter(NegotiationEvent.ride_id == ride_id)
        .order_by(NegotiationEvent.id.asc())
        .all()
    )
    actions = [event.action for event in events]
    assert NegotiationAction.PASSENGER_OFFER_CREATED in actions
    assert NegotiationAction.PASSENGER_OFFER_INCREASED in actions
    assert NegotiationAction.PASSENGER_OFFER_MAINTAINED in actions


def test_driver_accept_does_not_assign_or_reserve(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    created = _open_request(authenticated_passenger, authenticated_driver)
    ride_id = created["id"]
    driver_accept_passenger_offer(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        ride_id,
    )
    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    driver = db_session.get(User, authenticated_driver["user"].id)
    assert ride.status == RideStatus.PENDING
    assert ride.accepted_driver_id is None
    assert ride.agreed_fare is None
    assert driver.availability_status == "available"
    response = (
        db_session.query(DriverResponse)
        .filter(
            DriverResponse.ride_id == ride_id,
            DriverResponse.driver_id == driver.id,
        )
        .one()
    )
    assert response.response_type == DriverResponseType.ACCEPT_PASSENGER_OFFER
    assert response.status == DriverResponseStatus.OPEN
    assert Decimal(str(response.amount)) == Decimal("150.00")


def test_driver_counter_uses_generated_amounts_only(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    created = _open_request(authenticated_passenger, authenticated_driver)
    ride_id = created["id"]
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]

    options = driver_client.get(
        f"/rides/{ride_id}/counter-options",
        headers=driver_headers,
    )
    assert options.status_code == 200
    amounts = options.json()["amounts"]
    expected = [float(value) for value in generate_counter_offer_amounts(150)]
    assert amounts == expected

    custom = driver_client.put(
        f"/rides/{ride_id}/respond",
        headers=driver_headers,
        json={"response_type": "counter_offer", "amount": 199.00},
    )
    assert custom.status_code == 400

    chosen = amounts[1]
    countered = driver_client.put(
        f"/rides/{ride_id}/respond",
        headers=driver_headers,
        json={"response_type": "counter_offer", "amount": chosen},
    )
    assert countered.status_code == 200
    assert countered.json()["passenger_current_offer"] == 150.0
    assert countered.json()["accepted_driver_id"] is None

    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert Decimal(str(ride.passenger_current_offer)) == Decimal("150.00")
    response = (
        db_session.query(DriverResponse)
        .filter(DriverResponse.ride_id == ride_id)
        .one()
    )
    assert response.response_type == DriverResponseType.COUNTER_OFFER
    assert float(response.amount) == chosen


def test_multiple_open_driver_responses(
    authenticated_passenger,
    authenticated_driver,
    authenticated_second_driver,
):
    created = _open_request(authenticated_passenger, authenticated_driver)
    prepare_driver_online(
        authenticated_second_driver["client"],
        authenticated_second_driver["headers"],
    )
    ride_id = created["id"]
    driver_accept_passenger_offer(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        ride_id,
    )
    authenticated_second_driver["client"].put(
        f"/rides/{ride_id}/respond",
        headers=authenticated_second_driver["headers"],
        json={"response_type": "counter_offer", "amount": 155.0},
    )
    responses = list_responses(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        ride_id,
    )
    assert len(responses) == 2
    assert {item["status"] for item in responses} == {"open"}
    assert {item["driver_id"] for item in responses} == {
        authenticated_driver["user"].id,
        authenticated_second_driver["user"].id,
    }


def test_passenger_select_locks_agreed_fare_and_closes_losers(
    authenticated_passenger,
    authenticated_driver,
    authenticated_second_driver,
    db_session,
):
    created = _open_request(authenticated_passenger, authenticated_driver)
    prepare_driver_online(
        authenticated_second_driver["client"],
        authenticated_second_driver["headers"],
    )
    ride_id = created["id"]
    driver_accept_passenger_offer(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        ride_id,
    )
    authenticated_second_driver["client"].put(
        f"/rides/{ride_id}/respond",
        headers=authenticated_second_driver["headers"],
        json={"response_type": "counter_offer", "amount": 155.0},
    )
    responses = list_responses(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        ride_id,
    )
    winner = next(
        item for item in responses
        if item["driver_id"] == authenticated_second_driver["user"].id
    )
    selected = passenger_select_response(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        ride_id,
        winner["id"],
    )
    assert selected["status"] == "accepted"
    assert selected["accepted_driver_id"] == authenticated_second_driver["user"].id
    assert selected["agreed_fare"] == 155.0

    immutable = authenticated_passenger["client"].put(
        f"/rides/{ride_id}/offer",
        headers=authenticated_passenger["headers"],
        json={"action": "increase", "amount": 170.0},
    )
    assert immutable.status_code == 400

    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride.agreed_fare is not None
    assert Decimal(str(ride.agreed_fare)) == Decimal("155.00")
    rows = db_session.query(DriverResponse).filter_by(ride_id=ride_id).all()
    statuses = {row.driver_id: row.status for row in rows}
    assert statuses[authenticated_second_driver["user"].id] == DriverResponseStatus.SELECTED
    assert statuses[authenticated_driver["user"].id] == DriverResponseStatus.CLOSED_LOSER
    winner_user = db_session.get(User, authenticated_second_driver["user"].id)
    loser_user = db_session.get(User, authenticated_driver["user"].id)
    assert winner_user.availability_status == "busy"
    assert loser_user.availability_status == "available"


def test_two_drivers_accept_concurrently_both_open(
    authenticated_passenger,
    authenticated_driver,
    authenticated_second_driver,
    db_session,
    test_session_factory: sessionmaker,
):
    created = _open_request(authenticated_passenger, authenticated_driver)
    prepare_driver_online(
        authenticated_second_driver["client"],
        authenticated_second_driver["headers"],
    )
    ride_id = created["id"]
    errors: list[Exception] = []

    def _respond(driver: User) -> None:
        session = test_session_factory()
        try:
            MarketplaceService.driver_respond(
                db=session,
                ride_id=ride_id,
                current_user=session.get(User, driver.id),
                response_type=DriverResponseType.ACCEPT_PASSENGER_OFFER,
                amount=None,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            session.close()

    first = threading.Thread(target=_respond, args=(authenticated_driver["user"],))
    second = threading.Thread(
        target=_respond,
        args=(authenticated_second_driver["user"],),
    )
    first.start()
    second.start()
    first.join()
    second.join()
    assert errors == []
    db_session.expire_all()
    rows = (
        db_session.query(DriverResponse)
        .filter(
            DriverResponse.ride_id == ride_id,
            DriverResponse.status == DriverResponseStatus.OPEN,
        )
        .all()
    )
    assert len(rows) == 2
    ride = db_session.get(RideRequest, ride_id)
    assert ride.status == RideStatus.PENDING
    assert ride.accepted_driver_id is None


def test_selection_beats_late_driver_response(
    authenticated_passenger,
    authenticated_driver,
    authenticated_second_driver,
    db_session,
):
    created = _open_request(authenticated_passenger, authenticated_driver)
    ride_id = created["id"]
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
    winner_id = responses[0]["id"]
    passenger_select_response(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        ride_id,
        winner_id,
    )
    prepare_driver_online(
        authenticated_second_driver["client"],
        authenticated_second_driver["headers"],
    )
    late = authenticated_second_driver["client"].put(
        f"/rides/{ride_id}/respond",
        headers=authenticated_second_driver["headers"],
        json={"response_type": "accept_passenger_offer"},
    )
    assert late.status_code == 400
    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride.accepted_driver_id == authenticated_driver["user"].id


def test_increase_preserves_driver_response_snapshot(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    created = _open_request(authenticated_passenger, authenticated_driver)
    ride_id = created["id"]
    driver_accept_passenger_offer(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        ride_id,
    )
    authenticated_passenger["client"].put(
        f"/rides/{ride_id}/offer",
        headers=authenticated_passenger["headers"],
        json={"action": "increase", "amount": 170.0},
    )
    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    response = (
        db_session.query(DriverResponse)
        .filter(DriverResponse.ride_id == ride_id)
        .one()
    )
    assert Decimal(str(ride.passenger_current_offer)) == Decimal("170.00")
    assert Decimal(str(response.amount)) == Decimal("150.00")
    assert Decimal(str(response.passenger_offer_amount_at_submit)) == Decimal("150.00")
    assert response.status == DriverResponseStatus.OPEN
    assert ride.passenger_offer_version == 2


def test_two_passenger_actions_one_version_wins(
    authenticated_passenger,
    authenticated_driver,
    db_session,
    test_session_factory: sessionmaker,
):
    created = _open_request(authenticated_passenger, authenticated_driver)
    ride_id = created["id"]
    user = authenticated_passenger["user"]
    outcomes: list[str] = []

    def _increase(amount: float) -> None:
        session = test_session_factory()
        try:
            MarketplaceService.update_passenger_offer(
                db=session,
                ride_id=ride_id,
                current_user=session.get(User, user.id),
                action="increase",
                amount=Decimal(str(amount)),
                passenger_offer_version=1,
            )
            outcomes.append("ok")
        except Exception:
            outcomes.append("fail")
        finally:
            session.close()

    threads = [
        threading.Thread(target=_increase, args=(160.0,)),
        threading.Thread(target=_increase, args=(165.0,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert outcomes.count("ok") == 1
    assert outcomes.count("fail") == 1
    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride.passenger_offer_version == 2
    assert Decimal(str(ride.passenger_current_offer)) in (
        Decimal("160.00"),
        Decimal("165.00"),
    )


def test_expire_vs_select_single_winner(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    created = _open_request(authenticated_passenger, authenticated_driver)
    ride_id = created["id"]
    driver_accept_passenger_offer(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        ride_id,
    )
    response = (
        db_session.query(DriverResponse)
        .filter(DriverResponse.ride_id == ride_id)
        .one()
    )
    expired = MarketplaceService.expire_open_response(db_session, response.id)
    assert expired is True
    select = authenticated_passenger["client"].put(
        f"/rides/{ride_id}/select",
        headers=authenticated_passenger["headers"],
        json={"response_id": response.id},
    )
    assert select.status_code == 400
    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride.status == RideStatus.PENDING
    assert ride.agreed_fare is None


def test_cancel_vs_driver_response(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    created = _open_request(authenticated_passenger, authenticated_driver)
    ride_id = created["id"]
    cancelled = authenticated_passenger["client"].put(
        f"/rides/{ride_id}/cancel",
        headers=authenticated_passenger["headers"],
    )
    assert cancelled.status_code == 200
    late = authenticated_driver["client"].put(
        f"/rides/{ride_id}/respond",
        headers=authenticated_driver["headers"],
        json={"response_type": "accept_passenger_offer"},
    )
    assert late.status_code == 400
    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride.status == RideStatus.CANCELLED_BY_PASSENGER


def test_driver_isolation_of_counters(
    authenticated_passenger,
    authenticated_driver,
    authenticated_second_driver,
):
    created = _open_request(authenticated_passenger, authenticated_driver)
    prepare_driver_online(
        authenticated_second_driver["client"],
        authenticated_second_driver["headers"],
    )
    ride_id = created["id"]
    driver_accept_passenger_offer(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        ride_id,
    )
    authenticated_second_driver["client"].put(
        f"/rides/{ride_id}/respond",
        headers=authenticated_second_driver["headers"],
        json={"response_type": "counter_offer", "amount": 155.0},
    )
    first = list_responses(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        ride_id,
    )
    second = list_responses(
        authenticated_second_driver["client"],
        authenticated_second_driver["headers"],
        ride_id,
    )
    assert len(first) == 1
    assert first[0]["driver_id"] == authenticated_driver["user"].id
    assert len(second) == 1
    assert second[0]["driver_id"] == authenticated_second_driver["user"].id
    assert second[0]["amount"] == 155.0


def test_passenger_isolation_of_trips(
    authenticated_passenger,
    authenticated_driver,
    client: TestClient,
    db_session: Session,
):
    other = User(
        full_name="Other Passenger",
        phone_number="+15550001999",
        email="other.passenger@test.nexo",
        password=hash_password("OtherPassenger123!"),
        role="passenger",
    )
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    created = _open_request(authenticated_passenger, authenticated_driver)
    other_headers = _auth_headers(other)
    trip = client.get(f"/trips/{created['id']}", headers=other_headers)
    assert trip.status_code == 403
    responses = client.get(
        f"/rides/{created['id']}/responses",
        headers=other_headers,
    )
    assert responses.status_code == 403


def test_websocket_events_include_version_and_event_id(
    authenticated_passenger,
    authenticated_driver,
):
    with patch(
        "app.services.notification_service.NotificationService.notify_marketplace_request_created"
    ) as created_event, patch(
        "app.services.notification_service.NotificationService.notify_driver_response_received"
    ) as received_event, patch(
        "app.services.notification_service.NotificationService.notify_ride_agreed"
    ) as agreed_event:
        selected = advance_to_accepted(
            authenticated_passenger["client"],
            authenticated_passenger["headers"],
            authenticated_driver["client"],
            authenticated_driver["headers"],
            authenticated_driver["user"].id,
        )
        assert selected["agreed_fare"] == 150.0
        assert created_event.called
        created_kwargs = created_event.call_args.kwargs
        assert created_kwargs["passenger_offer_version"] == 1
        assert created_kwargs["event_id"]
        assert received_event.called
        received_kwargs = received_event.call_args.kwargs
        assert received_kwargs["passenger_offer_version"] == 1
        assert received_kwargs["event_id"]
        assert agreed_event.called
        agreed_kwargs = agreed_event.call_args.kwargs
        assert agreed_kwargs["agreed_fare"] == 150.0
        assert agreed_kwargs["event_id"]


def test_two_passengers_cannot_select_same_driver(
    authenticated_passenger,
    authenticated_driver,
    client: TestClient,
    db_session: Session,
):
    second_user = User(
        full_name="Passenger Two",
        phone_number="+15550001888",
        email="passenger.two@test.nexo",
        password=hash_password("PassengerTwo123!"),
        role="passenger",
    )
    db_session.add(second_user)
    db_session.commit()
    db_session.refresh(second_user)
    from app.models.passenger import Passenger

    second_profile = Passenger(
        user_id=second_user.id,
        first_name="Two",
        last_name="Passenger",
        phone="+15550001889",
        email="passenger.two.profile@test.nexo",
    )
    db_session.add(second_profile)
    db_session.commit()
    second_headers = _auth_headers(second_user)

    first = _open_request(authenticated_passenger, authenticated_driver)
    second = create_pending_ride(client, second_headers)
    driver_accept_passenger_offer(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        first["id"],
    )
    driver_accept_passenger_offer(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        second["id"],
    )
    first_responses = list_responses(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        first["id"],
    )
    selected = passenger_select_response(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        first["id"],
        first_responses[0]["id"],
    )
    assert selected["accepted_driver_id"] == authenticated_driver["user"].id
    second_responses = list_responses(client, second_headers, second["id"])
    conflict = client.put(
        f"/rides/{second['id']}/select",
        headers=second_headers,
        json={"response_id": second_responses[0]["id"]},
    )
    assert conflict.status_code == 400


def test_post_accept_lifecycle_preserved_after_selection(
    authenticated_passenger,
    authenticated_driver,
):
    selected = advance_to_accepted(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        authenticated_driver["user"].id,
    )
    ride_id = selected["id"]
    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]
    assert driver_client.put(
        f"/rides/{ride_id}/arrive",
        headers=driver_headers,
    ).json()["status"] == "driver_arriving"
    assert driver_client.put(
        f"/rides/{ride_id}/driver-arrived",
        headers=driver_headers,
    ).json()["status"] == "driver_arrived"
    assert driver_client.put(
        f"/rides/{ride_id}/start",
        headers=driver_headers,
    ).json()["status"] == "in_progress"
    complete = driver_client.put(
        f"/rides/{ride_id}/complete",
        headers=driver_headers,
    )
    assert complete.status_code == 200
    assert complete.json()["status"] == "completed"
    assert complete.json()["agreed_fare"] == 150.0
    assert complete.json()["completed_at"] is not None


def test_system_message_and_pickup_eta_after_selection(
    authenticated_passenger,
    authenticated_driver,
):
    selected = advance_to_accepted(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        authenticated_driver["user"].id,
    )
    messages = selected["system_messages"]
    assert messages
    assert messages[0]["body"] == DRIVER_ON_THE_WAY
    assert messages[0]["source"] == "system"
    assert "Automatically generated" not in messages[0]["body"]
    assert selected["pickup_eta_seconds"] is not None
    assert selected["agreed_fare"] == 150.0

    late_counter = authenticated_driver["client"].put(
        f"/rides/{selected['id']}/respond",
        headers=authenticated_driver["headers"],
        json={"response_type": "counter_offer", "amount": 155.0},
    )
    assert late_counter.status_code == 400
    trip = authenticated_passenger["client"].get(
        f"/trips/{selected['id']}",
        headers=authenticated_passenger["headers"],
    )
    assert trip.status_code == 200
    assert trip.json()["agreed_fare"] == 150.0
    assert trip.json()["system_messages"][0]["body"] == DRIVER_ON_THE_WAY


def test_negotiation_history_is_append_only_through_selection(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    payload = {**RIDE_CREATE_PAYLOAD, "proposed_fare": 35.0}
    created = _open_request(
        authenticated_passenger,
        authenticated_driver,
        payload=payload,
    )
    ride_id = created["id"]
    passenger = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    driver = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]

    options = driver.get(
        f"/rides/{ride_id}/counter-options",
        headers=driver_headers,
    )
    assert options.status_code == 200
    amounts = options.json()["amounts"]
    assert amounts == [37.0, 40.0, 43.0]

    countered = driver.put(
        f"/rides/{ride_id}/respond",
        headers=driver_headers,
        json={"response_type": "counter_offer", "amount": 37.0},
    )
    assert countered.status_code == 200

    increased = passenger.put(
        f"/rides/{ride_id}/offer",
        headers=passenger_headers,
        json={"action": "increase", "amount": 37.0},
    )
    assert increased.status_code == 200

    accepted = driver.put(
        f"/rides/{ride_id}/respond",
        headers=driver_headers,
        json={"response_type": "accept_passenger_offer"},
    )
    assert accepted.status_code == 200

    responses = list_responses(passenger, passenger_headers, ride_id)
    winner = next(item for item in responses if item["status"] == "open")
    selected = passenger_select_response(
        passenger,
        passenger_headers,
        ride_id,
        winner["id"],
    )
    assert selected["agreed_fare"] == 37.0

    db_session.expire_all()
    events = (
        db_session.query(NegotiationEvent)
        .filter(NegotiationEvent.ride_id == ride_id)
        .order_by(NegotiationEvent.id.asc())
        .all()
    )
    actions = [event.action for event in events]
    assert actions[0] == NegotiationAction.PASSENGER_OFFER_CREATED
    assert NegotiationAction.DRIVER_SUBMITTED_OFFER in actions
    assert NegotiationAction.PASSENGER_OFFER_INCREASED in actions
    assert NegotiationAction.DRIVER_ACCEPTED_PASSENGER_OFFER in actions
    assert NegotiationAction.FARE_AGREED in actions
    assert Decimal(str(selected["agreed_fare"])) == Decimal("37.00")
    # History stays; later events never rewrite earlier rows.
    first_id = events[0].id
    replay = (
        db_session.query(NegotiationEvent)
        .filter(NegotiationEvent.ride_id == ride_id)
        .order_by(NegotiationEvent.id.asc())
        .all()
    )
    assert replay[0].id == first_id
    assert [event.action for event in replay] == actions
    assert len(replay) == len(events)


def test_agreed_fare_cannot_change_after_trip_starts(
    authenticated_passenger,
    authenticated_driver,
):
    selected = advance_to_accepted(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        authenticated_driver["user"].id,
        payload={**RIDE_CREATE_PAYLOAD, "proposed_fare": 100.0},
    )
    ride_id = selected["id"]
    driver = authenticated_driver["client"]
    headers = authenticated_driver["headers"]
    assert driver.put(f"/rides/{ride_id}/arrive", headers=headers).status_code == 200
    started = driver.put(f"/rides/{ride_id}/start", headers=headers)
    assert started.status_code == 200
    assert started.json()["agreed_fare"] == 100.0
    change = authenticated_passenger["client"].put(
        f"/rides/{ride_id}/offer",
        headers=authenticated_passenger["headers"],
        json={"action": "increase", "amount": 120.0},
    )
    assert change.status_code == 400
    complete = driver.put(f"/rides/{ride_id}/complete", headers=headers)
    assert complete.status_code == 200
    assert complete.json()["agreed_fare"] == 100.0


def test_legacy_accept_path_is_marketplace_response(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    created = _open_request(authenticated_passenger, authenticated_driver)
    accept = authenticated_driver["client"].put(
        f"/rides/{created['id']}/accept",
        headers=authenticated_driver["headers"],
    )
    assert accept.status_code == 200
    assert accept.json()["status"] == "pending"
    db_session.expire_all()
    assert (
        db_session.query(DriverResponse)
        .filter(DriverResponse.ride_id == created["id"])
        .count()
        == 1
    )
