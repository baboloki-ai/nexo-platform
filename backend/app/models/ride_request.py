from datetime import datetime

from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship

from app.database.base import Base


class RideRequest(Base):
    __tablename__ = "ride_requests"

    id = Column(Integer, primary_key=True, index=True)

    passenger_id = Column(
        Integer,
        ForeignKey("passengers.id"),
        nullable=False
    )

    pickup_location = Column(
        String,
        nullable=False
    )

    pickup_latitude = Column(
        Float,
        nullable=True
    )

    pickup_longitude = Column(
        Float,
        nullable=True
    )

    destination = Column(
        String,
        nullable=False
    )

    destination_latitude = Column(
        Float,
        nullable=True
    )

    destination_longitude = Column(
        Float,
        nullable=True
    )

    proposed_fare = Column(
        Float,
        nullable=False
    )

    status = Column(
        String,
        default="pending"
    )

    accepted_driver_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True
    )

    requested_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    passenger = relationship(
        "Passenger",
        back_populates="ride_requests"
    )

    accepted_driver = relationship(
    "User",
    back_populates="accepted_rides",
    foreign_keys=[accepted_driver_id]
)
offers = relationship(
    "RideOffer",
    back_populates="ride",
    cascade="all, delete-orphan"
)