from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.constants.negotiation import NegotiationAction, NegotiationActorType
from app.constants.ride_offer_status import RideOfferStatus
from app.constants.ride_status import RideStatus
from app.models.passenger import Passenger
from app.models.ride_offer import RideOffer
from app.models.ride_request import (
    UQ_RIDE_REQUESTS_ONE_ACTIVE_PER_PASSENGER,
    RideRequest,
)
from app.models.user import User
from app.services.dispatch_service import DispatchService
from app.services.marketplace_service import MarketplaceService
from app.services.next_ride_service import NextRideService
from app.services.notification_service import NotificationService
from app.services.payment_service import PaymentService
from app.services.pricing_service import PricingService
from app.services.wallet_service import WalletService
from app.services.shared_ride_service import SharedRideService
from app.utils.money import MIN_PASSENGER_OFFER, quantize_pula

_PG_UNIQUE_VIOLATION = "23505"


class RideService:

    # ==========================================================
    # CREATE RIDE
    # ==========================================================

    @staticmethod
    def create_ride(
        db: Session,
        current_user: User,
        pickup_location: str,
        pickup_latitude: float,
        pickup_longitude: float,
        destination: str,
        destination_latitude: float,
        destination_longitude: float,
        proposed_fare: float,
    ):
        if current_user.role != "passenger":
            raise HTTPException(
                status_code=403,
                detail="Only passengers can create ride requests.",
            )

        passenger = (
            db.query(Passenger)
            .filter(
                Passenger.user_id == current_user.id
            )
            .first()
        )

        if passenger is None:
            raise HTTPException(
                status_code=404,
                detail="Passenger profile not found.",
            )

        active_ride = (
            db.query(RideRequest)
            .filter(
                RideRequest.passenger_id == passenger.id,
                RideRequest.status.in_(
                    [
                        RideStatus.PENDING,
                        RideStatus.PENDING_DRIVER_ACCEPTANCE,
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
            raise HTTPException(
                status_code=400,
                detail="You already have an active ride.",
            )

        offer = quantize_pula(proposed_fare)
        if offer < MIN_PASSENGER_OFFER:
            raise HTTPException(
                status_code=400,
                detail="Minimum passenger offer is P20.",
            )

        quote = PricingService.quote_trip(
            pickup_latitude,
            pickup_longitude,
            destination_latitude,
            destination_longitude,
        )

        ride = RideRequest(
            passenger_id=passenger.id,
            pickup_location=pickup_location,
            pickup_latitude=pickup_latitude,
            pickup_longitude=pickup_longitude,
            destination=destination,
            destination_latitude=destination_latitude,
            destination_longitude=destination_longitude,
            proposed_fare=float(offer),
            recommended_fare=quote.recommended_fare,
            passenger_current_offer=offer,
            passenger_offer_version=1,
            trip_distance_km=quote.estimated_trip_distance_km,
            status=RideStatus.PENDING,
        )

        db.add(ride)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            if RideService._is_duplicate_active_ride_error(exc):
                raise HTTPException(
                    status_code=400,
                    detail="You already have an active ride.",
                ) from exc
            raise

        db.refresh(ride)

        MarketplaceService.record_event(
            db,
            ride=ride,
            actor_type=NegotiationActorType.PASSENGER,
            actor_user_id=current_user.id,
            action=NegotiationAction.PASSENGER_OFFER_CREATED,
            amount=offer,
        )
        db.commit()
        db.refresh(ride)

        ride = DispatchService.broadcast_marketplace_request(
            db=db,
            ride=ride,
        )

        return ride

    @staticmethod
    def _is_duplicate_active_ride_error(exc: IntegrityError) -> bool:
        orig = getattr(exc, "orig", None)
        if orig is None:
            return UQ_RIDE_REQUESTS_ONE_ACTIVE_PER_PASSENGER in str(exc)

        sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
        if sqlstate is not None and str(sqlstate) != _PG_UNIQUE_VIOLATION:
            return False

        constraint_name = None
        diag = getattr(orig, "diag", None)
        if diag is not None:
            constraint_name = getattr(diag, "constraint_name", None)

        if constraint_name == UQ_RIDE_REQUESTS_ONE_ACTIVE_PER_PASSENGER:
            return True

        return UQ_RIDE_REQUESTS_ONE_ACTIVE_PER_PASSENGER in str(orig)

    # ==========================================================
    # AVAILABLE RIDES
    # ==========================================================

    @staticmethod
    def get_available_rides(
        db: Session,
    ):
        return (
            db.query(RideRequest)
            .filter(
                RideRequest.status == RideStatus.PENDING
            )
            .all()
        )

    # ==========================================================
    # PASSENGER RIDES
    # ==========================================================

    @staticmethod
    def get_passenger_rides(
        db: Session,
        current_user: User,
    ):
        passenger = (
            db.query(Passenger)
            .filter(
                Passenger.user_id == current_user.id
            )
            .first()
        )

        if passenger is None:
            raise HTTPException(
                status_code=404,
                detail="Passenger profile not found.",
            )

        return (
            db.query(RideRequest)
            .filter(
                RideRequest.passenger_id == passenger.id
            )
            .order_by(
                RideRequest.requested_at.desc()
            )
            .all()
        )

    # ==========================================================
    # DRIVER RIDES
    # ==========================================================

    @staticmethod
    def get_driver_rides(
        db: Session,
        current_user: User,
    ):
        if current_user.role != "driver":
            raise HTTPException(
                status_code=403,
                detail="Only drivers can view driver ride history.",
            )

        return (
            db.query(RideRequest)
            .filter(
                RideRequest.accepted_driver_id == current_user.id
            )
            .order_by(
                RideRequest.requested_at.desc()
            )
            .all()
        )

    # ==========================================================
    # ACCEPT RIDE
    # ==========================================================

    @staticmethod
    def accept_ride(
        db: Session,
        ride_id: int,
        current_user: User,
    ):
        # ------------------------------------------------------
        # Security: only drivers can accept rides
        # ------------------------------------------------------

        if current_user.role != "driver":
            raise HTTPException(
                status_code=403,
                detail="Only drivers can accept rides.",
            )

        if current_user.verification_status != "approved":
            raise HTTPException(
                status_code=403,
                detail="Driver account is not approved.",
            )

        return MarketplaceService.driver_respond(
            db=db,
            ride_id=ride_id,
            current_user=current_user,
            response_type="accept_passenger_offer",
            amount=None,
        )

    # ==========================================================
    # DRIVER ARRIVING
    # ==========================================================

    @staticmethod
    def arrive_at_pickup(
        db: Session,
        ride_id: int,
        current_user: User,
    ):
        if current_user.role != "driver":
            raise HTTPException(
                status_code=403,
                detail="Only drivers can update ride status.",
            )

        ride = (
            db.query(RideRequest)
            .filter(
                RideRequest.id == ride_id
            )
            .first()
        )

        if ride is None:
            raise HTTPException(
                status_code=404,
                detail="Ride not found.",
            )

        if ride.accepted_driver_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="You are not assigned to this ride.",
            )

        NextRideService.reject_if_next_ride(ride)

        # CAS: ACCEPTED → DRIVER_ARRIVING (assigned driver only)
        ride_result = db.execute(
            update(RideRequest)
            .where(
                RideRequest.id == ride.id,
                RideRequest.accepted_driver_id == current_user.id,
                RideRequest.status == RideStatus.ACCEPTED,
            )
            .values(status=RideStatus.DRIVER_ARRIVING)
            .execution_options(synchronize_session=False)
        )

        if ride_result.rowcount != 1:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail="Ride is not in the accepted state.",
            )

        db.commit()
        db.refresh(ride)

        NotificationService.notify_passenger(
            ride.passenger_id,
            "Your driver is on the way to the pickup location.",
        )

        return ride

    # ==========================================================
    # DRIVER ARRIVED
    # ==========================================================

    @staticmethod
    def driver_arrived(
        db: Session,
        ride_id: int,
        current_user: User,
    ):
        if current_user.role != "driver":
            raise HTTPException(
                status_code=403,
                detail="Only drivers can update ride status.",
            )

        ride = (
            db.query(RideRequest)
            .filter(
                RideRequest.id == ride_id
            )
            .first()
        )

        if ride is None:
            raise HTTPException(
                status_code=404,
                detail="Ride not found.",
            )

        if ride.accepted_driver_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="You are not assigned to this ride.",
            )

        NextRideService.reject_if_next_ride(ride)

        # CAS: DRIVER_ARRIVING → DRIVER_ARRIVED (assigned driver only)
        ride_result = db.execute(
            update(RideRequest)
            .where(
                RideRequest.id == ride.id,
                RideRequest.accepted_driver_id == current_user.id,
                RideRequest.status == RideStatus.DRIVER_ARRIVING,
            )
            .values(status=RideStatus.DRIVER_ARRIVED)
            .execution_options(synchronize_session=False)
        )

        if ride_result.rowcount != 1:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail="Ride is not in the driver-arriving state.",
            )

        db.commit()
        db.refresh(ride)

        NotificationService.notify_passenger(
            ride.passenger_id,
            "Your driver has arrived.",
        )

        return ride

    # ==========================================================
    # START RIDE
    # ==========================================================

    @staticmethod
    def start_ride(
        db: Session,
        ride_id: int,
        current_user: User,
    ):
        if current_user.role != "driver":
            raise HTTPException(
                status_code=403,
                detail="Only drivers can start rides.",
            )

        ride = (
            db.query(RideRequest)
            .filter(
                RideRequest.id == ride_id
            )
            .first()
        )

        if ride is None:
            raise HTTPException(
                status_code=404,
                detail="Ride not found.",
            )

        if ride.accepted_driver_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="You are not assigned to this ride.",
            )

        NextRideService.reject_if_next_ride(ride)

        # CAS: DRIVER_ARRIVING | DRIVER_ARRIVED → IN_PROGRESS
        # Both predecessors remain valid product states for start.
        ride_result = db.execute(
            update(RideRequest)
            .where(
                RideRequest.id == ride.id,
                RideRequest.accepted_driver_id == current_user.id,
                RideRequest.status.in_(
                    [
                        RideStatus.DRIVER_ARRIVING,
                        RideStatus.DRIVER_ARRIVED,
                    ]
                ),
            )
            .values(status=RideStatus.IN_PROGRESS)
            .execution_options(synchronize_session=False)
        )

        if ride_result.rowcount != 1:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail="Ride is not ready to start.",
            )

        db.commit()
        db.refresh(ride)

        NotificationService.notify_passenger(
            ride.passenger_id,
            "Your ride has started.",
        )

        return ride

    # ==========================================================
    # COMPLETE RIDE
    # ==========================================================

    @staticmethod
    def complete_ride(
        db: Session,
        ride_id: int,
        current_user: User,
    ):
        if current_user.role != "driver":
            raise HTTPException(
                status_code=403,
                detail="Only drivers can complete rides.",
            )

        ride = (
            db.query(RideRequest)
            .filter(
                RideRequest.id == ride_id
            )
            .first()
        )

        if ride is None:
            raise HTTPException(
                status_code=404,
                detail="Ride not found.",
            )

        if ride.accepted_driver_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="You are not assigned to this ride.",
            )

        NextRideService.reject_if_next_ride(ride)

        # CAS: IN_PROGRESS → COMPLETED (assigned driver only)
        ride_result = db.execute(
            update(RideRequest)
            .where(
                RideRequest.id == ride.id,
                RideRequest.accepted_driver_id == current_user.id,
                RideRequest.status == RideStatus.IN_PROGRESS,
            )
            .values(
                status=RideStatus.COMPLETED,
                completed_at=datetime.utcnow(),
            )
            .execution_options(synchronize_session=False)
        )

        if ride_result.rowcount != 1:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail="Ride is not currently in progress.",
            )

        db.flush()

        # Complete the confirmed shared-ride passenger together with the host ride.
        shared_passenger_id = None
        if ride.shared_ride_consent is True and ride.shared_ride_with_id is not None:
            shared_ride = SharedRideService._lock_ride(db, ride.shared_ride_with_id)
            if (
                shared_ride is not None
                and shared_ride.status == RideStatus.ACCEPTED
                and shared_ride.accepted_driver_id == current_user.id
                and shared_ride.shared_ride_with_id == ride.id
                and shared_ride.shared_ride_consent is True
            ):
                shared_ride.status = RideStatus.COMPLETED
                shared_ride.completed_at = datetime.utcnow()
                shared_passenger_id = shared_ride.passenger_id

        db.refresh(ride)
        WalletService.post_completion_commission(db, ride)

        promoted = NextRideService.promote_after_current_completion(
            db,
            current_user.id,
        )
        if promoted is None:
            current_user.availability_status = "available"
            WalletService.apply_offline_if_below_minimum(db, current_user.id)

        db.commit()
        db.refresh(ride)

        NotificationService.notify_passenger(
            ride.passenger_id,
            "Your ride has been completed.",
        )
        if shared_passenger_id is not None:
            NotificationService.notify_passenger(
                shared_passenger_id,
                "Your shared ride has been completed.",
            )

        return ride

    # ==========================================================
    # CANCEL RIDE (PILOT)
    # Passenger: pending marketplace through arrived, not after start.
    # Assigned driver: accepted through arrived, not after start.
    # No fees, no refunds, no commission.
    # ==========================================================

    _CANNOT_CANCEL = "Ride cannot be cancelled in its current state."

    @staticmethod
    def cancel_ride(
        db: Session,
        ride_id: int,
        current_user: User,
    ):
        ride = (
            db.query(RideRequest)
            .filter(
                RideRequest.id == ride_id
            )
            .first()
        )

        if ride is None:
            raise HTTPException(
                status_code=404,
                detail="Ride not found.",
            )

        passenger = (
            db.query(Passenger)
            .filter(
                Passenger.user_id == current_user.id
            )
            .first()
        )
        is_passenger_owner = (
            passenger is not None and ride.passenger_id == passenger.id
        )
        is_assigned_driver = (
            current_user.role == "driver"
            and ride.accepted_driver_id == current_user.id
        )

        if not is_passenger_owner and not is_assigned_driver:
            if passenger is None and current_user.role != "driver":
                raise HTTPException(
                    status_code=404,
                    detail="Passenger profile not found.",
                )
            if current_user.role == "driver":
                raise HTTPException(
                    status_code=400,
                    detail=RideService._CANNOT_CANCEL,
                )
            raise HTTPException(
                status_code=403,
                detail="You are not authorized to cancel this ride.",
            )

        locked = (
            db.query(RideRequest)
            .filter(RideRequest.id == ride_id)
            .with_for_update()
            .first()
        )
        if locked is None:
            raise HTTPException(
                status_code=404,
                detail="Ride not found.",
            )

        if is_passenger_owner:
            return RideService._passenger_cancel_locked(
                db,
                locked,
                current_user,
            )
        return RideService._driver_cancel_locked(
            db,
            locked,
            current_user,
        )

    @staticmethod
    def _passenger_cancel_locked(
        db: Session,
        ride: RideRequest,
        current_user: User,
    ):
        if ride.status == RideStatus.PENDING:
            return RideService._cancel_pending_marketplace(
                db,
                ride,
                current_user,
            )

        if ride.status == RideStatus.PENDING_DRIVER_ACCEPTANCE:
            return RideService._cancel_pending_driver_acceptance(
                db,
                ride,
            )

        if ride.status in RideStatus.DRIVER_CANCELLABLE:
            return RideService._cancel_assigned_pre_start(
                db,
                ride,
                current_user,
                cancelled_status=RideStatus.CANCELLED_BY_PASSENGER,
                actor_type=NegotiationActorType.PASSENGER,
            )

        raise HTTPException(
            status_code=400,
            detail=RideService._CANNOT_CANCEL,
        )

    @staticmethod
    def _driver_cancel_locked(
        db: Session,
        ride: RideRequest,
        current_user: User,
    ):
        if (
            ride.accepted_driver_id != current_user.id
            or ride.status not in RideStatus.DRIVER_CANCELLABLE
        ):
            raise HTTPException(
                status_code=400,
                detail=RideService._CANNOT_CANCEL,
            )
        return RideService._cancel_assigned_pre_start(
            db,
            ride,
            current_user,
            cancelled_status=RideStatus.CANCELLED_BY_DRIVER,
            actor_type=NegotiationActorType.DRIVER,
        )

    @staticmethod
    def _cancel_pending_marketplace(
        db: Session,
        ride: RideRequest,
        current_user: User,
    ):
        pending_result = db.execute(
            update(RideRequest)
            .where(
                RideRequest.id == ride.id,
                RideRequest.status == RideStatus.PENDING,
                RideRequest.accepted_driver_id.is_(None),
            )
            .values(status=RideStatus.CANCELLED_BY_PASSENGER)
            .execution_options(synchronize_session=False)
        )

        if pending_result.rowcount != 1:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail=RideService._CANNOT_CANCEL,
            )

        db.refresh(ride)
        driver_ids = MarketplaceService.close_open_responses_on_cancel(
            db,
            ride,
            current_user.id,
        )
        db.commit()
        db.refresh(ride)
        MarketplaceService.notify_request_cancelled(ride, driver_ids)
        return ride

    @staticmethod
    def _cancel_pending_driver_acceptance(
        db: Session,
        ride: RideRequest,
    ):
        assigned_driver_id = ride.accepted_driver_id
        now = datetime.utcnow()

        # Conditionally close the live pending offer (do not overwrite
        # accepted / rejected / expired).
        if assigned_driver_id is not None:
            db.execute(
                update(RideOffer)
                .where(
                    RideOffer.ride_id == ride.id,
                    RideOffer.driver_id == assigned_driver_id,
                    RideOffer.status == RideOfferStatus.PENDING,
                )
                .values(
                    status=RideOfferStatus.REJECTED,
                    responded_at=now,
                )
                .execution_options(synchronize_session=False)
            )

        ride_filters = [
            RideRequest.id == ride.id,
            RideRequest.status == RideStatus.PENDING_DRIVER_ACCEPTANCE,
        ]
        if assigned_driver_id is not None:
            ride_filters.append(
                RideRequest.accepted_driver_id == assigned_driver_id
            )
        else:
            ride_filters.append(RideRequest.accepted_driver_id.is_(None))

        ride_result = db.execute(
            update(RideRequest)
            .where(*ride_filters)
            .values(
                status=RideStatus.CANCELLED_BY_PASSENGER,
                accepted_driver_id=None,
            )
            .execution_options(synchronize_session=False)
        )

        if ride_result.rowcount != 1:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail=RideService._CANNOT_CANCEL,
            )

        if assigned_driver_id is not None:
            # reserved → available; offline (or any other status) unchanged
            db.execute(
                update(User)
                .where(
                    User.id == assigned_driver_id,
                    User.availability_status == "reserved",
                )
                .values(availability_status="available")
                .execution_options(synchronize_session=False)
            )

        db.commit()
        db.refresh(ride)
        return ride

    @staticmethod
    def _cancel_assigned_pre_start(
        db: Session,
        ride: RideRequest,
        current_user: User,
        cancelled_status: str,
        actor_type: str,
    ):
        assigned_driver_id = ride.accepted_driver_id
        if assigned_driver_id is None:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail=RideService._CANNOT_CANCEL,
            )

        ride_result = db.execute(
            update(RideRequest)
            .where(
                RideRequest.id == ride.id,
                RideRequest.accepted_driver_id == assigned_driver_id,
                RideRequest.status.in_(RideStatus.DRIVER_CANCELLABLE),
            )
            .values(status=cancelled_status)
            .execution_options(synchronize_session=False)
        )

        if ride_result.rowcount != 1:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail=RideService._CANNOT_CANCEL,
            )

        db.refresh(ride)
        cancelled_payment = PaymentService.cancel_open_for_ride(db, ride)
        driver_ids = MarketplaceService.close_open_responses_on_cancel(
            db,
            ride,
            current_user.id,
            actor_type=actor_type,
        )
        remaining_assignment = (
            db.query(RideRequest)
            .filter(
                RideRequest.accepted_driver_id == assigned_driver_id,
                RideRequest.id != ride.id,
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
        if remaining_assignment is None:
            db.execute(
                update(User)
                .where(
                    User.id == assigned_driver_id,
                    User.availability_status == "busy",
                )
                .values(availability_status="available")
                .execution_options(synchronize_session=False)
            )
        db.commit()
        db.refresh(ride)

        notify_ids = list(driver_ids)
        if assigned_driver_id not in notify_ids:
            notify_ids.append(assigned_driver_id)
        MarketplaceService.notify_request_cancelled(ride, notify_ids)
        if cancelled_status == RideStatus.CANCELLED_BY_DRIVER:
            NotificationService.notify_passenger(
                ride.passenger_id,
                "The driver cancelled this ride.",
            )
        else:
            NotificationService.notify_driver(
                assigned_driver_id,
                "The passenger cancelled this ride.",
            )
        if cancelled_payment is not None:
            NotificationService.notify_payment_updated(
                passenger_id=ride.passenger_id,
                driver_id=assigned_driver_id,
                ride_id=ride.id,
                payment_id=cancelled_payment.id,
                status=cancelled_payment.status,
            )
        return ride