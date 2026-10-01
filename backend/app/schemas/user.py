from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    full_name: str
    phone_number: str
    email: EmailStr
    password: str
    role: str = "passenger"


class UserResponse(BaseModel):
    id: int
    full_name: str
    phone_number: str
    email: EmailStr
    role: str
    verification_status: str | None = None
    profile_photo_url: str | None = None
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    message: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class ResetPasswordResponse(BaseModel):
    message: str
