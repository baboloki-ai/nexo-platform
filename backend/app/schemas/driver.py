from pydantic import BaseModel


class DriverLocationUpdate(BaseModel):
    latitude: float
    longitude: float


class DriverStatusResponse(BaseModel):
    message: str
    status: str