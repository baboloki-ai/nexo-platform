"""Marketplace concurrency: multiple open responses, single selection winner."""
from __future__ import annotations

import threading

from sqlalchemy.orm import Session, sessionmaker

from app.constants.driver_response import DriverResponseStatus, DriverResponseType
from app.models.driver_response import DriverResponse
from app.models.ride_request import RideRequest
from app.models.user import User
from app.services.marketplace_service import MarketplaceService
from app.services.wallet_service import WalletService
from app.utils.security import hash_password
from tests.ride_flow import RIDE_CREATE_PAYLOAD, create_pending_ride, prepare_driver_online


def _second_driver(db_session: Session) -> User:
    user = User(
        full_name="Concurrency Driver B",
        phone_number="+15550004102",
        email="concurrency.driver.b@test.nexo",
        password=hash_password("TestDriverB123!"),
        role="driver",
        verification_status="approved",
        availability_status="available",
        current_latitude=-26.2041,
        current_longitude=28.0473,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    WalletService.ensure_wallet(db_session, user.id)
    db_session.commit()
    return user


def test_concurrent_driver_responses_both_remain_open(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
    test_session_factory: sessionmaker,
):
    second = _second_driver(db_session)
    prepare_driver_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    created = create_pending_ride(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
    )
    ride_id = created["id"]
    errors: list[Exception] = []

    def _respond(driver_id: int) -> None:
        session = test_session_factory()
        try:
            MarketplaceService.driver_respond(
                db=session,
                ride_id=ride_id,
                current_user=session.get(User, driver_id),
                response_type=DriverResponseType.ACCEPT_PASSENGER_OFFER,
                amount=None,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            session.close()

    threads = [
        threading.Thread(target=_respond, args=(authenticated_driver["user"].id,)),
        threading.Thread(target=_respond, args=(second.id,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    db_session.expire_all()
    assert (
        db_session.query(DriverResponse)
        .filter(
            DriverResponse.ride_id == ride_id,
            DriverResponse.status == DriverResponseStatus.OPEN,
        )
        .count()
        == 2
    )
    ride = db_session.get(RideRequest, ride_id)
    assert ride.status == "pending"
    assert ride.accepted_driver_id is None
