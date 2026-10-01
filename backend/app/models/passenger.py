from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

from app.database.base import Base


class Passenger(Base):
    __tablename__ = "passengers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))

    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    email = Column(String, nullable=True)

    user = relationship(
        "User",
        back_populates="passengers"
    )

    ride_requests = relationship(
        "RideRequest",
        back_populates="passenger",
    )