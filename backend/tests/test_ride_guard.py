from app.models.ride_guard_event import RideGuardEvent
from app.models.ride_request import RideRequest
from app.constants.ride_guard import RideGuardEventType
from app.constants.ride_status import RideStatus
from tests.ride_flow import advance_to_accepted


def test_driver_gps_update_records_rideguard_event(
    authenticated_passenger,
    authenticated_driver,
    db_session,
):
    passenger_client = authenticated_passenger["client"]
    passenger_headers = authenticated_passenger["headers"]

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

    arrive_response = driver_client.put(
        f"/rides/{ride_id}/arrive",
        headers=driver_headers,
    )
    assert arrive_response.status_code == 200

    driver_arrived_response = driver_client.put(
        f"/rides/{ride_id}/driver-arrived",
        headers=driver_headers,
    )
    assert driver_arrived_response.status_code == 200

    start_response = driver_client.put(
        f"/rides/{ride_id}/start",
        headers=driver_headers,
    )
    assert start_response.status_code == 200

    db_session.expire_all()
    ride = db_session.get(RideRequest, ride_id)
    assert ride is not None
    assert ride.status == RideStatus.IN_PROGRESS

    gps_response = driver_client.put(
        "/drivers/location",
        headers=driver_headers,
        json={
            "latitude": -24.6545,
            "longitude": 25.9086,
            "accuracy": 8.5,
            "speed": 42.0 / 3.6,
            "heading": 180.0,
            "timestamp": 1790870000000,
        },
    )

    assert gps_response.status_code == 200

    event = (
        db_session.query(RideGuardEvent)
        .filter(
            RideGuardEvent.ride_id == ride_id,
            RideGuardEvent.event_type == RideGuardEventType.GPS_UPDATE,
        )
        .order_by(RideGuardEvent.id.desc())
        .first()
    )

    assert event is not None
    assert event.driver_id == driver.id
    assert event.latitude == -24.6545
    assert event.longitude == 25.9086
    assert event.speed_kmh == 42.0
    assert event.accuracy_meters == 8.5
    assert event.heading_degrees == 180.0
    assert event.metadata_json is not None
