"""Trip distance estimates.

The fare engine consumes one distance value. This module is the only place
that knows how that value is produced. Launch uses Haversine great-circle
distance and labels it as estimated — it is not road distance.

A road-routing provider can replace HaversineTripDistanceProvider later
without rewriting PricingService.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.services.location_service import LocationService

DISTANCE_SOURCE_HAVERSINE = "estimated_haversine"


@dataclass(frozen=True)
class TripDistanceEstimate:
    km: Decimal
    source: str
    is_road_distance: bool


class TripDistanceProvider:
    """Provider-independent distance contract for the fare engine."""

    def estimate(
        self,
        pickup_latitude: float | None,
        pickup_longitude: float | None,
        destination_latitude: float | None,
        destination_longitude: float | None,
    ) -> TripDistanceEstimate | None:
        raise NotImplementedError


class HaversineTripDistanceProvider(TripDistanceProvider):
    """Straight-line estimate. Not traffic-aware and not road routing."""

    SOURCE = DISTANCE_SOURCE_HAVERSINE

    def estimate(
        self,
        pickup_latitude: float | None,
        pickup_longitude: float | None,
        destination_latitude: float | None,
        destination_longitude: float | None,
    ) -> TripDistanceEstimate | None:
        if None in (
            pickup_latitude,
            pickup_longitude,
            destination_latitude,
            destination_longitude,
        ):
            return None
        distance = LocationService.calculate_distance(
            pickup_latitude,
            pickup_longitude,
            destination_latitude,
            destination_longitude,
        )
        km = Decimal(str(round(distance, 3)))
        return TripDistanceEstimate(
            km=km,
            source=self.SOURCE,
            is_road_distance=False,
        )


def get_trip_distance_provider() -> TripDistanceProvider:
    """Return the configured distance provider.

    No paid routing service is wired. When a real router is configured,
    swap the implementation here.
    """
    return HaversineTripDistanceProvider()
