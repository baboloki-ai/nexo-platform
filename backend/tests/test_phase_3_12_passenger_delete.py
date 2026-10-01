"""
Phase 3.12: passenger profile deletion must never destroy ride history.

A profile may be deleted only when it has zero RideRequest records.
Any attached ride — active or historical — rejects DELETE with HTTP 400.
RideOffers and driver availability must be left unchanged.
"""
from __future__ import annotations

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.constants.ride_offer_status import RideOfferStatus
from app.constants.ride_status import RideStatus
from app.models.passenger import Passenger
from app.models.ride_offer import RideOffer
from app.models.ride_request import (
    UQ_RIDE_REQUESTS_ONE_ACTIVE_PER_PASSENGER,
    RideRequest,
)
from app.models.user import User
from app.utils.jwt import create_access_token
from app.utils.security import hash_password

PICKUP_LAT = -26.2041
PICKUP_LON = 28.0473
DEST_LAT = -26.1330
DEST_LON = 28.2420

RIDE_CREATE_PAYLOAD = {
    "pickup_location": "Sandton City Pickup",
    "pickup_latitude": PICKUP_LAT,
    "pickup_longitude": PICKUP_LON,
    "destination": "OR Tambo Destination",
    "destination_latitude": DEST_LAT,
    "destination_longitude": DEST_LON,
    "proposed_fare": 150.0,
}

DELETE_BLOCKED_DETAIL = "Cannot delete passenger profile with ride history."

ACTIVE_STATUSES = (
    RideStatus.PENDING,
    RideStatus.PENDING_DRIVER_ACCEPTANCE,
    RideStatus.ACCEPTED,
    RideStatus.DRIVER_ARRIVING,
    RideStatus.DRIVER_ARRIVED,
    RideStatus.IN_PROGRESS,
)

