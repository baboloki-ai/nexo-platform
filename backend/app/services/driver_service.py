from datetime import datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.constants.ride_offer_status import RideOfferStatus
from app.constants.ride_status import RideStatus
from app.models.ride_offer import RideOffer
from app.models.ride_request import RideRequest
from app.models.user import User
from app.services.marketplace_service import MarketplaceService
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
        """
        L3.0: driver accepts the current passenger offer as a marketplace
        response. Does not assign the ride.
        """
        driver = db.query(User).filter(User.id == driver_id).first()
        if driver is None:
            return None
        return MarketplaceService.driver_respond(
            db=db,
            ride_id=ride_id,
            current_user=driver,
            response_type="accept_passenger_offer",
            amount=None,
        )

    @staticmethod
    def reject_ride(
        db: Session,
        ride_id: int,
        driver_id: int
    ) -> RideRequest | None:
        """
        L3.0: withdraw the driver's open marketplace response.
        """
        driver = db.query(User).filter(User.id == driver_id).first()
        if driver is None or driver.role != "driver":
            return None
        return MarketplaceService.withdraw_response(
            db=db,
            ride_id=ride_id,
            current_user=driver,
        )
