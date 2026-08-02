from pydantic import BaseModel


class AcceptRideRequest(BaseModel):
    ride_id: int


class AcceptRideResponse(BaseModel):
    message: str
    ride_id: int
    status: str
    driver_id: int