# Statuses that share the same DELETE-rejected / ride-preserved assertions.
RIDE_HISTORY_STATUSES = (
    RideStatus.PENDING,
    RideStatus.DRIVER_ARRIVING,
    RideStatus.DRIVER_ARRIVED,
    RideStatus.IN_PROGRESS,
    RideStatus.COMPLETED,
    RideStatus.CANCELLED_BY_PASSENGER,
    RideStatus.CANCELLED_BY_DRIVER,
    RideStatus.NO_DRIVER_AVAILABLE,
    RideStatus.EXPIRED,
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


def _seed_ride(
    db_session: Session,
    passenger_id: int,
    status: str,
    *,
    accepted_driver_id: int | None = None,
) -> RideRequest:
    ride = RideRequest(
        passenger_id=passenger_id,
        pickup_location=RIDE_CREATE_PAYLOAD["pickup_location"],
        pickup_latitude=RIDE_CREATE_PAYLOAD["pickup_latitude"],
        pickup_longitude=RIDE_CREATE_PAYLOAD["pickup_longitude"],
        destination=RIDE_CREATE_PAYLOAD["destination"],
        destination_latitude=RIDE_CREATE_PAYLOAD["destination_latitude"],
        destination_longitude=RIDE_CREATE_PAYLOAD["destination_longitude"],
        proposed_fare=RIDE_CREATE_PAYLOAD["proposed_fare"],
        status=status,
        accepted_driver_id=accepted_driver_id,
    )
    db_session.add(ride)
    db_session.commit()
    db_session.refresh(ride)
    return ride


def _seed_offer(
    db_session: Session,
    *,
    ride_id: int,
    driver_id: int,
    status: str = RideOfferStatus.PENDING,
) -> RideOffer:
    offer = RideOffer(
        ride_id=ride_id,
        driver_id=driver_id,
        status=status,
    )
    db_session.add(offer)
    db_session.commit()
    db_session.refresh(offer)
    return offer


def _assert_delete_rejected(
    response,
    *,
    db_session: Session,
    passenger_id: int,
    ride_id: int,
    expected_status: str,
) -> None:
    assert response.status_code == 400
    assert response.json()["detail"] == DELETE_BLOCKED_DETAIL

    db_session.expire_all()
    assert db_session.get(Passenger, passenger_id) is not None
    ride_row = db_session.get(RideRequest, ride_id)
    assert ride_row is not None
    assert ride_row.status == expected_status
    assert ride_row.passenger_id == passenger_id


@pytest.fixture
def second_passenger_user(db_session: Session) -> User:
    user = User(
        full_name="Phase312 Passenger B",
        phone_number="+15550003121",
        email="phase312.passenger.b@test.nexo",
        password=hash_password("TestPassengerBPhase312!"),
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


def test_idle_passenger_profile_with_no_rides_can_be_deleted(
    authenticated_passenger,
    db_session: Session,
):
    client = authenticated_passenger["client"]
    headers = authenticated_passenger["headers"]
    passenger = authenticated_passenger["passenger"]
    passenger_id = passenger.id

    assert (
        db_session.query(RideRequest)
        .filter(RideRequest.passenger_id == passenger_id)
        .count()
        == 0
    )

    response = client.delete(
        f"/passengers/{passenger_id}",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Passenger deleted successfully"

    db_session.expire_all()
    assert db_session.get(Passenger, passenger_id) is None


@pytest.mark.parametrize("ride_status", RIDE_HISTORY_STATUSES)
def test_delete_rejected_when_passenger_has_ride_history(
    authenticated_passenger,
    db_session: Session,
    ride_status: str,
):
    client = authenticated_passenger["client"]
    headers = authenticated_passenger["headers"]
    passenger = authenticated_passenger["passenger"]

    ride = _seed_ride(db_session, passenger.id, ride_status)

    response = client.delete(
        f"/passengers/{passenger.id}",
        headers=headers,
    )
    _assert_delete_rejected(
        response,
        db_session=db_session,
        passenger_id=passenger.id,
        ride_id=ride.id,
        expected_status=ride_status,
    )


def test_delete_rejected_for_pending_driver_acceptance_preserves_offer_and_reservation(
    authenticated_passenger,
    db_session: Session,
    driver_user: User,
):
    client = authenticated_passenger["client"]
    headers = authenticated_passenger["headers"]
    passenger = authenticated_passenger["passenger"]

    driver_user.availability_status = "reserved"
    db_session.commit()

    ride = _seed_ride(
        db_session,
        passenger.id,
        RideStatus.PENDING_DRIVER_ACCEPTANCE,
        accepted_driver_id=driver_user.id,
    )
    offer = _seed_offer(
        db_session,
        ride_id=ride.id,
        driver_id=driver_user.id,
        status=RideOfferStatus.PENDING,
    )

    response = client.delete(
        f"/passengers/{passenger.id}",
        headers=headers,
    )
    _assert_delete_rejected(
        response,
        db_session=db_session,
        passenger_id=passenger.id,
        ride_id=ride.id,
        expected_status=RideStatus.PENDING_DRIVER_ACCEPTANCE,
    )

    offer_row = db_session.get(RideOffer, offer.id)
    assert offer_row is not None
    assert offer_row.ride_id == ride.id
    assert offer_row.driver_id == driver_user.id
    assert offer_row.status == RideOfferStatus.PENDING

    driver_row = db_session.get(User, driver_user.id)
    assert driver_row is not None
    assert driver_row.availability_status == "reserved"


def test_delete_rejected_for_accepted_ride_preserves_busy_driver(
    authenticated_passenger,
    db_session: Session,
    driver_user: User,
):
    client = authenticated_passenger["client"]
    headers = authenticated_passenger["headers"]
    passenger = authenticated_passenger["passenger"]

    driver_user.availability_status = "busy"
    db_session.commit()

    ride = _seed_ride(
        db_session,
        passenger.id,
        RideStatus.ACCEPTED,
        accepted_driver_id=driver_user.id,
    )
    offer = _seed_offer(
        db_session,
        ride_id=ride.id,
        driver_id=driver_user.id,
        status=RideOfferStatus.ACCEPTED,
    )

    response = client.delete(
        f"/passengers/{passenger.id}",
        headers=headers,
    )
    _assert_delete_rejected(
        response,
        db_session=db_session,
        passenger_id=passenger.id,
        ride_id=ride.id,
        expected_status=RideStatus.ACCEPTED,
    )

    offer_row = db_session.get(RideOffer, offer.id)
    assert offer_row is not None
    assert offer_row.status == RideOfferStatus.ACCEPTED

    driver_row = db_session.get(User, driver_user.id)
    assert driver_row is not None
    assert driver_row.availability_status == "busy"


def test_cannot_delete_another_users_passenger_profile(
    authenticated_passenger,
    second_passenger_profile: Passenger,
    db_session: Session,
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


def test_passenger_ride_requests_relationship_has_no_delete_orphan_cascade():
    relationship = inspect(Passenger).relationships["ride_requests"]
    cascade = relationship.cascade
    assert "delete-orphan" not in cascade
    assert "delete" not in cascade
    assert "all" not in cascade
    assert not cascade.delete
    assert not cascade.delete_orphan


def test_phase_3_11_one_active_ride_constraint_remains_intact(
    db_session: Session,
):
    row = db_session.execute(
        text(
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = 'ride_requests'
              AND indexname = :index_name
            """
        ),
        {"index_name": UQ_RIDE_REQUESTS_ONE_ACTIVE_PER_PASSENGER},
    ).one_or_none()

    assert row is not None
    indexname, indexdef = row
    assert indexname == UQ_RIDE_REQUESTS_ONE_ACTIVE_PER_PASSENGER
    indexdef_lower = indexdef.lower()
    assert "unique" in indexdef_lower
    assert "passenger_id" in indexdef_lower
    assert "where" in indexdef_lower
    for status in ACTIVE_STATUSES:
        assert f"'{status}'" in indexdef_lower
