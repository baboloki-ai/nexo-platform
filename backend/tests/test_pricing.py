"""Focused Botswana launch pricing: formula, config, no fare cap."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from app.services.distance_provider import (
    DISTANCE_SOURCE_HAVERSINE,
    HaversineTripDistanceProvider,
    TripDistanceEstimate,
)
from app.services.pricing_service import PricingService
from app.utils.money import MIN_PASSENGER_OFFER
from tests.ride_flow import RIDE_CREATE_PAYLOAD, create_pending_ride, prepare_driver_online


def test_recommended_fare_examples_round_to_thebe():
    cases = (
        (1, "22.50"),
        (2, "25.00"),
        (5, "32.50"),
        (10, "45.00"),
        (20, "70.00"),
        (30, "95.00"),
        (0, "20.00"),
    )
    for kilometres, expected in cases:
        assert PricingService.recommended_fare_from_distance(
            Decimal(str(kilometres))
        ) == Decimal(expected)


def test_recommended_fare_never_below_p20():
    assert PricingService.recommended_fare_from_distance(None) == MIN_PASSENGER_OFFER
    assert PricingService.recommended_fare_from_distance(Decimal("-3")) == MIN_PASSENGER_OFFER
    assert PricingService.recommended_fare_from_distance(Decimal("0.01")) == Decimal("20.03")


def test_p70_is_recommended_for_20km_not_a_cap():
    assert PricingService.recommended_fare_from_distance(20) == Decimal("70.00")
    options = PricingService.passenger_offer_options(Decimal("70.00"))
    assert Decimal("70.00") in options
    assert Decimal("90.00") in options
    assert max(options) > Decimal("70.00")


def test_pricing_uses_configured_base_and_rate():
    with patch("app.services.pricing_service.config.NEXO_BASE_FARE", Decimal("15.00")), patch(
        "app.services.pricing_service.config.NEXO_FARE_PER_KM",
        Decimal("3.00"),
    ):
        # Engine still floors at P20 passenger minimum.
        assert PricingService.recommended_fare_from_distance(1) == Decimal("20.00")
        assert PricingService.recommended_fare_from_distance(5) == Decimal("30.00")


def test_quote_from_estimate_is_provider_independent():
    estimate = TripDistanceEstimate(
        km=Decimal("10.000"),
        source="test_router",
        is_road_distance=True,
    )
    quote = PricingService.quote_from_estimate(estimate)
    assert quote.recommended_fare == Decimal("45.00")
    assert quote.estimated_trip_distance_km == Decimal("10.000")
    assert quote.distance_source == "test_router"
    assert quote.is_road_distance is True
    assert quote.offer_options[0] == Decimal("45.00")
    assert Decimal("65.00") in quote.offer_options


def test_haversine_provider_is_estimated_not_road():
    provider = HaversineTripDistanceProvider()
    estimate = provider.estimate(-24.6545, 25.9086, -24.6278, 25.9059)
    assert estimate is not None
    assert estimate.source == DISTANCE_SOURCE_HAVERSINE
    assert estimate.is_road_distance is False
    assert estimate.km > 0


def test_quote_endpoint_returns_recommended_fare(authenticated_passenger):
    with patch(
        "app.services.pricing_service.get_trip_distance_provider"
    ) as provider:
        provider.return_value.estimate.return_value = TripDistanceEstimate(
            km=Decimal("10"),
            source=DISTANCE_SOURCE_HAVERSINE,
            is_road_distance=False,
        )
        response = authenticated_passenger["client"].post(
            "/rides/quote",
            headers=authenticated_passenger["headers"],
            json={
                "pickup_latitude": -24.6545,
                "pickup_longitude": 25.9086,
                "destination_latitude": -24.6278,
                "destination_longitude": 25.9059,
            },
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["recommended_fare"] == 45.0
    assert body["minimum_offer"] == 20.0
    assert body["base_fare"] == 20.0
    assert body["fare_per_km"] == 2.5
    assert body["is_road_distance"] is False
    assert 45.0 in body["offer_options"]
    assert 65.0 in body["offer_options"]


def test_create_ride_stores_quote_fields(
    authenticated_passenger,
    authenticated_driver,
):
    prepare_driver_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    with patch(
        "app.services.ride_service.PricingService.quote_trip"
    ) as quote_trip:
        quote_trip.return_value = PricingService.quote_from_estimate(
            TripDistanceEstimate(
                km=Decimal("10"),
                source=DISTANCE_SOURCE_HAVERSINE,
                is_road_distance=False,
            )
        )
        created = create_pending_ride(
            authenticated_passenger["client"],
            authenticated_passenger["headers"],
            payload={**RIDE_CREATE_PAYLOAD, "proposed_fare": 45.0},
        )
    assert created["trip_distance_km"] == 10.0
    assert created["recommended_fare"] == 45.0
    assert created["trip_distance_is_road_distance"] is False
    assert created["passenger_current_offer"] == 45.0


def test_high_fares_are_allowed_including_above_p70(
    authenticated_passenger,
    authenticated_driver,
):
    prepare_driver_online(
        authenticated_driver["client"],
        authenticated_driver["headers"],
    )
    for amount in (80.0, 100.0, 150.0, 200.0):
        created = create_pending_ride(
            authenticated_passenger["client"],
            authenticated_passenger["headers"],
            payload={**RIDE_CREATE_PAYLOAD, "proposed_fare": amount},
        )
        assert created["passenger_current_offer"] == amount
        cancel = authenticated_passenger["client"].put(
            f"/rides/{created['id']}/cancel",
            headers=authenticated_passenger["headers"],
        )
        assert cancel.status_code == 200
