from datetime import datetime

from sqlalchemy.orm import Session

from app.constants.ride_offer_status import RideOfferStatus
from app.constants.ride_status import RideStatus
from app.models.ride_offer import RideOffer
from app.models.ride_request import RideRequest
from app.models.user import User
from app.services.dispatch_service import DispatchService
from app.services.notification_service import NotificationService


class DriverService:

    @staticmethod
    def update_location(
        db: Session,
        driver: User,
        latitude: float,
        longitude: float,
    ) -> User:
        """
        Updates the driver's current GPS coordinates.

        If the driver has an active ride,
        broadcast the live location to the passenger.
        """

        driver.current_latitude = latitude
        driver.current_longitude = longitude
        driver.last_seen = datetime.utcnow()

        db.commit()
        db.refresh(driver)

        # ------------------------------------------
        # Find driver's active ride
        # ------------------------------------------

        active_ride = (
            db.query(RideRequest)
            .filter(
                RideRequest.accepted_driver_id == driver.id,
                RideRequest.status.in_([
                    RideStatus.ACCEPTED,
                    RideStatus.DRIVER_ARRIVING,
                    RideStatus.DRIVER_ARRIVED,
                    RideStatus.IN_PROGRESS,
                ])
            )
            .first()
        )

        if active_ride:

            NotificationService.send_driver_location(
                passenger_id=active_ride.passenger_id,
                driver_id=driver.id,
                latitude=driver.current_latitude,
                longitude=driver.current_longitude,
            )

        return driver

    @staticmethod
    def accept_ride(
        db: Session,
        ride_id: int,
        driver_id: int
    ) -> RideRequest | None:

        ride = (
            db.query(RideRequest)
            .filter(
                RideRequest.id == ride_id,
                RideRequest.accepted_driver_id == driver_id,
                RideRequest.status == RideStatus.PENDING_DRIVER_ACCEPTANCE
            )
            .first()
        )

        if ride is None:
            return None

        ride.status = RideStatus.ACCEPTED

        offer = (
            db.query(RideOffer)
            .filter(
                RideOffer.ride_id == ride.id,
                RideOffer.driver_id == driver_id,
                RideOffer.status == RideOfferStatus.PENDING
            )
            .first()
        )

        if offer:
            offer.status = RideOfferStatus.ACCEPTED
            offer.responded_at = datetime.utcnow()

        db.commit()
        db.refresh(ride)

        return ride

    @staticmethod
    def reject_ride(
        db: Session,
        ride_id: int,
        driver_id: int
    ) -> RideRequest | None:

        ride = (
            db.query(RideRequest)
            .filter(
                RideRequest.id == ride_id,
                RideRequest.accepted_driver_id == driver_id,
                RideRequest.status == RideStatus.PENDING_DRIVER_ACCEPTANCE
            )
            .first()
        )

        if ride is None:
            return None

        driver = (
            db.query(User)
            .filter(User.id == driver_id)
            .first()
        )

        if driver:
            driver.availability_status = "available"

        offer = (
            db.query(RideOffer)
            .filter(
                RideOffer.ride_id == ride.id,
                RideOffer.driver_id == driver_id,
                RideOffer.status == RideOfferStatus.PENDING
            )
            .first()
        )

        if offer:
            offer.status = RideOfferStatus.REJECTED
            offer.responded_at = datetime.utcnow()

        ride.accepted_driver_id = None
        ride.status = RideStatus.PENDING

        db.commit()

        ride = DispatchService.assign_driver(
            db=db,
            ride=ride
        )

        return ride