"""Drivers stay available until passenger selection."""
from app.models.user import User
from tests.ride_flow import (
    advance_to_accepted,
    create_pending_ride,
    driver_accept_passenger_offer,
    prepare_driver_online,
)


def test_responding_does_not_reserve_driver(
    authenticated_passenger,
    authenticated_driver,
    db_session,
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
    db_session.expire_all()
    driver = db_session.get(User, authenticated_driver["user"].id)
    assert driver.availability_status == "available"


def test_selection_sets_driver_busy(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    selected = advance_to_accepted(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        authenticated_driver["client"],
        authenticated_driver["headers"],
        authenticated_driver["user"].id,
    )
    assert selected["status"] == "accepted"
    db_session.expire_all()
    driver = db_session.get(User, authenticated_driver["user"].id)
    assert driver.availability_status == "busy"
