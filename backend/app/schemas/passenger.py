from pydantic import BaseModel
from typing import Optional


class PassengerCreate(BaseModel):
    first_name: str
    last_name: str
    phone: str
    email: Optional[str] = None


class PassengerUpdate(BaseModel):
    first_name: str
    last_name: str
    phone: str
    email: Optional[str] = None


class PassengerResponse(BaseModel):
    id: int
    user_id: int
    first_name: str
    last_name: str
    phone: str
    email: Optional[str] = None

    class Config:
        from_attributes = True