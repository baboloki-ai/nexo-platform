from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    text,
)
from sqlalchemy.orm import relationship

from app.constants.payment import (
    PaymentCurrency,
    PaymentStatus,
    RefundStatus,
)
from app.database.base import Base

UQ_PAYMENTS_ONE_PAID_PER_RIDE = "uq_payments_one_paid_per_ride"
UQ_PAYMENTS_ONE_OPEN_PER_RIDE = "uq_payments_one_open_per_ride"
UQ_PAYMENTS_PROVIDER_REFERENCE = "uq_payments_provider_reference"


class Payment(Base):
    __tablename__ = "payments"

    __table_args__ = (
        Index(
            UQ_PAYMENTS_ONE_PAID_PER_RIDE,
            "ride_id",
            unique=True,
            postgresql_where=text(f"status = '{PaymentStatus.PAID}'"),
        ),
        Index(
            UQ_PAYMENTS_ONE_OPEN_PER_RIDE,
            "ride_id",
            unique=True,
            postgresql_where=text(
                f"status IN ('{PaymentStatus.PENDING}', '{PaymentStatus.PROCESSING}')"
            ),
        ),
        Index(
            UQ_PAYMENTS_PROVIDER_REFERENCE,
            "provider",
            "provider_reference",
            unique=True,
            postgresql_where=text("provider_reference IS NOT NULL"),
        ),
        Index("ix_payments_ride_id", "ride_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    ride_id = Column(
        Integer,
        ForeignKey("ride_requests.id"),
        nullable=False,
    )
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(
        String,
        nullable=False,
        default=PaymentCurrency.BWP,
        server_default=PaymentCurrency.BWP,
    )
    method = Column(String, nullable=False)
    status = Column(
        String,
        nullable=False,
        default=PaymentStatus.PENDING,
        server_default=PaymentStatus.PENDING,
    )
    provider = Column(String, nullable=True)
    provider_reference = Column(String, nullable=True)
    idempotency_key = Column(String, nullable=True)
    attempt_number = Column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    paid_at = Column(DateTime, nullable=True)
    failed_at = Column(DateTime, nullable=True)
    failure_code = Column(String, nullable=True)
    failure_message = Column(String, nullable=True)
    cash_confirmed_at = Column(DateTime, nullable=True)
    cash_confirmed_by_user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
    )
    settlement_status = Column(String, nullable=False)
    settled_at = Column(DateTime, nullable=True)
    refund_status = Column(
        String,
        nullable=False,
        default=RefundStatus.NONE,
        server_default=RefundStatus.NONE,
    )
    refunded_at = Column(DateTime, nullable=True)
    refund_provider_reference = Column(String, nullable=True)
    refund_amount = Column(Numeric(10, 2), nullable=True)

    ride = relationship(
        "RideRequest",
        back_populates="payments",
    )
    cash_confirmed_by = relationship(
        "User",
        foreign_keys=[cash_confirmed_by_user_id],
        lazy="noload",
    )
