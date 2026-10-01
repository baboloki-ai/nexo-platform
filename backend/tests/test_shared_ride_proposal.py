"""Shared Ride pilot: driver proposal and passenger consent."""
from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.constants.ride_status import RideStatus
from app.models.passenger import Passenger
from app.models.payment import Payment
from app.models.ride_request import (
    UQ_RIDE_REQUESTS_ONE_ACTIVE_PER_DRIVER,
    RideRequest,
    _ACTIVE_DRIVER_ASSIGNMENT_PREDICATE,
)
from app.models.user import User
from app.models.wallet_ledger_entry import WalletLedgerEntry
from app.utils.jwt import create_access_token
from app.utils.security import hash_password
from tests.ride_flow import (
    RIDE_CREATE_PAYLOAD,
    advance_to_in_progress,
    create_pending_ride,
)

_FAR_DESTINATION = {
    **RIDE_CREATE_PAYLOAD,
    "pickup_location": "Far Shared Pickup",
    "destination": "Cape Town",
    "destination_latitude": -33.9249,
    "destination_longitude": 18.4241,
}


@pytest.fixture(scope="module", autouse=True)
def _sync_active_driver_index(test_engine: Engine) -> None:
    """create_all does not replace an existing partial index predicate."""
    index_name = UQ_RIDE_REQUESTS_ONE_ACTIVE_PER_DRIVER
    with test_engine.begin() as connection:
        connection.execute(text(f"DROP INDEX IF EXISTS {index_name}"))
        connection.execute(
            text(
                f"CREATE UNIQUE INDEX {index_name} "
                "ON ride_requests (accepted_driver_id) "
                f"WHERE {_ACTIVE_DRIVER_ASSIGNMENT_PREDICATE}"
            )
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
        first_name="Shared",
        last_name="Passenger",
        phone=profile_phone,
        email=profile_email,
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)
    return user, profile, _auth_headers(user)


