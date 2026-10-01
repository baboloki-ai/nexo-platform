from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_serializer, field_validator

from app.constants.driver_response import DriverResponseType
from app.constants.negotiation import PassengerOfferAction
from app.constants.ride_messages import SYSTEM_MESSAGE_LABEL, SYSTEM_MESSAGE_SOURCE
from app.schemas.driver import DriverPublicIdentity
from app.schemas.payment import PaymentPublic
from app.utils.money import MIN_PASSENGER_OFFER, money_float, quantize_pula


def _quantize_optional_money(value):
    if value is None:
        return None
    return quantize_pula(value)


class RideRequestCreate(BaseModel):
    pickup_location: str
    pickup_latitude: float
    pickup_longitude: float

    destination: str
    destination_latitude: float
    destination_longitude: float

    proposed_fare: Decimal = Field(..., ge=MIN_PASSENGER_OFFER)

    @field_validator("proposed_fare", mode="before")
    @classmethod
    def _quantize_proposed_fare(cls, value):
        return quantize_pula(value)


class FareQuoteRequest(BaseModel):
    pickup_latitude: float
    pickup_longitude: float
    destination_latitude: float
    destination_longitude: float


class FareQuoteResponse(BaseModel):
    estimated_trip_distance_km: float | None = None
    distance_source: str
    is_road_distance: bool = False
    recommended_fare: float
    minimum_offer: float
    base_fare: float
    fare_per_km: float
    offer_options: list[float]


class RideSystemMessage(BaseModel):
    source: str = SYSTEM_MESSAGE_SOURCE
    label: str = SYSTEM_MESSAGE_LABEL
    body: str
    created_at: datetime | None = None


class RideRequestResponse(BaseModel):
    id: int
    passenger_id: int

    pickup_location: str
    pickup_latitude: float | None = None
    pickup_longitude: float | None = None

    destination: str
    destination_latitude: float | None = None
    destination_longitude: float | None = None

    proposed_fare: float
    recommended_fare: Decimal | None = None
    passenger_current_offer: Decimal | None = None
    passenger_offer_version: int = 1
    agreed_fare: Decimal | None = None
    trip_distance_km: Decimal | None = None
    trip_distance_source: str | None = None
    trip_distance_is_road_distance: bool = False
    pickup_distance_km: Decimal | None = None
    pickup_eta_seconds: int | None = None
    selected_at: datetime | None = None
    completed_at: datetime | None = None
    status: str
    accepted_driver_id: int | None = None
    is_next_ride: bool = False
    shared_ride_with_id: int | None = None
    shared_ride_consent: bool = False
    requested_at: datetime
    assigned_driver: DriverPublicIdentity | None = None
    payment: PaymentPublic | None = None
    system_messages: list[RideSystemMessage] = Field(default_factory=list)

    class Config:
        from_attributes = True

    @field_serializer(
        "recommended_fare",
        "passenger_current_offer",
        "agreed_fare",
        "trip_distance_km",
        "pickup_distance_km",
    )
    def _serialize_decimal(self, value):
        return money_float(value)


class PassengerOfferUpdate(BaseModel):
    action: Literal[
        PassengerOfferAction.INCREASE,
        PassengerOfferAction.MAINTAIN,
    ]
    amount: Decimal | None = None
    passenger_offer_version: int | None = None

    @field_validator("amount", mode="before")
    @classmethod
    def _quantize_amount(cls, value):
        return _quantize_optional_money(value)


class DriverRespondRequest(BaseModel):
    response_type: Literal[
        DriverResponseType.ACCEPT_PASSENGER_OFFER,
        DriverResponseType.COUNTER_OFFER,
    ]
    amount: Decimal | None = None

    @field_validator("amount", mode="before")
    @classmethod
    def _quantize_amount(cls, value):
        return _quantize_optional_money(value)


class SelectDriverRequest(BaseModel):
    response_id: int


class SharedRideConsentRequest(BaseModel):
    consent: bool


class CounterOfferOptionsResponse(BaseModel):
    ride_id: int
    passenger_current_offer: float
    passenger_offer_version: int
    amounts: list[float]


class DriverResponseOut(BaseModel):
    id: int
    ride_id: int
    driver_id: int
    response_type: str
    amount: Decimal
    status: str
    passenger_offer_version_at_submit: int
    passenger_offer_amount_at_submit: Decimal
    pickup_distance_km: Decimal | None = None
    pickup_eta_seconds: int | None = None
    created_at: datetime
    expires_at: datetime | None = None
    responded_at: datetime | None = None
    driver: DriverPublicIdentity | None = None

    class Config:
        from_attributes = True

    @field_serializer(
        "amount",
        "passenger_offer_amount_at_submit",
        "pickup_distance_km",
    )
    def _serialize_decimal(self, value):
        return money_float(value)


class NegotiationEventOut(BaseModel):
    id: int
    ride_id: int
    actor_type: str
    actor_user_id: int | None = None
    driver_id: int | None = None
    action: str
    amount: Decimal | None = None
    resulting_ride_status: str | None = None
    resulting_response_status: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True

    @field_serializer("amount")
    def _serialize_amount(self, value):
        return money_float(value)


