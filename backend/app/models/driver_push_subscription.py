from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from app.database.base import Base


class DriverPushSubscription(Base):
    """
    Web Push subscription for one driver browser/device.

    Isolated from ride, wallet, vehicle, and driver lifecycle models.
    Identity is always the authenticated driver_id, never a client-supplied id.
    """

    __tablename__ = "driver_push_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    driver_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    endpoint = Column(String, nullable=False, unique=True)
    p256dh = Column(String, nullable=False)
    auth = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
