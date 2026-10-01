from pydantic import BaseModel, Field


class PushSubscriptionKeys(BaseModel):
    p256dh: str = Field(..., min_length=1, max_length=512)
    auth: str = Field(..., min_length=1, max_length=512)


class PushSubscriptionIn(BaseModel):
    endpoint: str = Field(..., min_length=8, max_length=2048)
    keys: PushSubscriptionKeys


class PushSubscriptionDelete(BaseModel):
    endpoint: str = Field(..., min_length=8, max_length=2048)


class PushSubscriptionOut(BaseModel):
    driver_id: int
    endpoint: str


class VapidPublicKeyOut(BaseModel):
    vapid_public_key: str
