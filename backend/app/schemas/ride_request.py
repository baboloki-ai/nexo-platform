from datetime import datetime

from pydantic import BaseModel


class RideRequestCreate(BaseModel):
    pickup_location: str
    pickup_latitude: float
    pickup_longitude: float

    destination: str
    destination_latitude: float
    destination_longitude: float

    proposed_fare: float


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
    status: str
    accepted_driver_id: int | None = None
    requested_at: datetime

    class Config:
        from_attributes = True