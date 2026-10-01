"""Driver-response expiry CAS (no exclusive RideOffer redispatch)."""
from app.constants.driver_response import DriverResponseStatus
from app.models.driver_response import DriverResponse
from app.services.marketplace_service import MarketplaceService
from tests.ride_flow import (
    create_pending_ride,
    driver_accept_passenger_offer,
    prepare_driver_online,
)


def test_expire_open_response_loses_to_nothing_and_blocks_select(
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
    row = (
        db_session.query(DriverResponse)
        .filter(DriverResponse.ride_id == created["id"])
        .one()
    )
    assert MarketplaceService.expire_open_response(db_session, row.id) is True
    assert MarketplaceService.expire_open_response(db_session, row.id) is False
    select = authenticated_passenger["client"].put(
        f"/rides/{created['id']}/select",
        headers=authenticated_passenger["headers"],
        json={"response_id": row.id},
    )
    assert select.status_code == 400
    db_session.expire_all()
    expired = db_session.get(DriverResponse, row.id)
    assert expired.status == DriverResponseStatus.EXPIRED
