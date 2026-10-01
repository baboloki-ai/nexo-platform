"""Botswana launch fare engine.

Recommended fare = max(BASE, BASE + estimated_distance_km × RATE),
rounded to the nearest thebe. There is no maximum fare.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app import config
from app.services.distance_provider import (
    TripDistanceEstimate,
    get_trip_distance_provider,
)
from app.utils.money import MIN_PASSENGER_OFFER, quantize_pula

PASSENGER_OFFER_INCREMENTS = (
    Decimal("0.00"),
    Decimal("5.00"),
    Decimal("10.00"),
    Decimal("20.00"),
)
PASSENGER_OFFER_STEP = Decimal("5.00")
DISTANCE_SOURCE_NONE = "unavailable"


@dataclass(frozen=True)
class FareQuote:
    estimated_trip_distance_km: Decimal | None
    distance_source: str
    is_road_distance: bool
    recommended_fare: Decimal
    minimum_offer: Decimal
    base_fare: Decimal
    fare_per_km: Decimal
    offer_options: list[Decimal]


class PricingService:
    @staticmethod
    def base_fare() -> Decimal:
        return quantize_pula(config.NEXO_BASE_FARE)

    @staticmethod
    def fare_per_km() -> Decimal:
        return quantize_pula(config.NEXO_FARE_PER_KM)

    @staticmethod
    def recommended_fare_from_distance(distance_km: Decimal | float | None) -> Decimal:
        """Provider-independent: one distance in, one recommended fare out."""
        base = PricingService.base_fare()
        rate = PricingService.fare_per_km()
        if distance_km is None:
            return base
        distance = Decimal(str(distance_km))
        if distance < 0:
            distance = Decimal("0")
        computed = quantize_pula(base + (distance * rate))
        recommended = computed if computed > base else base
        if recommended < MIN_PASSENGER_OFFER:
            return MIN_PASSENGER_OFFER
        return recommended

    @staticmethod
    def passenger_offer_options(recommended_fare: Decimal | float) -> list[Decimal]:
        recommended = quantize_pula(recommended_fare)
        if recommended < MIN_PASSENGER_OFFER:
            recommended = MIN_PASSENGER_OFFER
        amounts: list[Decimal] = []
        seen: set[Decimal] = set()
        for increment in PASSENGER_OFFER_INCREMENTS:
            amount = quantize_pula(recommended + increment)
            if amount < MIN_PASSENGER_OFFER:
                amount = MIN_PASSENGER_OFFER
            if amount not in seen:
                seen.add(amount)
                amounts.append(amount)
        return amounts

    @staticmethod
    def quote_from_estimate(estimate: TripDistanceEstimate | None) -> FareQuote:
        distance_km = estimate.km if estimate is not None else None
        recommended = PricingService.recommended_fare_from_distance(distance_km)
        return FareQuote(
            estimated_trip_distance_km=distance_km,
            distance_source=(
                estimate.source if estimate is not None else DISTANCE_SOURCE_NONE
            ),
            is_road_distance=(
                estimate.is_road_distance if estimate is not None else False
            ),
            recommended_fare=recommended,
            minimum_offer=MIN_PASSENGER_OFFER,
            base_fare=PricingService.base_fare(),
            fare_per_km=PricingService.fare_per_km(),
            offer_options=PricingService.passenger_offer_options(recommended),
        )

    @staticmethod
    def quote_trip(
        pickup_latitude: float | None,
        pickup_longitude: float | None,
        destination_latitude: float | None,
        destination_longitude: float | None,
    ) -> FareQuote:
        estimate = get_trip_distance_provider().estimate(
            pickup_latitude,
            pickup_longitude,
            destination_latitude,
            destination_longitude,
        )
        return PricingService.quote_from_estimate(estimate)

    @staticmethod
    def serialize_quote(quote: FareQuote) -> dict:
        return {
            "estimated_trip_distance_km": (
                float(quote.estimated_trip_distance_km)
                if quote.estimated_trip_distance_km is not None
                else None
            ),
            "distance_source": quote.distance_source,
            "is_road_distance": quote.is_road_distance,
            "recommended_fare": float(quote.recommended_fare),
            "minimum_offer": float(quote.minimum_offer),
            "base_fare": float(quote.base_fare),
            "fare_per_km": float(quote.fare_per_km),
            "offer_options": [float(amount) for amount in quote.offer_options],
        }
