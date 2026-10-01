"""
Phase 1.2: automated happy-path ride lifecycle test.
"""
from app.models.ride_request import RideRequest
from app.models.user import User
from tests.ride_flow import RIDE_CREATE_PAYLOAD, advance_to_accepted


def test_ride_happy_path_completes(
    authenticated_passenger,
    authenticated_driver,
    db_session,
    driver_user,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]
    passenger = authenticated_passenger["passenger"]

    driver_client = authenticated_driver["client"]
    driver_headers = authenticated_driver["headers"]
    driver = authenticated_driver["user"]

    selected = advance_to_accepted(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        driver.id,
    )
    ride_id = selected["id"]
    assert selected["status"] == "accepted"
    assert selected["accepted_driver_id"] == driver.id
    assert selected["accepted_driver_id"] == driver_user.id
    assert selected["passenger_id"] == passenger.id
    assert selected["agreed_fare"] == RIDE_CREATE_PAYLOAD["proposed_fare"]

    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride is not None
    assert ride.status == "accepted"
    assert ride.accepted_driver_id == driver.id

    driver_row = db_session.get(User, driver.id)
    assert driver_row.availability_status == "busy"

    # 11–12. Arrive → driver_arriving
    arrive_response = driver_client.put(
        f"/rides/{ride_id}/arrive",
        headers=driver_headers,
    )
    assert arrive_response.status_code == 200
    assert arrive_response.json()["status"] == "driver_arriving"

    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride.status == "driver_arriving"

    # 13–14. Driver arrived → driver_arrived
    driver_arrived_response = driver_client.put(
        f"/rides/{ride_id}/driver-arrived",
        headers=driver_headers,
    )
    assert driver_arrived_response.status_code == 200
    assert driver_arrived_response.json()["status"] == "driver_arrived"

    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride.status == "driver_arrived"

    # 15–16. Start → in_progress
    start_response = driver_client.put(
        f"/rides/{ride_id}/start",
        headers=driver_headers,
    )
    assert start_response.status_code == 200
    assert start_response.json()["status"] == "in_progress"

    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride.status == "in_progress"

    # 17–19. Complete → completed, driver available again
    complete_response = driver_client.put(
        f"/rides/{ride_id}/complete",
        headers=driver_headers,
    )
    assert complete_response.status_code == 200
    assert complete_response.json()["status"] == "completed"

    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride is not None
    assert ride.status == "completed"
    assert ride.accepted_driver_id == driver.id
    assert ride.passenger_id == passenger.id
    assert ride.pickup_location == RIDE_CREATE_PAYLOAD["pickup_location"]
    assert ride.pickup_latitude == RIDE_CREATE_PAYLOAD["pickup_latitude"]
    assert ride.pickup_longitude == RIDE_CREATE_PAYLOAD["pickup_longitude"]
    assert ride.destination == RIDE_CREATE_PAYLOAD["destination"]
    assert ride.destination_latitude == RIDE_CREATE_PAYLOAD["destination_latitude"]
    assert ride.destination_longitude == RIDE_CREATE_PAYLOAD["destination_longitude"]
    assert ride.proposed_fare == RIDE_CREATE_PAYLOAD["proposed_fare"]

    # 20. Final RideRequest record + driver availability
    driver_row = db_session.get(User, driver.id)
    assert driver_row.availability_status == "available"
