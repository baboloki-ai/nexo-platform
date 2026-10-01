"""Selection vs respond CAS: exactly one assignment."""
from app.constants.driver_response import DriverResponseStatus
from app.models.driver_response import DriverResponse
from app.models.ride_request import RideRequest
from tests.ride_flow import (
    create_pending_ride,
    driver_accept_passenger_offer,
    list_responses,
    passenger_select_response,
    prepare_driver_online,
)


def test_select_then_late_respond_fails(
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
    passenger_select_response(
        authenticated_passenger["client"],
        authenticated_passenger["headers"],
        ride_id,
        responses[0]["id"],
    )
    late = authenticated_driver["client"].put(
        f"/rides/{ride_id}/respond",
        headers=authenticated_driver["headers"],
        json={"response_type": "accept_passenger_offer"},
    )
    assert late.status_code == 400
    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride.status == "accepted"
    winner = (
        db_session.query(DriverResponse)
        .filter(DriverResponse.ride_id == ride_id)
        .one()
    )
    assert winner.status == DriverResponseStatus.SELECTED
