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

    class Config:
        from_attributes = True