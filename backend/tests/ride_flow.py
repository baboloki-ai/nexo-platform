"""Shared marketplace ride-flow helpers for L3.0 and Phase 3 regression."""
from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

RIDE_CREATE_PAYLOAD = {
    "pickup_location": "Sandton City Pickup",
    "pickup_latitude": -26.2041,
    "pickup_longitude": 28.0473,
    "destination": "OR Tambo Destination",
    "destination_latitude": -26.1330,
    "destination_longitude": 28.2420,
    "proposed_fare": 150.0,
}

DRIVER_LOCATION_PAYLOAD = {
    "latitude": -26.2041,
    "longitude": 28.0473,
}


def prepare_driver_online(
    driver_client: TestClient,
    driver_headers: dict[str, str],
) -> None:
    assert driver_client.put(
        "/drivers/location",
        headers=driver_headers,
        json=DRIVER_LOCATION_PAYLOAD,
    ).status_code == 200
    assert driver_client.put(
        "/drivers/go-online",
        headers=driver_headers,
    ).status_code == 200


def create_pending_ride(
    passenger_client: TestClient,
    passenger_headers: dict[str, str],
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    create_response = passenger_client.post(
        "/rides/",
        headers=passenger_headers,
        json=payload or RIDE_CREATE_PAYLOAD,
    )
    assert create_response.status_code == 200, create_response.text
    body = create_response.json()
    assert body["status"] == "pending"
    assert body["accepted_driver_id"] is None
    assert body["agreed_fare"] is None
    return body


def driver_accept_passenger_offer(
    driver_client: TestClient,
    driver_headers: dict[str, str],
    ride_id: int,
) -> dict[str, Any]:
    response = driver_client.put(
        f"/rides/{ride_id}/respond",
        headers=driver_headers,
        json={"response_type": "accept_passenger_offer"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "pending"
    assert body["accepted_driver_id"] is None
    return body


def list_responses(
    client: TestClient,
    headers: dict[str, str],
    ride_id: int,
) -> list[dict[str, Any]]:
    response = client.get(f"/rides/{ride_id}/responses", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def passenger_select_response(
    passenger_client: TestClient,
    passenger_headers: dict[str, str],
    ride_id: int,
    response_id: int,
) -> dict[str, Any]:
    response = passenger_client.put(
        f"/rides/{ride_id}/select",
        headers=passenger_headers,
        json={"response_id": response_id},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "accepted"
    assert body["agreed_fare"] is not None
    return body


def advance_to_accepted(
    passenger_client: TestClient,
    passenger_headers: dict[str, str],
    driver_client: TestClient,
    driver_headers: dict[str, str],
    expected_driver_id: int,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prepare_driver_online(driver_client, driver_headers)
    created = create_pending_ride(
        passenger_client,
        passenger_headers,
        payload=payload,
    )
    ride_id = created["id"]
    driver_accept_passenger_offer(driver_client, driver_headers, ride_id)
    responses = list_responses(passenger_client, passenger_headers, ride_id)
    match = next(
        item for item in responses
        if item["driver_id"] == expected_driver_id and item["status"] == "open"
    )
    selected = passenger_select_response(
        passenger_client,
        passenger_headers,
        ride_id,
        match["id"],
    )
    assert selected["accepted_driver_id"] == expected_driver_id
    return selected


def advance_to_in_progress(
    passenger_client: TestClient,
    passenger_headers: dict[str, str],
    driver_client: TestClient,
    driver_headers: dict[str, str],
    expected_driver_id: int,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selected = advance_to_accepted(
        passenger_client,
        passenger_headers,
        driver_client,
        driver_headers,
        expected_driver_id,
        payload=payload,
    )
    ride_id = selected["id"]
    assert driver_client.put(
        f"/rides/{ride_id}/arrive",
        headers=driver_headers,
    ).status_code == 200
    assert driver_client.put(
        f"/rides/{ride_id}/driver-arrived",
        headers=driver_headers,
    ).status_code == 200
    started = driver_client.put(
        f"/rides/{ride_id}/start",
        headers=driver_headers,
    )
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["status"] == "in_progress"
    assert body["accepted_driver_id"] == expected_driver_id
    return body


def accept_next_ride(
    driver_client: TestClient,
    driver_headers: dict[str, str],
    ride_id: int,
) -> dict[str, Any]:
    response = driver_client.put(
        f"/rides/{ride_id}/accept-next",
        headers=driver_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "accepted"
    assert body["is_next_ride"] is True
    assert body["accepted_driver_id"] is not None
    return body
