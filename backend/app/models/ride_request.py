from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    event,
    text,
)
from sqlalchemy.orm import relationship

from app.constants.ride_status import RideStatus
from app.database.base import Base

UQ_RIDE_REQUESTS_ONE_ACTIVE_PER_PASSENGER = (
    "uq_ride_requests_one_active_per_passenger"
)
UQ_RIDE_REQUESTS_ONE_ACTIVE_PER_DRIVER = (
    "uq_ride_requests_one_active_per_driver"
)
UQ_RIDE_REQUESTS_ONE_NEXT_PER_DRIVER = (
    "uq_ride_requests_one_next_per_driver"
)

_ACTIVE_RIDE_STATUS_PREDICATE = (
    "status IN ("
    f"'{RideStatus.PENDING}', "
    f"'{RideStatus.PENDING_DRIVER_ACCEPTANCE}', "
    f"'{RideStatus.ACCEPTED}', "
    f"'{RideStatus.DRIVER_ARRIVING}', "
    f"'{RideStatus.DRIVER_ARRIVED}', "
    f"'{RideStatus.IN_PROGRESS}'"
    ")"
)

# Consented shared joiner is accepted onto the current in-progress ride.
# Leave that accepted joiner out of this index. The host ride stays in it.
_ACTIVE_DRIVER_ASSIGNMENT_PREDICATE = (
    "accepted_driver_id IS NOT NULL "
    "AND is_next_ride IS NOT TRUE "
    "AND NOT ("
    "shared_ride_with_id IS NOT NULL "
    "AND shared_ride_consent IS TRUE "
    f"AND status = '{RideStatus.ACCEPTED}'"
    ") "
    "AND status IN ("
    f"'{RideStatus.ACCEPTED}', "
    f"'{RideStatus.DRIVER_ARRIVING}', "
    f"'{RideStatus.DRIVER_ARRIVED}', "
    f"'{RideStatus.IN_PROGRESS}'"
    ")"
)

_NEXT_DRIVER_ASSIGNMENT_PREDICATE = (
    "accepted_driver_id IS NOT NULL "
    "AND is_next_ride IS TRUE "
    f"AND status = '{RideStatus.ACCEPTED}'"
)

_POST_SELECTION_STATUSES = (
    RideStatus.ACCEPTED,
    RideStatus.DRIVER_ARRIVING,
    RideStatus.DRIVER_ARRIVED,
    RideStatus.IN_PROGRESS,
    RideStatus.COMPLETED,
)


class RideRequest(Base):
    __tablename__ = "ride_requests"

    __table_args__ = (
        Index(
            UQ_RIDE_REQUESTS_ONE_ACTIVE_PER_PASSENGER,
            "passenger_id",
            unique=True,
            postgresql_where=text(_ACTIVE_RIDE_STATUS_PREDICATE),
        ),
        Index(
            UQ_RIDE_REQUESTS_ONE_ACTIVE_PER_DRIVER,
            "accepted_driver_id",
            unique=True,
            postgresql_where=text(_ACTIVE_DRIVER_ASSIGNMENT_PREDICATE),
        ),
        Index(
            UQ_RIDE_REQUESTS_ONE_NEXT_PER_DRIVER,
            "accepted_driver_id",
            unique=True,
            postgresql_where=text(_NEXT_DRIVER_ASSIGNMENT_PREDICATE),
        ),
    )

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

    recommended_fare = Column(
        Numeric(10, 2),
        nullable=True,
    )

    passenger_current_offer = Column(
        Numeric(10, 2),
        nullable=False,
    )

    passenger_offer_version = Column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )

    agreed_fare = Column(
        Numeric(10, 2),
        nullable=True,
    )

    trip_distance_km = Column(
        Numeric(8, 3),
        nullable=True,
    )

    selected_at = Column(
        DateTime,
        nullable=True,
    )

    completed_at = Column(
        DateTime,
        nullable=True,
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

    # Next Ride 1.0: accepted future assignment. Current ride stays
    # in_progress; this flag keeps the queued ride out of the current
    # unique index until it is promoted after current completion.
    is_next_ride = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    # Shared Ride pilot.
    shared_ride_with_id = Column(
        Integer,
        ForeignKey("ride_requests.id"),
        nullable=True,
    )

    shared_ride_consent = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
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

    driver_responses = relationship(
        "DriverResponse",
        back_populates="ride",
        cascade="all, delete-orphan"
    )

    negotiation_events = relationship(
        "NegotiationEvent",
        back_populates="ride",
        cascade="all, delete-orphan"
    )

    payments = relationship(
        "Payment",
        back_populates="ride",
        cascade="all, delete-orphan",
    )

    ride_guard_events = relationship(
        "RideGuardEvent",
        back_populates="ride",
        cascade="all, delete-orphan",
    )


@event.listens_for(RideRequest, "before_insert")
def _fill_marketplace_defaults(mapper, connection, target):
    if target.passenger_current_offer is None and target.proposed_fare is not None:
        target.passenger_current_offer = target.proposed_fare
    if not target.passenger_offer_version:
        target.passenger_offer_version = 1
    if (
        target.agreed_fare is None
        and target.status in _POST_SELECTION_STATUSES
        and target.proposed_fare is not None
    ):
        target.agreed_fare = target.proposed_fare
