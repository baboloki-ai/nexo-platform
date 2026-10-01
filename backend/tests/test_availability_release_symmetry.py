"""Availability is released on complete, not on marketplace response."""
from app.models.user import User
from tests.ride_flow import advance_to_accepted


def test_complete_releases_driver_to_available(
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
    ride_id = selected["id"]
    driver_client = authenticated_driver["client"]
    headers = authenticated_driver["headers"]
    assert driver_client.put(f"/rides/{ride_id}/arrive", headers=headers).status_code == 200
    assert driver_client.put(
        f"/rides/{ride_id}/driver-arrived", headers=headers
    ).status_code == 200
    assert driver_client.put(f"/rides/{ride_id}/start", headers=headers).status_code == 200
    assert driver_client.put(f"/rides/{ride_id}/complete", headers=headers).status_code == 200
    db_session.expire_all()
    driver = db_session.get(User, authenticated_driver["user"].id)
    assert driver.availability_status == "available"
