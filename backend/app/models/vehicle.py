from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

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

    driver = relationship(
        "User",
        back_populates="vehicles"
    )