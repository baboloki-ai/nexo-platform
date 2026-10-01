from datetime import datetime, timedelta

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.config import RIDE_OFFER_TTL_SECONDS
from app.constants.ride_offer_status import RideOfferStatus
from app.constants.ride_status import RideStatus
from app.models.ride_offer import RideOffer
from app.models.ride_request import RideRequest
from app.models.user import User
from app.services.dispatch_service import DispatchService


class RideOfferExpiryService:
    """
    Expires stale pending RideOffers and redispatches the ride.

    Race-safe: offer status is transitioned with a conditional UPDATE so
    concurrent accept / reject / cancel / expiry cannot double-apply.
    """

    @staticmethod
    def expire_stale_offers(db: Session) -> int:
        """
        Find pending offers older than the TTL and expire each safely.

        Returns the number of offers successfully expired.
        """
        cutoff = datetime.utcnow() - timedelta(seconds=RIDE_OFFER_TTL_SECONDS)

        stale_offer_ids = [
            offer_id
            for (offer_id,) in (
                db.query(RideOffer.id)
                .filter(
                    RideOffer.status == RideOfferStatus.PENDING,
                    RideOffer.offered_at <= cutoff,
                )
                .all()
            )
        ]

        expired_count = 0
        for offer_id in stale_offer_ids:
            if RideOfferExpiryService.expire_offer(db, offer_id):
                expired_count += 1

        return expired_count

    @staticmethod
    def expire_offer(db: Session, offer_id: int) -> bool:
        """
        Conditionally expire a single pending offer and release/redispatch.

        Returns True only when the offer transitioned PENDING → EXPIRED.
        """
        offer = (
            db.query(RideOffer)
            .filter(
                RideOffer.id == offer_id,
                RideOffer.status == RideOfferStatus.PENDING,
            )
            .first()
        )
        if offer is None:
            return False

        ride_id = offer.ride_id
        driver_id = offer.driver_id
        now = datetime.utcnow()

        offer_result = db.execute(
            update(RideOffer)
            .where(
                RideOffer.id == offer_id,
                RideOffer.status == RideOfferStatus.PENDING,
            )
            .values(
                status=RideOfferStatus.EXPIRED,
                responded_at=now,
            )
            .execution_options(synchronize_session=False)
        )

        if offer_result.rowcount != 1:
            return False

        ride_result = db.execute(
            update(RideRequest)
            .where(
                RideRequest.id == ride_id,
                RideRequest.status == RideStatus.PENDING_DRIVER_ACCEPTANCE,
                RideRequest.accepted_driver_id == driver_id,
            )
            .values(
                status=RideStatus.PENDING,
                accepted_driver_id=None,
            )
            .execution_options(synchronize_session=False)
        )

        if ride_result.rowcount == 1:
            # reserved → available; offline (or any other status) unchanged
            db.execute(
                update(User)
                .where(
                    User.id == driver_id,
                    User.availability_status == "reserved",
                )
                .values(availability_status="available")
                .execution_options(synchronize_session=False)
            )

        db.commit()
        db.expire_all()

        if ride_result.rowcount == 1:
            ride = db.get(RideRequest, ride_id)
            if ride is not None and ride.status == RideStatus.PENDING:
                DispatchService.assign_driver(db=db, ride=ride)

        return True