def _create_driver(
    db_session: Session,
    *,
    full_name: str,
    phone_number: str,
    email: str,
) -> tuple[User, dict[str, str]]:
    user = User(
        full_name=full_name,
        phone_number=phone_number,
        email=email,
        password=hash_password("TestDriverOther123!"),
        role="driver",
        verification_status="approved",
        availability_status="offline",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user, _auth_headers(user)


def _shareable_pair(
    authenticated_passenger: dict[str, Any],
    authenticated_driver: dict[str, Any],
    db_session: Session,
    driver_user: User,
    *,
    passenger_name: str,
    phone_number: str,
    email: str,
    profile_phone: str,
    profile_email: str,
    candidate_payload: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    current = advance_to_in_progress(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        driver_user.id,
    )
    _user_b, _passenger_b, headers_b = _create_passenger(
        db_session,
        full_name=passenger_name,
        phone_number=phone_number,
        email=email,
        profile_phone=profile_phone,
        profile_email=profile_email,
    )
    candidate = create_pending_ride(
        authenticated_passenger["client"],
        headers_b,
        payload=candidate_payload,
    )
    return current, candidate, headers_b


def _propose(
    client: TestClient,
    headers: dict[str, str],
    ride_id: int,
    candidate_id: int,
):
    return client.post(
        f"/rides/{ride_id}/shared-candidates/{candidate_id}/propose",
        headers=headers,
    )


def _consent(
    client: TestClient,
    headers: dict[str, str],
    ride_id: int,
    consent: bool,
):
    return client.post(
        f"/rides/{ride_id}/shared-consent",
        headers=headers,
        json={"consent": consent},
    )


def test_assigned_driver_can_propose_valid_candidate(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
    driver_user: User,
):
    current, candidate, _headers_b = _shareable_pair(
        authenticated_passenger,
        authenticated_driver,
        db_session,
        driver_user,
        passenger_name="Passenger B Propose",
        phone_number="+15550007201",
        email="shared.passenger.propose@test.nexo",
        profile_phone="+15550007202",
        profile_email="shared.passenger.propose.profile@test.nexo",
    )

    response = _propose(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        current["id"],
        candidate["id"],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == current["id"]
    assert body["status"] == RideStatus.IN_PROGRESS
    assert body["accepted_driver_id"] == driver_user.id
    assert body["shared_ride_with_id"] == candidate["id"]
    assert body["shared_ride_consent"] is False

    db_session.expire_all()
    candidate_row = db_session.get(RideRequest, candidate["id"])
    assert candidate_row is not None
    assert candidate_row.status == RideStatus.PENDING
    assert candidate_row.accepted_driver_id is None
    assert candidate_row.shared_ride_consent is False


def test_unrelated_driver_cannot_propose(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
    driver_user: User,
):
    current, candidate, _headers_b = _shareable_pair(
        authenticated_passenger,
        authenticated_driver,
        db_session,
        driver_user,
        passenger_name="Passenger B Unrelated Driver",
        phone_number="+15550007211",
        email="shared.passenger.unrelated.driver@test.nexo",
        profile_phone="+15550007212",
        profile_email="shared.passenger.unrelated.driver.profile@test.nexo",
    )
    _other_driver, other_headers = _create_driver(
        db_session,
        full_name="Unrelated Shared Driver",
        phone_number="+15550007213",
        email="shared.driver.unrelated@test.nexo",
    )

    response = _propose(
        authenticated_driver["client"],
        other_headers,
        current["id"],
        candidate["id"],
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "You are not assigned to this ride."

    db_session.expire_all()
    current_row = db_session.get(RideRequest, current["id"])
    assert current_row is not None
    assert current_row.shared_ride_with_id is None
    assert current_row.shared_ride_consent is False


def test_invalid_candidate_is_rejected(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
    driver_user: User,
):
    current, candidate, _headers_b = _shareable_pair(
        authenticated_passenger,
        authenticated_driver,
        db_session,
        driver_user,
        passenger_name="Passenger B Invalid",
        phone_number="+15550007221",
        email="shared.passenger.invalid@test.nexo",
        profile_phone="+15550007222",
        profile_email="shared.passenger.invalid.profile@test.nexo",
        candidate_payload=_FAR_DESTINATION,
    )

    response = _propose(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        current["id"],
        candidate["id"],
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Candidate is not eligible for a shared ride."

    db_session.expire_all()
    current_row = db_session.get(RideRequest, current["id"])
    candidate_row = db_session.get(RideRequest, candidate["id"])
    assert current_row is not None
    assert current_row.shared_ride_with_id is None
    assert candidate_row is not None
    assert candidate_row.status == RideStatus.PENDING
    assert candidate_row.accepted_driver_id is None


def test_passenger_can_accept(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
    driver_user: User,
):
    current, candidate, _headers_b = _shareable_pair(
        authenticated_passenger,
        authenticated_driver,
        db_session,
        driver_user,
        passenger_name="Passenger B Accept",
        phone_number="+15550007231",
        email="shared.passenger.accept@test.nexo",
        profile_phone="+15550007232",
        profile_email="shared.passenger.accept.profile@test.nexo",
    )
    proposed = _propose(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        current["id"],
        candidate["id"],
    )
    assert proposed.status_code == 200, proposed.text

    db_session.expire_all()
    host_payments_before = [
        (payment.id, payment.status)
        for payment in db_session.query(Payment)
        .filter(Payment.ride_id == current["id"])
        .order_by(Payment.id)
        .all()
    ]
    ledger_before = (
        db_session.query(WalletLedgerEntry)
        .filter(WalletLedgerEntry.driver_id == driver_user.id)
        .count()
    )

    response = _consent(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        current["id"],
        True,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == current["id"]
    assert body["status"] == RideStatus.IN_PROGRESS
    assert body["accepted_driver_id"] == driver_user.id
    assert body["shared_ride_with_id"] == candidate["id"]
    assert body["shared_ride_consent"] is True

    db_session.expire_all()
    candidate_row = db_session.get(RideRequest, candidate["id"])
    assert candidate_row is not None
    assert candidate_row.status == RideStatus.ACCEPTED
    assert candidate_row.accepted_driver_id == driver_user.id
    assert candidate_row.shared_ride_with_id == current["id"]
    assert candidate_row.shared_ride_consent is True
    assert candidate_row.is_next_ride is False
    assert (
        db_session.query(Payment)
        .filter(Payment.ride_id == candidate["id"])
        .count()
        == 0
    )
    host_payments_after = [
        (payment.id, payment.status)
        for payment in db_session.query(Payment)
        .filter(Payment.ride_id == current["id"])
        .order_by(Payment.id)
        .all()
    ]
    assert host_payments_after == host_payments_before
    assert (
        db_session.query(WalletLedgerEntry)
        .filter(WalletLedgerEntry.driver_id == driver_user.id)
        .count()
        == ledger_before
    )


def test_passenger_can_decline(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
    driver_user: User,
):
    current, candidate, _headers_b = _shareable_pair(
        authenticated_passenger,
        authenticated_driver,
        db_session,
        driver_user,
        passenger_name="Passenger B Decline",
        phone_number="+15550007241",
        email="shared.passenger.decline@test.nexo",
        profile_phone="+15550007242",
        profile_email="shared.passenger.decline.profile@test.nexo",
    )
    proposed = _propose(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        current["id"],
        candidate["id"],
    )
    assert proposed.status_code == 200, proposed.text

    response = _consent(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        current["id"],
        False,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == current["id"]
    assert body["shared_ride_with_id"] is None
    assert body["shared_ride_consent"] is False

    db_session.expire_all()
    candidate_row = db_session.get(RideRequest, candidate["id"])
    assert candidate_row is not None
    assert candidate_row.status == RideStatus.PENDING
    assert candidate_row.accepted_driver_id is None
    assert candidate_row.shared_ride_with_id is None
    assert candidate_row.shared_ride_consent is False


def test_unrelated_passenger_cannot_consent(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
    driver_user: User,
):
    current, candidate, headers_b = _shareable_pair(
        authenticated_passenger,
        authenticated_driver,
        db_session,
        driver_user,
        passenger_name="Passenger B Unrelated Consent",
        phone_number="+15550007251",
        email="shared.passenger.unrelated.consent@test.nexo",
        profile_phone="+15550007252",
        profile_email="shared.passenger.unrelated.consent.profile@test.nexo",
    )
    proposed = _propose(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        current["id"],
        candidate["id"],
    )
    assert proposed.status_code == 200, proposed.text

    response = _consent(
        authenticated_passenger["client"],
        headers_b,
        current["id"],
        True,
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "You are not authorized to access this ride."

    db_session.expire_all()
    current_row = db_session.get(RideRequest, current["id"])
    candidate_row = db_session.get(RideRequest, candidate["id"])
    assert current_row is not None
    assert current_row.shared_ride_with_id == candidate["id"]
    assert current_row.shared_ride_consent is False
    assert candidate_row is not None
    assert candidate_row.accepted_driver_id is None
    assert candidate_row.status == RideStatus.PENDING


def test_candidate_becomes_assigned_only_after_consent(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
    driver_user: User,
):
    current, candidate, _headers_b = _shareable_pair(
        authenticated_passenger,
        authenticated_driver,
        db_session,
        driver_user,
        passenger_name="Passenger B Assign After Consent",
        phone_number="+15550007261",
        email="shared.passenger.assign@test.nexo",
        profile_phone="+15550007262",
        profile_email="shared.passenger.assign.profile@test.nexo",
    )
    proposed = _propose(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        current["id"],
        candidate["id"],
    )
    assert proposed.status_code == 200, proposed.text

    db_session.expire_all()
    before = db_session.get(RideRequest, candidate["id"])
    assert before is not None
    assert before.status == RideStatus.PENDING
    assert before.accepted_driver_id is None

    response = _consent(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        current["id"],
        True,
    )
    assert response.status_code == 200, response.text

    db_session.expire_all()
    after = db_session.get(RideRequest, candidate["id"])
    assert after is not None
    assert after.status == RideStatus.ACCEPTED
    assert after.accepted_driver_id == driver_user.id


def test_consent_rejected_if_candidate_already_taken(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
    driver_user: User,
):
    current, candidate, _headers_b = _shareable_pair(
        authenticated_passenger,
        authenticated_driver,
        db_session,
        driver_user,
        passenger_name="Passenger B Taken",
        phone_number="+15550007271",
        email="shared.passenger.taken@test.nexo",
        profile_phone="+15550007272",
        profile_email="shared.passenger.taken.profile@test.nexo",
    )
    other_driver, _other_headers = _create_driver(
        db_session,
        full_name="Driver Who Took Candidate",
        phone_number="+15550007273",
        email="shared.driver.took.candidate@test.nexo",
    )
    proposed = _propose(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        current["id"],
        candidate["id"],
    )
    assert proposed.status_code == 200, proposed.text

    db_session.expire_all()
    candidate_row = db_session.get(RideRequest, candidate["id"])
    assert candidate_row is not None
    candidate_row.status = RideStatus.ACCEPTED
    candidate_row.accepted_driver_id = other_driver.id
    db_session.commit()

    response = _consent(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        current["id"],
        True,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Shared ride candidate is no longer available."

    db_session.expire_all()
    current_row = db_session.get(RideRequest, current["id"])
    taken = db_session.get(RideRequest, candidate["id"])
    assert current_row is not None
    assert current_row.shared_ride_consent is False
    assert current_row.accepted_driver_id == driver_user.id
    assert taken is not None
    assert taken.status == RideStatus.ACCEPTED
    assert taken.accepted_driver_id == other_driver.id
    assert taken.shared_ride_consent is False

def test_shared_ride_completes_with_host(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
    driver_user: User,
):
    current, candidate, _headers_b = _shareable_pair(
        authenticated_passenger,
        authenticated_driver,
        db_session,
        driver_user,
        passenger_name="Passenger B Completion",
        phone_number="+15550007281",
        email="shared.passenger.completion@test.nexo",
        profile_phone="+15550007282",
        profile_email="shared.passenger.completion.profile@test.nexo",
    )

    proposed = _propose(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        current["id"],
        candidate["id"],
    )
    assert proposed.status_code == 200, proposed.text

    response = _consent(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        current["id"],
        True,
    )
    assert response.status_code == 200, response.text

    db_session.expire_all()
    candidate_row = db_session.get(RideRequest, candidate["id"])
    assert candidate_row is not None
    assert candidate_row.status == RideStatus.ACCEPTED
    assert candidate_row.accepted_driver_id == driver_user.id
    assert candidate_row.shared_ride_with_id == current["id"]
    assert candidate_row.shared_ride_consent is True

    complete = authenticated_driver["client"].put(
        f"/rides/{current['id']}/complete",
        headers=authenticated_driver["headers"],
    )
    assert complete.status_code == 200, complete.text

    db_session.expire_all()
    current_row = db_session.get(RideRequest, current["id"])
    candidate_row = db_session.get(RideRequest, candidate["id"])

    assert current_row is not None
    assert current_row.status == RideStatus.COMPLETED

    assert candidate_row is not None
    assert candidate_row.status == RideStatus.COMPLETED
    assert candidate_row.accepted_driver_id == driver_user.id
    assert candidate_row.completed_at is not None
