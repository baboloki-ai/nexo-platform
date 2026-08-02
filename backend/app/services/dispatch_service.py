from sqlalchemy.orm import Session

from app.constants.ride_offer_status import RideOfferStatus
from app.constants.ride_status import RideStatus
from app.models.ride_offer import RideOffer
from app.models.ride_request import RideRequest
from app.models.user import User
from app.services.location_service import LocationService


class DispatchService:

    @staticmethod
    def assign_driver(
        db: Session,
        ride: RideRequest
    ) -> RideRequest:
        """
        Assign the nearest available driver to a ride.
        """

        available_drivers = (
            db.query(User)
            .filter(
                User.role == "driver",
                User.availability_status == "available"
            )
            .all()
        )

        if not available_drivers:
            return ride

        closest_driver = None
        shortest_distance = float("inf")

        for driver in available_drivers:

            # Skip drivers who already rejected this ride
            existing_offer = (
                db.query(RideOffer)
                .filter(
                    RideOffer.ride_id == ride.id,
                    RideOffer.driver_id == driver.id,
                    RideOffer.status == RideOfferStatus.REJECTED
                )
                .first()
            )

            if existing_offer:
                continue

            # Skip drivers without GPS
            if (
                driver.current_latitude is None
                or driver.current_longitude is None
            ):
                continue

            distance = LocationService.calculate_distance(
                ride.pickup_latitude,
                ride.pickup_longitude,
                driver.current_latitude,
                driver.current_longitude
            )

            if distance < shortest_distance:
                shortest_distance = distance
                closest_driver = driver

        # No suitable driver found
        if closest_driver is None:
            return ride

        ride.accepted_driver_id = closest_driver.id
        ride.status = RideStatus.PENDING_DRIVER_ACCEPTANCE

        closest_driver.availability_status = "busy"

        offer = RideOffer(
            ride_id=ride.id,
            driver_id=closest_driver.id,
            status=RideOfferStatus.PENDING
        )

        db.add(offer)

        db.commit()

        db.refresh(closest_driver)
        db.refresh(ride)

        return ride