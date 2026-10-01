from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.constants.verification import VerificationStatus
from app.database.base import Base


class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True, index=True)

    driver_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    make = Column(String, nullable=False)
    model = Column(String, nullable=False)
    year = Column(Integer, nullable=False)
    color = Column(String, nullable=False)
    registration_number = Column(
        String,
        unique=True,
        nullable=False
    )
    vehicle_type = Column(String, nullable=False)
    verification_status = Column(
        String,
        nullable=False,
        default=VerificationStatus.PENDING,
    )
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    driver = relationship(
        "User",
        back_populates="vehicles"
    )
