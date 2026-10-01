from datetime import datetime

from sqlalchemy.orm import Session

from app.constants.ride_status import RideStatus
from app.models.ride_request import RideRequest
from app.models.user import User
from app.services.notification_service import NotificationService
from app.services.ride_guard_service import RideGuardService


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
        accuracy: float | None = None,
        speed: float | None = None,
        heading: float | None = None,
        timestamp: float | None = None,
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

            RideGuardService.record_gps_update(
                db=db,
                ride_id=active_ride.id,
                driver_id=driver.id,
                latitude=latitude,
                longitude=longitude,
                speed_kmh=(speed * 3.6 if speed is not None else None),
                accuracy_meters=accuracy,
                heading_degrees=heading,
                device_timestamp=timestamp,
            )

            NotificationService.send_driver_location(
                passenger_id=active_ride.passenger_id,
                driver_id=driver.id,
                latitude=driver.current_latitude,
                longitude=driver.current_longitude,
            )

        return driver