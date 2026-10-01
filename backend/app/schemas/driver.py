from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.vehicle import VehicleResponse


class DriverLocationUpdate(BaseModel):
    latitude: float
    longitude: float
    accuracy: float | None = None
    speed: float | None = None
    heading: float | None = None
    timestamp: float | None = None


class DriverStatusResponse(BaseModel):
    message: str
    status: str


class DriverProfileUpdate(BaseModel):
    display_name: str | None = None
    phone_number: str | None = None
    profile_photo_url: str | None = None


class DriverPublicVehicle(BaseModel):
    make: str
    model: str
    color: str
    registration_number: str
    verification_status: str


class DriverPublicIdentity(BaseModel):
    display_name: str
    verification_status: str
    vehicle: DriverPublicVehicle | None = None


class DriverProfileResponse(BaseModel):
    id: int
    display_name: str
    phone_number: str
    profile_photo_url: str | None = None
    verification_status: str | None = None
    availability_status: str | None = None
    current_latitude: float | None = None
    current_longitude: float | None = None
    last_seen: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    vehicle: VehicleResponse | None = None


class DriverVerificationUpdate(BaseModel):
    status: str


class WalletLedgerEntryOut(BaseModel):
    id: int
    driver_id: int
    ride_id: int | None = None
    entry_type: str
    amount: float
    balance_after: float
    created_at: datetime


class DriverWalletResponse(BaseModel):
    driver_id: int
    available_balance: float
    minimum_balance: float
    meets_minimum: bool
    updated_at: datetime | None = None
    ledger: list[WalletLedgerEntryOut] = Field(default_factory=list)


class DriverWalletCreditRequest(BaseModel):
    amount: Decimal = Field(..., gt=0)


class DriverPerformanceResponse(BaseModel):
    completed_rides: int
    today_gross: float
    today_commission: float
    today_net: float
    wallet_balance: float
    wallet_minimum: float
    meets_wallet_minimum: bool
    commission_rate: float


class DemandCell(BaseModel):
    latitude: float
    longitude: float
    count: int


class DemandDriverPoint(BaseModel):
    driver_id: int
    latitude: float
    longitude: float
    last_seen: datetime | None = None
    self: bool = False


class DriverDemandResponse(BaseModel):
    window_minutes: int
    cells: list[DemandCell]
    online_drivers: list[DemandDriverPoint]


class DriverOpenRequest(BaseModel):
    ride_id: int
    pickup_location: str
    pickup_latitude: float | None = None
    pickup_longitude: float | None = None
    destination: str
    destination_latitude: float | None = None
    destination_longitude: float | None = None
    passenger_current_offer: float | None = None
    passenger_offer_version: int
    trip_distance_km: float | None = None
    pickup_distance_km: float | None = None
    pickup_eta_seconds: int | None = None
    requested_at: datetime
    my_response: dict | None = None
    cash: bool = True

