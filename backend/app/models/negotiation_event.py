from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import relationship

from app.database.base import Base


class NegotiationEvent(Base):
    __tablename__ = "negotiation_events"

    __table_args__ = (
        Index("ix_negotiation_events_ride_id", "ride_id"),
    )

    id = Column(Integer, primary_key=True, index=True)

    ride_id = Column(
        Integer,
        ForeignKey("ride_requests.id"),
        nullable=False,
    )

    actor_type = Column(String, nullable=False)

    actor_user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
    )

    driver_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
    )

    action = Column(String, nullable=False)

    amount = Column(Numeric(10, 2), nullable=True)

    resulting_ride_status = Column(String, nullable=True)

    resulting_response_status = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    ride = relationship(
        "RideRequest",
        back_populates="negotiation_events",
    )
