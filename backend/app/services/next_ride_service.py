from datetime import datetime
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.constants.driver_response import DriverResponseStatus
from app.constants.negotiation import NegotiationAction, NegotiationActorType
from app.constants.ride_status import RideStatus
from app.constants.verification import VerificationStatus
from app.models.driver_response import DriverResponse
from app.models.driver_wallet import DriverWallet
from app.models.ride_request import (
    UQ_RIDE_REQUESTS_ONE_NEXT_PER_DRIVER,
    RideRequest,
)
from app.models.user import User
from app.models.vehicle import Vehicle
from app.services.marketplace_service import MarketplaceService
from app.services.notification_service import NotificationService
from app.services.payment_service import PaymentService
from app.utils.money import (
    DRIVER_WALLET_BELOW_MINIMUM,
    driver_wallet_meets_minimum,
    money_float,
    quantize_pula,
)

_PG_UNIQUE_VIOLATION = "23505"
_UNAVAILABLE = "Ride is no longer available."
_NEXT_REQUIRES_IN_PROGRESS = (
    "Next Ride can only be accepted during an in-progress ride."
)
_NEXT_ALREADY_EXISTS = "Driver already has a Next Ride."
_NEXT_LIFECYCLE_BLOCKED = (
    "Next Ride cannot be started until the current ride is completed."
)


