"""Marketplace: two open requests do not reserve a driver until selection."""
from app.models.user import User
from tests.ride_flow import create_pending_ride, prepare_driver_online


def test_two_pending_requests_do_not_reserve_the_only_driver(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    prepare_driver_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    first = create_pending_ride(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
    )
    # Second create is blocked by one-active-ride-per-passenger.
    second = authenticated_passenger["client"].post(
        "/rides/",
        headers=authenticated_passenger["headers"],
        json={
            "pickup_location": "Other Pickup",
            "pickup_latitude": -26.2041,
            "pickup_longitude": 28.0473,
            "destination": "Other Destination",
            "destination_latitude": -26.1330,
            "destination_longitude": 28.2420,
            "proposed_fare": 150.0,
        },
    )
    assert second.status_code == 400
    assert first["status"] == "pending"
    assert first["accepted_driver_id"] is None
    db_session.expire_all()
    driver = db_session.get(User, authenticated_driver["user"].id)
    assert driver.availability_status == "available"
