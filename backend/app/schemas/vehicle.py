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


class VehicleResponse(BaseModel):
    id: int
    driver_id: int
    make: str
    model: str
    year: int
    color: str
    registration_number: str
    vehicle_type: str

    class Config:
        from_attributes = True