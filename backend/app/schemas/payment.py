from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, field_serializer

from app.utils.money import money_float


class PaymentPublic(BaseModel):
    """Safe passenger/driver view of a payment. No secrets or internals."""

    id: int
    ride_id: int
    amount: Decimal
    currency: str
    method: str
    status: str
    paid_at: datetime | None = None
    settlement_status: str

    class Config:
        from_attributes = True

    @field_serializer("amount")
    def _serialize_amount(self, value):
        return money_float(value)
