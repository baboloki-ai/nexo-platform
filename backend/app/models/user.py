from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String
from sqlalchemy.orm import relationship

from app.database.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    phone_number = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    role = Column(String, default="passenger")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Future-safe; no document/photo upload in L1.
    profile_photo_url = Column(String, nullable=True)

    # Driver verification. Passengers leave this null.
    # New drivers are set to pending at registration.
    verification_status = Column(String, nullable=True)

    # ==========================
    # Driver Dispatch Fields
    # ==========================
    availability_status = Column(String, default="offline")
    current_latitude = Column(Float, nullable=True)
    current_longitude = Column(Float, nullable=True)
    last_seen = Column(DateTime, nullable=True)

    # ==========================
    # Relationships
    # ==========================
    vehicles = relationship(
        "Vehicle",
        back_populates="driver",
        cascade="all, delete-orphan"
    )

    passengers = relationship(
        "Passenger",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    accepted_rides = relationship(
        "RideRequest",
        back_populates="accepted_driver",
        foreign_keys="RideRequest.accepted_driver_id"
    )

    ride_offers = relationship(
        "RideOffer",
        back_populates="driver"
    )

    driver_responses = relationship(
        "DriverResponse",
        back_populates="driver"
    )

    wallet = relationship(
        "DriverWallet",
        back_populates="driver",
        uselist=False,
        lazy="noload",
    )
