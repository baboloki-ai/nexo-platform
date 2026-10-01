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

from app.constants.driver_response import DriverResponseStatus
from app.database.base import Base

UQ_DRIVER_RESPONSES_ONE_OPEN_PER_DRIVER_RIDE = (
    "uq_driver_responses_one_open_per_driver_ride"
)


class DriverResponse(Base):
    __tablename__ = "driver_responses"

    __table_args__ = (
        Index(
            UQ_DRIVER_RESPONSES_ONE_OPEN_PER_DRIVER_RIDE,
            "ride_id",
            "driver_id",
            unique=True,
            postgresql_where=text(f"status = '{DriverResponseStatus.OPEN}'"),
        ),
        Index("ix_driver_responses_ride_id", "ride_id"),
        Index("ix_driver_responses_driver_id", "driver_id"),
    )

    id = Column(Integer, primary_key=True, index=True)

    ride_id = Column(
        Integer,
        ForeignKey("ride_requests.id"),
        nullable=False,
    )

    driver_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
    )

    response_type = Column(String, nullable=False)

    amount = Column(Numeric(10, 2), nullable=False)

    passenger_offer_version_at_submit = Column(Integer, nullable=False)

    passenger_offer_amount_at_submit = Column(Numeric(10, 2), nullable=False)

    status = Column(
        String,
        nullable=False,
        default=DriverResponseStatus.OPEN,
    )

    pickup_distance_km = Column(Numeric(8, 3), nullable=True)

    pickup_eta_seconds = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    expires_at = Column(DateTime, nullable=True)

    responded_at = Column(DateTime, nullable=True)

    ride = relationship(
        "RideRequest",
        back_populates="driver_responses",
    )

    driver = relationship(
        "User",
        back_populates="driver_responses",
    )
