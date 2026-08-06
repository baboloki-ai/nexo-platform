from sqlalchemy.orm import Session

from app.constants.ride_offer_status import RideOfferStatus
from app.constants.ride_status import RideStatus
from app.models.ride_offer import RideOffer
from app.models.ride_request import RideRequest
from app.models.user import User
from app.services.location_service import LocationService
from app.services.notification_service import NotificationService


class DispatchService:
    """
    Handles driver selection and ride offer creation.

    Responsibilities:
    - Find available drivers
    - Select the nearest driver
    - Create RideOffer records
    - Update ride status

    This service NEVER communicates with WebSockets directly.
    All notifications go through NotificationService.
    """

    @staticmethod
    def assign_driver(
        db: Session,
        ride: RideRequest
    ) -> RideRequest:

        print("🚖 DispatchService.assign_driver() called")

        available_drivers = (
            db.query(User)
            .filter(
                User.role == "driver",
                User.availability_status == "available"
            )
            .all()
        )

        if not available_drivers:
            print("❌ No available drivers.")
            return ride

        closest_driver = None
        shortest_distance = float("inf")

        for driver in available_drivers:

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
                print(f"⏭ Driver {driver.id} already rejected this ride.")
                continue

            if (
                driver.current_latitude is None
                or driver.current_longitude is None
            ):
                print(f"⏭ Driver {driver.id} has no GPS location.")
                continue

            distance = LocationService.calculate_distance(
                ride.pickup_latitude,
                ride.pickup_longitude,
                driver.current_latitude,
                driver.current_longitude
            )

            print(
                f"📍 Driver {driver.id} "
                f"is {distance:.2f} km from passenger."
            )

            if distance < shortest_distance:
                shortest_distance = distance
                closest_driver = driver

        if closest_driver is None:
            print("❌ No suitable driver found.")
            return ride

        print(f"✅ Selected Driver: {closest_driver.id}")

        ride.accepted_driver_id = closest_driver.id
        ride.status = RideStatus.PENDING_DRIVER_ACCEPTANCE

        offer = RideOffer(
            ride_id=ride.id,
            driver_id=closest_driver.id,
            status=RideOfferStatus.PENDING
        )

        db.add(offer)
        db.commit()

        db.refresh(ride)

        print(f"📡 Sending ride offer to Driver {closest_driver.id}")

        NotificationService.send_ride_offer(
            driver_id=closest_driver.id,
            ride_id=ride.id,
            pickup=ride.pickup_location,
            destination=ride.destination,
            fare=ride.proposed_fare,
        )

        print("✅ Ride offer notification sent")

        return ride