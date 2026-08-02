from sqlalchemy import Column, Integer, String, DateTime, Float
from sqlalchemy.orm import relationship
from datetime import datetime

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

    # ==========================
    # Driver Dispatch Fields
    # ==========================
    availability_status = Column(String, default="offline")
    current_latitude = Column(Float, nullable=True)
    current_longitude = Column(Float, nullable=True)
    last_seen = Column(DateTime, nullable=True)

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