class NextRideService:
    """One accepted future ride while the current ride is in_progress."""

    @staticmethod
    def current_in_progress_ride(
        db: Session,
        driver_id: int,
        *,
        for_update: bool = False,
    ) -> RideRequest | None:
        query = db.query(RideRequest).filter(
            RideRequest.accepted_driver_id == driver_id,
            RideRequest.status == RideStatus.IN_PROGRESS,
            RideRequest.is_next_ride.is_(False),
        )
        if for_update:
            query = query.with_for_update()
        return query.first()

    @staticmethod
    def next_ride(
        db: Session,
        driver_id: int,
        *,
        for_update: bool = False,
    ) -> RideRequest | None:
        query = db.query(RideRequest).filter(
            RideRequest.accepted_driver_id == driver_id,
            RideRequest.is_next_ride.is_(True),
        )
        if for_update:
            query = query.with_for_update()
        return query.first()

    @staticmethod
    def reject_if_next_ride(ride: RideRequest) -> None:
        if ride.is_next_ride:
            raise HTTPException(
                status_code=400,
                detail=_NEXT_LIFECYCLE_BLOCKED,
            )

    @staticmethod
    def promote_after_current_completion(
        db: Session,
        driver_id: int,
    ) -> RideRequest | None:
        """Clear the Next Ride flag so the queued ride becomes current.

        Does not change ride status, notify arrival, or post commission.
        """
        result = db.execute(
            update(RideRequest)
            .where(
                RideRequest.accepted_driver_id == driver_id,
                RideRequest.is_next_ride.is_(True),
                RideRequest.status == RideStatus.ACCEPTED,
            )
            .values(is_next_ride=False)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            return None
        return (
            db.query(RideRequest)
            .filter(
                RideRequest.accepted_driver_id == driver_id,
                RideRequest.is_next_ride.is_(False),
                RideRequest.status == RideStatus.ACCEPTED,
            )
            .order_by(RideRequest.selected_at.desc(), RideRequest.id.desc())
            .first()
        )

    @staticmethod
    def _require_eligible_next_driver(db: Session, driver: User) -> None:
        if driver.role != "driver":
            raise HTTPException(
                status_code=403,
                detail="Only drivers can accept a Next Ride.",
            )
        if driver.verification_status != VerificationStatus.APPROVED:
            raise HTTPException(
                status_code=403,
                detail="Driver account is not approved.",
            )
        approved_vehicle = (
            db.query(Vehicle)
            .filter(
                Vehicle.driver_id == driver.id,
                Vehicle.verification_status == VerificationStatus.APPROVED,
            )
            .first()
        )
        if approved_vehicle is None:
            raise HTTPException(
                status_code=403,
                detail="Driver does not have an approved vehicle.",
            )
        if driver.current_latitude is None or driver.current_longitude is None:
            raise HTTPException(
                status_code=400,
                detail="Current GPS location is required to accept a Next Ride.",
            )
        wallet = (
            db.query(DriverWallet)
            .filter(DriverWallet.driver_id == driver.id)
            .first()
        )
        if wallet is None or not driver_wallet_meets_minimum(
            wallet.available_balance
        ):
            raise HTTPException(
                status_code=400,
                detail=DRIVER_WALLET_BELOW_MINIMUM,
            )

    @staticmethod
    def accept_next_ride(
        db: Session,
        ride_id: int,
        current_user: User,
    ) -> RideRequest:
        driver = (
            db.query(User)
            .filter(User.id == current_user.id)
            .with_for_update()
            .first()
        )
        if driver is None:
            raise HTTPException(status_code=404, detail="Driver not found.")

        NextRideService._require_eligible_next_driver(db, driver)

        current = NextRideService.current_in_progress_ride(
            db,
            driver.id,
            for_update=True,
        )
        if current is None:
            raise HTTPException(
                status_code=400,
                detail=_NEXT_REQUIRES_IN_PROGRESS,
            )

        existing_next = NextRideService.next_ride(
            db,
            driver.id,
            for_update=True,
        )
        if existing_next is not None:
            raise HTTPException(
                status_code=400,
                detail=_NEXT_ALREADY_EXISTS,
            )

        ride = (
            db.query(RideRequest)
            .filter(RideRequest.id == ride_id)
            .with_for_update()
            .first()
        )
        if ride is None:
            raise HTTPException(status_code=404, detail="Ride not found.")
        if (
            ride.status != RideStatus.PENDING
            or ride.accepted_driver_id is not None
            or ride.agreed_fare is not None
        ):
            raise HTTPException(status_code=400, detail=_UNAVAILABLE)

        locked_fare = quantize_pula(ride.passenger_current_offer)
        now = datetime.utcnow()

        try:
            ride_result = db.execute(
                update(RideRequest)
                .where(
                    RideRequest.id == ride.id,
                    RideRequest.status == RideStatus.PENDING,
                    RideRequest.accepted_driver_id.is_(None),
                    RideRequest.agreed_fare.is_(None),
                    RideRequest.is_next_ride.is_(False),
                )
                .values(
                    accepted_driver_id=driver.id,
                    agreed_fare=locked_fare,
                    status=RideStatus.ACCEPTED,
                    selected_at=now,
                    is_next_ride=True,
                )
                .execution_options(synchronize_session=False)
            )
            if ride_result.rowcount != 1:
                db.rollback()
                raise HTTPException(status_code=400, detail=_UNAVAILABLE)

            next_count = (
                db.query(RideRequest)
                .filter(
                    RideRequest.accepted_driver_id == driver.id,
                    RideRequest.is_next_ride.is_(True),
                )
                .count()
            )
            if next_count != 1:
                db.rollback()
                raise HTTPException(
                    status_code=400,
                    detail=_NEXT_ALREADY_EXISTS,
                )

            winner = (
                db.query(DriverResponse)
                .filter(
                    DriverResponse.ride_id == ride.id,
                    DriverResponse.driver_id == driver.id,
                    DriverResponse.status == DriverResponseStatus.OPEN,
                )
                .with_for_update()
                .first()
            )
            winner_id = winner.id if winner is not None else None
            if winner is not None:
                winner.status = DriverResponseStatus.SELECTED
                winner.responded_at = now

            db.execute(
                update(DriverResponse)
                .where(
                    DriverResponse.ride_id == ride.id,
                    DriverResponse.status == DriverResponseStatus.OPEN,
                    *(
                        [DriverResponse.id != winner.id]
                        if winner is not None
                        else []
                    ),
                )
                .values(
                    status=DriverResponseStatus.CLOSED_LOSER,
                    responded_at=now,
                )
                .execution_options(synchronize_session=False)
            )

            db.flush()
            db.refresh(ride)
            PaymentService.create_pending_cash(db, ride)
            MarketplaceService.record_event(
                db,
                ride=ride,
                actor_type=NegotiationActorType.DRIVER,
                actor_user_id=driver.id,
                driver_id=driver.id,
                action=NegotiationAction.DRIVER_ACCEPTED_PASSENGER_OFFER,
                amount=locked_fare,
                resulting_response_status=(
                    DriverResponseStatus.SELECTED
                    if winner is not None
                    else None
                ),
            )
            MarketplaceService.record_event(
                db,
                ride=ride,
                actor_type=NegotiationActorType.SYSTEM,
                driver_id=driver.id,
                action=NegotiationAction.FARE_AGREED,
                amount=locked_fare,
                resulting_response_status=(
                    DriverResponseStatus.SELECTED
                    if winner is not None
                    else None
                ),
            )
            db.commit()
        except HTTPException:
            db.rollback()
            raise
        except IntegrityError as exc:
            db.rollback()
            if NextRideService._is_unique_violation(
                exc,
                UQ_RIDE_REQUESTS_ONE_NEXT_PER_DRIVER,
            ):
                raise HTTPException(
                    status_code=400,
                    detail=_NEXT_ALREADY_EXISTS,
                ) from exc
            if PaymentService.is_constraint_violation(exc):
                raise HTTPException(
                    status_code=400,
                    detail="Payment could not be recorded.",
                ) from exc
            raise

        db.refresh(ride)
        NextRideService._notify_next_accepted(db, ride, winner_id)
        return ride

    @staticmethod
    def _notify_next_accepted(
        db: Session,
        ride: RideRequest,
        winner_response_id: int | None,
    ) -> None:
        event_id = uuid4().hex
        agreed = money_float(ride.agreed_fare)
        NotificationService.notify_ride_agreed(
            passenger_id=ride.passenger_id,
            ride_id=ride.id,
            event_id=event_id,
            passenger_offer_version=ride.passenger_offer_version,
            driver_id=ride.accepted_driver_id,
            agreed_fare=agreed,
            response_id=winner_response_id or 0,
        )
        NotificationService.notify_ride_accepted(
            passenger_id=ride.passenger_id,
            ride_id=ride.id,
            driver_id=ride.accepted_driver_id,
        )
        responses = (
            db.query(DriverResponse)
            .filter(DriverResponse.ride_id == ride.id)
            .all()
        )
        closed_event_id = uuid4().hex
        notified: set[int] = set()
        for row in responses:
            notified.add(row.driver_id)
            NotificationService.notify_marketplace_request_closed(
                driver_id=row.driver_id,
                ride_id=ride.id,
                event_id=closed_event_id,
                reason="selected",
                won=row.driver_id == ride.accepted_driver_id,
                agreed_fare=agreed,
                selected_driver_id=ride.accepted_driver_id,
            )
        if (
            ride.accepted_driver_id is not None
            and ride.accepted_driver_id not in notified
        ):
            NotificationService.notify_marketplace_request_closed(
                driver_id=ride.accepted_driver_id,
                ride_id=ride.id,
                event_id=closed_event_id,
                reason="selected",
                won=True,
                agreed_fare=agreed,
                selected_driver_id=ride.accepted_driver_id,
            )

    @staticmethod
    def _is_unique_violation(exc: IntegrityError, constraint_name: str) -> bool:
        orig = getattr(exc, "orig", None)
        if orig is None:
            return constraint_name in str(exc)
        sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
        if sqlstate is not None and str(sqlstate) != _PG_UNIQUE_VIOLATION:
            return False
        diag = getattr(orig, "diag", None)
        name = getattr(diag, "constraint_name", None) if diag is not None else None
        if name == constraint_name:
            return True
        return constraint_name in str(orig)
