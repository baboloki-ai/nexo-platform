from decimal import Decimal

from sqlalchemy.orm import Session

from app.constants.driver_response import DriverResponseStatus
from app.constants.ride_messages import (
    DRIVER_ON_THE_WAY,
    SYSTEM_MESSAGE_LABEL,
    SYSTEM_MESSAGE_SOURCE,
)
from app.constants.ride_status import RideStatus
from app.models.driver_response import DriverResponse
from app.models.ride_request import RideRequest
from app.models.user import User
from app.models.vehicle import Vehicle
from app.schemas.driver import (
    DriverProfileResponse,
    DriverPublicIdentity,
    DriverPublicVehicle,
)
from app.schemas.ride_request import RideRequestResponse, RideSystemMessage
from app.schemas.vehicle import VehicleResponse
from app.services.distance_provider import DISTANCE_SOURCE_HAVERSINE
from app.services.location_service import LocationService
from app.services.payment_service import PaymentService
from app.utils.money import estimate_pickup_eta_seconds

_LIVE_PICKUP_ETA_STATUSES = (
    RideStatus.ACCEPTED,
    RideStatus.DRIVER_ARRIVING,
)


class DriverIdentityService:
    """Builds driver identity payloads without duplicating User data."""

    @staticmethod
    def primary_vehicle(db: Session, driver_id: int) -> Vehicle | None:
        return (
            db.query(Vehicle)
            .filter(Vehicle.driver_id == driver_id)
            .order_by((Vehicle.verification_status == "approved").desc(), Vehicle.id.asc())
            .first()
        )

    @staticmethod
    def public_identity(
        db: Session,
        driver_id: int | None,
    ) -> DriverPublicIdentity | None:
        if driver_id is None:
            return None

        driver = db.get(User, driver_id)
        if driver is None or driver.role != "driver":
            return None

        vehicle = DriverIdentityService.primary_vehicle(db, driver.id)
        public_vehicle = None
        if vehicle is not None:
            public_vehicle = DriverPublicVehicle(
                make=vehicle.make,
                model=vehicle.model,
                color=vehicle.color,
                registration_number=vehicle.registration_number,
                verification_status=vehicle.verification_status or "pending",
            )

        return DriverPublicIdentity(
            display_name=driver.full_name,
            verification_status=driver.verification_status or "pending",
            vehicle=public_vehicle,
        )

    @staticmethod
    def profile_response(db: Session, driver: User) -> DriverProfileResponse:
        vehicle = DriverIdentityService.primary_vehicle(db, driver.id)
        return DriverProfileResponse(
            id=driver.id,
            display_name=driver.full_name,
            phone_number=driver.phone_number,
            profile_photo_url=driver.profile_photo_url,
            verification_status=driver.verification_status,
            availability_status=driver.availability_status,
            current_latitude=driver.current_latitude,
            current_longitude=driver.current_longitude,
            last_seen=driver.last_seen,
            created_at=driver.created_at,
            updated_at=driver.updated_at,
            vehicle=(
                VehicleResponse.model_validate(vehicle)
                if vehicle is not None
                else None
            ),
        )

    @staticmethod
    def _system_messages(ride: RideRequest) -> list[RideSystemMessage]:
        if ride.accepted_driver_id is None and ride.selected_at is None:
            return []
        return [
            RideSystemMessage(
                source=SYSTEM_MESSAGE_SOURCE,
                label=SYSTEM_MESSAGE_LABEL,
                body=DRIVER_ON_THE_WAY,
                created_at=ride.selected_at,
            )
        ]

    @staticmethod
    def _selected_pickup_support(
        db: Session,
        ride: RideRequest,
    ) -> tuple[Decimal | None, int | None]:
        if ride.accepted_driver_id is None:
            return None, None
        selected = (
            db.query(DriverResponse)
            .filter(
                DriverResponse.ride_id == ride.id,
                DriverResponse.driver_id == ride.accepted_driver_id,
                DriverResponse.status == DriverResponseStatus.SELECTED,
            )
            .first()
        )
        snapshot_distance = (
            selected.pickup_distance_km if selected is not None else None
        )
        snapshot_eta = selected.pickup_eta_seconds if selected is not None else None
        if ride.status not in _LIVE_PICKUP_ETA_STATUSES:
            return snapshot_distance, snapshot_eta
        driver = db.get(User, ride.accepted_driver_id)
        if (
            driver is None
            or ride.pickup_latitude is None
            or ride.pickup_longitude is None
            or driver.current_latitude is None
            or driver.current_longitude is None
        ):
            return snapshot_distance, snapshot_eta
        distance = LocationService.calculate_distance(
            ride.pickup_latitude,
            ride.pickup_longitude,
            driver.current_latitude,
            driver.current_longitude,
        )
        return (
            Decimal(str(round(distance, 3))),
            estimate_pickup_eta_seconds(distance),
        )

    @staticmethod
    def serialize_ride(db: Session, ride: RideRequest) -> RideRequestResponse:
        response = RideRequestResponse.model_validate(ride)
        if response.passenger_current_offer is None:
            response = response.model_copy(
                update={"passenger_current_offer": ride.proposed_fare}
            )
        pickup_distance_km, pickup_eta_seconds = (
            DriverIdentityService._selected_pickup_support(db, ride)
        )
        return response.model_copy(
            update={
                "assigned_driver": DriverIdentityService.public_identity(
                    db,
                    ride.accepted_driver_id,
                ),
                "payment": PaymentService.serialize(
                    PaymentService.current_for_ride(db, ride.id)
                ),
                "trip_distance_source": (
                    DISTANCE_SOURCE_HAVERSINE
                    if ride.trip_distance_km is not None
                    else None
                ),
                "trip_distance_is_road_distance": False,
                "pickup_distance_km": pickup_distance_km,
                "pickup_eta_seconds": pickup_eta_seconds,
                "system_messages": DriverIdentityService._system_messages(ride),
            }
        )

    @staticmethod
    def serialize_rides(
        db: Session,
        rides: list[RideRequest],
    ) -> list[RideRequestResponse]:
        return [
            DriverIdentityService.serialize_ride(db, ride)
            for ride in rides
        ]


