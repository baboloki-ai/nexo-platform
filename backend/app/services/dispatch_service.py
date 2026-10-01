from sqlalchemy.orm import Session

from app.models.ride_request import RideRequest
from app.services.marketplace_service import MarketplaceService
from app.services.notification_service import NotificationService


class DispatchService:
    """
    L3.0 marketplace broadcast.

    Does not claim a driver, reserve availability, or auto-assign
    nearest/cheapest. Pickup distance is decision-support only.
    """

    @staticmethod
    def _terminalize_no_driver_available(
        db: Session,
        ride: RideRequest,
    ) -> RideRequest:
        """
        Retained for Phase 3 tests that call it directly.
        Marketplace create/broadcast does not terminalize an open request.
        """
        from sqlalchemy import update

        from app.constants.ride_status import RideStatus

        result = db.execute(
            update(RideRequest)
            .where(
                RideRequest.id == ride.id,
                RideRequest.status == RideStatus.PENDING,
                RideRequest.accepted_driver_id.is_(None),
            )
            .values(status=RideStatus.NO_DRIVER_AVAILABLE)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            db.refresh(ride)
            return ride

        db.commit()
        db.refresh(ride)
        NotificationService.notify_no_driver_available(
            passenger_id=ride.passenger_id,
            ride_id=ride.id,
        )
        return ride

    @staticmethod
    def assign_driver(
        db: Session,
        ride: RideRequest,
    ) -> RideRequest:
        return DispatchService.broadcast_marketplace_request(db=db, ride=ride)

    @staticmethod
    def broadcast_marketplace_request(
        db: Session,
        ride: RideRequest,
    ) -> RideRequest:
        return MarketplaceService.broadcast_marketplace_request(db=db, ride=ride)
