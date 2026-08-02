from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
    DateTime,
)
from sqlalchemy.orm import relationship

from app.database.base import Base


class RideOffer(Base):
    __tablename__ = "ride_offers"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    ride_id = Column(
        Integer,
        ForeignKey("ride_requests.id"),
        nullable=False
    )

    driver_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    status = Column(
        String,
        default="pending"
    )

    offered_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    responded_at = Column(
        DateTime,
        nullable=True
    )

    ride = relationship(
        "RideRequest",
        back_populates="offers"
    )

    driver = relationship(
        "User",
        back_populates="ride_offers"
    )