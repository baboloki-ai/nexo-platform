"""Open marketplace requests stay pending when no driver is eligible."""
from app.constants.ride_status import RideStatus
from app.models.ride_request import RideRequest
from tests.ride_flow import RIDE_CREATE_PAYLOAD


def test_create_with_no_drivers_stays_pending(
    authenticated_passenger,
    db_session,
):
    payload = authenticated_passenger["client"].post(
        "/rides/",
        headers=authenticated_passenger["headers"],
        json=RIDE_CREATE_PAYLOAD,
    ).json()
    assert payload["status"] == RideStatus.PENDING
    db_session.expire_all()
    ride = db_session.get(RideRequest, payload["id"])
    assert ride.status == RideStatus.PENDING
    assert ride.accepted_driver_id is None
