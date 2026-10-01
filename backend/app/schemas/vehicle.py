from datetime import datetime

from pydantic import BaseModel


class VehicleCreate(BaseModel):
    make: str
    model: str
    year: int
    color: str
    registration_number: str
    vehicle_type: str


class VehicleUpdate(BaseModel):
    make: str
    model: str
    year: int
    color: str
    registration_number: str
    vehicle_type: str


class VehicleVerificationUpdate(BaseModel):
    status: str


class VehicleResponse(BaseModel):
    id: int
    driver_id: int
    make: str
    model: str
    year: int
    color: str
    registration_number: str
    vehicle_type: str
    verification_status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True
