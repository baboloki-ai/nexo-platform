"""L3.0 driver responses replace exclusive RideOffers."""
from app.constants.driver_response import DriverResponseStatus, DriverResponseType
from app.models.driver_response import DriverResponse
from tests.ride_flow import (
    create_pending_ride,
    driver_accept_passenger_offer,
    prepare_driver_online,
)


def test_driver_accept_creates_open_response_not_assignment(
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
    row = (
        db_session.query(DriverResponse)
        .filter(DriverResponse.ride_id == created["id"])
        .one()
    )
    assert row.status == DriverResponseStatus.OPEN
    assert row.response_type == DriverResponseType.ACCEPT_PASSENGER_OFFER
    assert created["accepted_driver_id"] is None
