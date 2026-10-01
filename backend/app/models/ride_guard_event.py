from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database.base import Base


class RideGuardEvent(Base):
    __tablename__ = "ride_guard_events"

    __table_args__ = (
        Index("ix_ride_guard_events_ride_id", "ride_id"),
        Index("ix_ride_guard_events_driver_id", "driver_id"),
        Index("ix_ride_guard_events_type", "event_type"),
        Index("ix_ride_guard_events_status", "status"),
        Index("ix_ride_guard_events_created_at", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)

    ride_id = Column(
        Integer,
        ForeignKey("ride_requests.id", ondelete="CASCADE"),
        nullable=False,
    )

    driver_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
    )

    event_type = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    status = Column(String, nullable=False)

    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    speed_kmh = Column(Float, nullable=True)
    accuracy_meters = Column(Float, nullable=True)
    heading_degrees = Column(Float, nullable=True)

    message = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = Column(DateTime, nullable=True)

    ride = relationship("RideRequest", back_populates="ride_guard_events")
    driver = relationship("User")
