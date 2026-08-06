from datetime import datetime

from sqlalchemy.orm import Session

from app.constants.ride_status import RideStatus
from app.models.ride_request import RideRequest
from app.models.user import User
from app.services.notification_service import NotificationService


class GPSService:
    """
    Handles all GPS and location-related operations.
    """

    @staticmethod
    def update_driver_location(
        db: Session,
        driver: User,
        latitude: float,
        longitude: float,
    ) -> User:
        """
        Updates the driver's GPS location and broadcasts it
        to the passenger if the driver has an active ride.
        """

        # ------------------------------------------
        # Update driver's location
        # ------------------------------------------

        driver.current_latitude = latitude
        driver.current_longitude = longitude
        driver.last_seen = datetime.utcnow()

        db.commit()
        db.refresh(driver)

        # ------------------------------------------
        # Find active ride
        # ------------------------------------------

        active_ride = (
            db.query(RideRequest)
            .filter(
                RideRequest.accepted_driver_id == driver.id,
                RideRequest.status.in_(
                    [
                        RideStatus.ACCEPTED,
                        RideStatus.DRIVER_ARRIVING,
                        RideStatus.DRIVER_ARRIVED,
                        RideStatus.IN_PROGRESS,
                    ]
                ),
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