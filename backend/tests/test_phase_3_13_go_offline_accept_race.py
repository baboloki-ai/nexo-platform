"""
Phase 3.13: go-offline vs passenger selection CAS.

Selection requires the driver to still be available. Go-offline while a
marketplace response is open withdraws it and prevents selection.
"""
from __future__ import annotations

import threading

from sqlalchemy.orm import Session, sessionmaker

from app.models.ride_request import RideRequest
from app.models.user import User
from app.routers.driver import go_offline
from app.services.marketplace_service import MarketplaceService
from tests.ride_flow import (
    create_pending_ride,
    driver_accept_passenger_offer,
    list_responses,
    prepare_driver_online,
)


def test_go_offline_prevents_selection(
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
    ride_id = created["id"]
    driver_accept_passenger_offer(
        authenticated_driver["client"],
        authenticated_driver["headers"],
        ride_id,
    )
    offline = authenticated_driver["client"].put(
        "/drivers/go-offline",
        headers=authenticated_driver["headers"],
    )
    assert offline.status_code == 200
    responses = list_responses(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        ride_id,
    )
    open_rows = [row for row in responses if row["status"] == "open"]
    assert open_rows == []
    if responses:
        select = authenticated_passenger["client"].put(
            f"/rides/{ride_id}/select",
            headers=authenticated_passenger["headers"],
            json={"response_id": responses[0]["id"]},
        )
        assert select.status_code == 400
    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride.status == "pending"
    assert ride.accepted_driver_id is None
    driver = db_session.get(User, authenticated_driver["user"].id)
    assert driver.availability_status == "offline"


def test_selection_then_go_offline_rejected(
    authenticated_passenger,
    authenticated_driver,
    db_session: Session,
):
    from tests.ride_flow import advance_to_accepted

    selected = advance_to_accepted(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        authenticated_driver["user"].id,
    )
    offline = authenticated_driver["client"].put(
        "/drivers/go-offline",
        headers=authenticated_driver["headers"],
    )
    assert offline.status_code == 400
    db_session.expire_all()
    ride = db_session.get(RideRequest, selected["id"])
    assert ride.status == "accepted"
    driver = db_session.get(User, authenticated_driver["user"].id)
    assert driver.availability_status == "busy"


def test_concurrent_select_vs_go_offline_one_winner(
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
    response_id = responses[0]["id"]
    passenger_user = authenticated_passenger["user"]
    driver_user_id = authenticated_driver["user"].id
    outcomes: list[str] = []

    def _select() -> None:
        session = test_session_factory()
        try:
            MarketplaceService.select_driver(
                db=session,
                ride_id=ride_id,
                current_user=session.get(User, passenger_user.id),
                response_id=response_id,
            )
            outcomes.append("selected")
        except Exception:
            outcomes.append("select_fail")
        finally:
            session.close()

    def _offline() -> None:
        session = test_session_factory()
        try:
            driver = session.get(User, driver_user_id)
            go_offline(db=session, current_user=driver)
            outcomes.append("offline")
        except Exception:
            outcomes.append("offline_fail")
        finally:
            session.close()

    first = threading.Thread(target=_select)
    second = threading.Thread(target=_offline)
    first.start()
    second.start()
    first.join()
    second.join()
    assert "selected" in outcomes or "offline" in outcomes
    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    driver = db_session.get(User, driver_user_id)
    if ride.status == "accepted":
        assert driver.availability_status == "busy"
        assert "offline_fail" in outcomes or "offline" not in outcomes
    else:
        assert ride.accepted_driver_id is None
        assert driver.availability_status in {"offline", "available"}
