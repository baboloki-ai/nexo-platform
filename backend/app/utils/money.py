from decimal import Decimal, ROUND_HALF_UP
from typing import Any

THEBE = Decimal("0.01")
MIN_PASSENGER_OFFER = Decimal("20.00")
# Operating gate: drivers may work with any balance strictly above P0.
MIN_DRIVER_WALLET = Decimal("0.00")
LAUNCH_SEED_AMOUNT = Decimal("40.00")
DRIVER_WALLET_BELOW_MINIMUM = "Driver wallet must have a balance above P0."
# Launch commission: 8% of the final agreed fare. No cap.
COMMISSION_RATE = Decimal("0.08")
COUNTER_OFFER_INCREMENTS = (
    Decimal("2.00"),
    Decimal("5.00"),
    Decimal("8.00"),
)
# Decision-support ETA only. Not traffic-aware road routing.
ASSUMED_PICKUP_SPEED_KMH = Decimal("30")


def quantize_pula(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(THEBE, rounding=ROUND_HALF_UP)


def driver_wallet_meets_minimum(balance: Any) -> bool:
    """True when the wallet can operate: strictly greater than P0.00."""
    if balance is None:
        return False
    return quantize_pula(balance) > MIN_DRIVER_WALLET


def money_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(quantize_pula(value))


def calculate_commission(agreed_fare: Any) -> Decimal:
    """8% of agreed fare, half-up to thebe. No commission cap."""
    fare = quantize_pula(agreed_fare)
    return quantize_pula(fare * COMMISSION_RATE)


def driver_net_from_agreed(agreed_fare: Any) -> Decimal:
    fare = quantize_pula(agreed_fare)
    return fare - calculate_commission(fare)


def generate_counter_offer_amounts(passenger_current_offer: Any) -> list[Decimal]:
    base = quantize_pula(passenger_current_offer)
    amounts: list[Decimal] = []
    for increment in COUNTER_OFFER_INCREMENTS:
        amount = quantize_pula(base + increment)
        if amount > base:
            amounts.append(amount)
    return amounts


def estimate_pickup_eta_seconds(distance_km: float | Decimal | None) -> int | None:
    if distance_km is None:
        return None
    distance = Decimal(str(distance_km))
    if distance < 0:
        return None
    hours = distance / ASSUMED_PICKUP_SPEED_KMH
    return int((hours * Decimal("3600")).to_integral_value(rounding=ROUND_HALF_UP))
