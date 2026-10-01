from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.constants.driver_response import DriverResponseStatus, DriverResponseType
from app.constants.negotiation import (
    NegotiationAction,
    NegotiationActorType,
    PassengerOfferAction,
)
from app.constants.ride_status import RideStatus
from app.constants.verification import VerificationStatus
from app.models.driver_response import (
    UQ_DRIVER_RESPONSES_ONE_OPEN_PER_DRIVER_RIDE,
    DriverResponse,
)
from app.models.driver_wallet import DriverWallet
from app.models.negotiation_event import NegotiationEvent
from app.models.passenger import Passenger
from app.models.ride_request import (
    UQ_RIDE_REQUESTS_ONE_ACTIVE_PER_DRIVER,
    RideRequest,
)
from app.models.user import User
from app.schemas.ride_request import (
    DriverResponseOut,
    NegotiationEventOut,
)
from app.services.distance_provider import get_trip_distance_provider
from app.services.driver_identity_service import DriverIdentityService
from app.services.location_service import LocationService
from app.services.notification_service import NotificationService
from app.services.payment_service import PaymentService
from app.utils.money import (
    DRIVER_WALLET_BELOW_MINIMUM,
    MIN_DRIVER_WALLET,
    MIN_PASSENGER_OFFER,
    driver_wallet_meets_minimum,
    estimate_pickup_eta_seconds,
    generate_counter_offer_amounts,
    money_float,
    quantize_pula,
)

_PG_UNIQUE_VIOLATION = "23505"
_UNAVAILABLE = "Ride is no longer available."


class MarketplaceService:
    """Passenger offers, driver responses, selection CAS, and history."""

    # ==========================================================
    # Eligibility
    # ==========================================================

    @staticmethod
    def eligible_drivers(db: Session) -> list[User]:
        return (
            db.query(User)
            .join(DriverWallet, DriverWallet.driver_id == User.id)
            .filter(
                User.role == "driver",
                User.availability_status == "available",
                User.verification_status == VerificationStatus.APPROVED,
                User.current_latitude.isnot(None),
                User.current_longitude.isnot(None),
                DriverWallet.available_balance > MIN_DRIVER_WALLET,
            )
            .all()
        )

    @staticmethod
    def require_passenger_owner(
        db: Session,
        ride: RideRequest,
        current_user: User,
    ) -> Passenger:
        passenger = (
            db.query(Passenger)
            .filter(Passenger.user_id == current_user.id)
            .first()
        )
        if passenger is None:
            raise HTTPException(
                status_code=404,
                detail="Passenger profile not found.",
            )
        if ride.passenger_id != passenger.id:
            raise HTTPException(
                status_code=403,
                detail="You are not authorized to access this ride.",
            )
        return passenger

    @staticmethod
    def _require_open_marketplace_ride(
        db: Session,
        ride_id: int,
    ) -> RideRequest:
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
        return ride

    @staticmethod
    def _pickup_decision_support(
        ride: RideRequest,
        driver: User,
    ) -> tuple[Decimal | None, int | None]:
        if (
            ride.pickup_latitude is None
            or ride.pickup_longitude is None
            or driver.current_latitude is None
            or driver.current_longitude is None
        ):
            return None, None
        distance = LocationService.calculate_distance(
            ride.pickup_latitude,
            ride.pickup_longitude,
            driver.current_latitude,
            driver.current_longitude,
        )
        distance_km = Decimal(str(round(distance, 3)))
        return distance_km, estimate_pickup_eta_seconds(distance)

    @staticmethod
    def trip_distance_km(
        pickup_latitude: float | None,
        pickup_longitude: float | None,
        destination_latitude: float | None,
        destination_longitude: float | None,
    ) -> Decimal | None:
        estimate = get_trip_distance_provider().estimate(
            pickup_latitude,
            pickup_longitude,
            destination_latitude,
            destination_longitude,
        )
        return estimate.km if estimate is not None else None

    @staticmethod
    def record_event(
        db: Session,
        *,
        ride: RideRequest,
        actor_type: str,
        action: str,
        actor_user_id: int | None = None,
        driver_id: int | None = None,
        amount: Decimal | None = None,
        resulting_response_status: str | None = None,
    ) -> None:
        db.add(
            NegotiationEvent(
                ride_id=ride.id,
                actor_type=actor_type,
                actor_user_id=actor_user_id,
                driver_id=driver_id,
                action=action,
                amount=amount,
                resulting_ride_status=ride.status,
                resulting_response_status=resulting_response_status,
            )
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

    # ==========================================================
    # Broadcast
    # ==========================================================

    @staticmethod
    def broadcast_marketplace_request(
        db: Session,
        ride: RideRequest,
    ) -> RideRequest:
        drivers = MarketplaceService.eligible_drivers(db)
        event_id = uuid4().hex
        offer = money_float(ride.passenger_current_offer) or float(ride.proposed_fare)
        for driver in drivers:
            pickup_distance_km, pickup_eta_seconds = (
                MarketplaceService._pickup_decision_support(ride, driver)
            )
            NotificationService.notify_marketplace_request_created(
                driver_id=driver.id,
                ride_id=ride.id,
                event_id=event_id,
                passenger_offer_version=ride.passenger_offer_version,
                passenger_current_offer=offer,
                pickup=ride.pickup_location,
                destination=ride.destination,
                trip_distance_km=money_float(ride.trip_distance_km),
                pickup_distance_km=money_float(pickup_distance_km),
                pickup_eta_seconds=pickup_eta_seconds,
            )
        return ride

    @staticmethod
    def _broadcast_passenger_offer_updated(
        db: Session,
        ride: RideRequest,
        action: str,
    ) -> None:
        event_id = uuid4().hex
        offer = money_float(ride.passenger_current_offer)
        notified: set[int] = set()
        for driver in MarketplaceService.eligible_drivers(db):
            notified.add(driver.id)
            NotificationService.notify_passenger_offer_updated(
                driver_id=driver.id,
                ride_id=ride.id,
                event_id=event_id,
                passenger_offer_version=ride.passenger_offer_version,
                passenger_current_offer=offer,
                action=action,
            )
        open_responders = (
            db.query(DriverResponse.driver_id)
            .filter(
                DriverResponse.ride_id == ride.id,
                DriverResponse.status == DriverResponseStatus.OPEN,
            )
            .all()
        )
        for (driver_id,) in open_responders:
            if driver_id in notified:
                continue
            NotificationService.notify_passenger_offer_updated(
                driver_id=driver_id,
                ride_id=ride.id,
                event_id=event_id,
                passenger_offer_version=ride.passenger_offer_version,
                passenger_current_offer=offer,
                action=action,
            )

    # ==========================================================
    # Passenger offer
    # ==========================================================

    @staticmethod
    def update_passenger_offer(
        db: Session,
        ride_id: int,
        current_user: User,
        action: str,
        amount: Decimal | None,
        passenger_offer_version: int | None,
    ) -> RideRequest:
        ride = (
            db.query(RideRequest)
            .filter(RideRequest.id == ride_id)
            .first()
        )
        if ride is None:
            raise HTTPException(status_code=404, detail="Ride not found.")
        MarketplaceService.require_passenger_owner(db, ride, current_user)

        ride = MarketplaceService._require_open_marketplace_ride(db, ride_id)
        current_offer = quantize_pula(ride.passenger_current_offer)
        seen_version = (
            passenger_offer_version
            if passenger_offer_version is not None
            else ride.passenger_offer_version
        )

        if action == PassengerOfferAction.MAINTAIN:
            new_offer = current_offer
            event_action = NegotiationAction.PASSENGER_OFFER_MAINTAINED
        elif action == PassengerOfferAction.INCREASE:
            if amount is None:
                raise HTTPException(
                    status_code=400,
                    detail="An increased offer amount is required.",
                )
            new_offer = quantize_pula(amount)
            if new_offer < MIN_PASSENGER_OFFER:
                raise HTTPException(
                    status_code=400,
                    detail="Minimum passenger offer is P20.",
                )
            if new_offer <= current_offer:
                raise HTTPException(
                    status_code=400,
                    detail="Increased offer must be greater than the current offer.",
                )
            event_action = NegotiationAction.PASSENGER_OFFER_INCREASED
        else:
            raise HTTPException(status_code=400, detail="Invalid offer action.")

        result = db.execute(
            update(RideRequest)
            .where(
                RideRequest.id == ride.id,
                RideRequest.status == RideStatus.PENDING,
                RideRequest.accepted_driver_id.is_(None),
                RideRequest.agreed_fare.is_(None),
                RideRequest.passenger_offer_version == seen_version,
            )
            .values(
                passenger_current_offer=new_offer,
                proposed_fare=float(new_offer),
                passenger_offer_version=seen_version + 1,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(status_code=400, detail=_UNAVAILABLE)

        db.flush()
        db.refresh(ride)
        MarketplaceService.record_event(
            db,
            ride=ride,
            actor_type=NegotiationActorType.PASSENGER,
            actor_user_id=current_user.id,
            action=event_action,
            amount=new_offer,
        )
        db.commit()
        db.refresh(ride)
        MarketplaceService._broadcast_passenger_offer_updated(db, ride, action)
        return ride

    # ==========================================================
    # Driver counter options / respond
    # ==========================================================

    @staticmethod
    def get_counter_options(
        db: Session,
        ride_id: int,
        current_user: User,
    ) -> dict:
        if current_user.role != "driver":
            raise HTTPException(
                status_code=403,
                detail="Only drivers can view counter-offer options.",
            )
        ride = db.query(RideRequest).filter(RideRequest.id == ride_id).first()
        if ride is None:
            raise HTTPException(status_code=404, detail="Ride not found.")
        if ride.status != RideStatus.PENDING:
            raise HTTPException(status_code=400, detail=_UNAVAILABLE)
        current = quantize_pula(ride.passenger_current_offer)
        amounts = [
            float(amount)
            for amount in generate_counter_offer_amounts(current)
        ]
        return {
            "ride_id": ride.id,
            "passenger_current_offer": float(current),
            "passenger_offer_version": ride.passenger_offer_version,
            "amounts": amounts,
        }

    @staticmethod
    def _require_eligible_responder(db: Session, current_user: User) -> None:
        if current_user.role != "driver":
            raise HTTPException(
                status_code=403,
                detail="Only drivers can respond to rides.",
            )
        if current_user.verification_status != VerificationStatus.APPROVED:
            raise HTTPException(
                status_code=403,
                detail="Driver account is not approved.",
            )
        if current_user.availability_status != "available":
            raise HTTPException(
                status_code=400,
                detail="Driver must be online to respond.",
            )
        if (
            current_user.current_latitude is None
            or current_user.current_longitude is None
        ):
            raise HTTPException(
                status_code=400,
                detail="Driver location is required to respond.",
            )
        wallet = (
            db.query(DriverWallet)
            .filter(DriverWallet.driver_id == current_user.id)
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
    def driver_respond(
        db: Session,
        ride_id: int,
        current_user: User,
        response_type: str,
        amount: Decimal | None,
    ) -> RideRequest:
        MarketplaceService._require_eligible_responder(db, current_user)
        ride = MarketplaceService._require_open_marketplace_ride(db, ride_id)

        passenger_offer = quantize_pula(ride.passenger_current_offer)
        version = ride.passenger_offer_version
        if response_type == DriverResponseType.ACCEPT_PASSENGER_OFFER:
            response_amount = passenger_offer
            action = NegotiationAction.DRIVER_ACCEPTED_PASSENGER_OFFER
        elif response_type == DriverResponseType.COUNTER_OFFER:
            if amount is None:
                raise HTTPException(
                    status_code=400,
                    detail="A generated counter-offer amount is required.",
                )
            response_amount = quantize_pula(amount)
            allowed = generate_counter_offer_amounts(passenger_offer)
            if response_amount not in allowed:
                raise HTTPException(
                    status_code=400,
                    detail="Driver counter-offer must be one of the generated amounts.",
                )
            action = NegotiationAction.DRIVER_SUBMITTED_OFFER
        else:
            raise HTTPException(status_code=400, detail="Invalid response type.")

        pickup_distance_km, pickup_eta_seconds = (
            MarketplaceService._pickup_decision_support(ride, current_user)
        )
        now = datetime.utcnow()
        existing = (
            db.query(DriverResponse)
            .filter(
                DriverResponse.ride_id == ride.id,
                DriverResponse.driver_id == current_user.id,
                DriverResponse.status == DriverResponseStatus.OPEN,
            )
            .with_for_update()
            .first()
        )

        replaced = existing is not None
        if existing is not None:
            existing.response_type = response_type
            existing.amount = response_amount
            existing.passenger_offer_version_at_submit = version
            existing.passenger_offer_amount_at_submit = passenger_offer
            existing.pickup_distance_km = pickup_distance_km
            existing.pickup_eta_seconds = pickup_eta_seconds
            existing.created_at = now
            response = existing
        else:
            response = DriverResponse(
                ride_id=ride.id,
                driver_id=current_user.id,
                response_type=response_type,
                amount=response_amount,
                passenger_offer_version_at_submit=version,
                passenger_offer_amount_at_submit=passenger_offer,
                status=DriverResponseStatus.OPEN,
                pickup_distance_km=pickup_distance_km,
                pickup_eta_seconds=pickup_eta_seconds,
                created_at=now,
            )
            db.add(response)

        if replaced:
            MarketplaceService.record_event(
                db,
                ride=ride,
                actor_type=NegotiationActorType.DRIVER,
                actor_user_id=current_user.id,
                driver_id=current_user.id,
                action=NegotiationAction.DRIVER_RESPONSE_REPLACED,
                amount=response_amount,
                resulting_response_status=DriverResponseStatus.OPEN,
            )

        MarketplaceService.record_event(
            db,
            ride=ride,
            actor_type=NegotiationActorType.DRIVER,
            actor_user_id=current_user.id,
            driver_id=current_user.id,
            action=action,
            amount=response_amount,
            resulting_response_status=DriverResponseStatus.OPEN,
        )

        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            if MarketplaceService._is_unique_violation(
                exc,
                UQ_DRIVER_RESPONSES_ONE_OPEN_PER_DRIVER_RIDE,
            ):
                raise HTTPException(
                    status_code=400,
                    detail="You already have an open response on this ride.",
                ) from exc
            raise

        db.refresh(ride)
        db.refresh(response)

        NotificationService.notify_driver_response_received(
            passenger_id=ride.passenger_id,
            ride_id=ride.id,
            event_id=uuid4().hex,
            passenger_offer_version=ride.passenger_offer_version,
            response_id=response.id,
            driver_id=current_user.id,
            response_type=response.response_type,
            amount=money_float(response.amount),
            pickup_distance_km=money_float(response.pickup_distance_km),
            pickup_eta_seconds=response.pickup_eta_seconds,
            driver_identity=DriverIdentityService.public_identity(
                db,
                current_user.id,
            ),
        )
        return ride

    # ==========================================================
    # List
    # ==========================================================

    @staticmethod
    def _can_view_ride(
        db: Session,
        ride: RideRequest,
        current_user: User,
    ) -> str | None:
        passenger = (
            db.query(Passenger)
            .filter(Passenger.user_id == current_user.id)
            .first()
        )
        if passenger is not None and ride.passenger_id == passenger.id:
            return "passenger"
        if ride.accepted_driver_id == current_user.id:
            return "assigned_driver"
        has_response = (
            db.query(DriverResponse.id)
            .filter(
                DriverResponse.ride_id == ride.id,
                DriverResponse.driver_id == current_user.id,
            )
            .first()
        )
        if has_response is not None:
            return "responding_driver"
        return None

    @staticmethod
    def require_ride_viewer(
        db: Session,
        ride: RideRequest,
        current_user: User,
    ) -> str:
        role = MarketplaceService._can_view_ride(db, ride, current_user)
        if role is None:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to view this trip.",
            )
        return role

    @staticmethod
    def serialize_driver_response(
        db: Session,
        response: DriverResponse,
        include_driver: bool,
    ) -> DriverResponseOut:
        payload = DriverResponseOut(
            id=response.id,
            ride_id=response.ride_id,
            driver_id=response.driver_id,
            response_type=response.response_type,
            amount=response.amount,
            status=response.status,
            passenger_offer_version_at_submit=response.passenger_offer_version_at_submit,
            passenger_offer_amount_at_submit=response.passenger_offer_amount_at_submit,
            pickup_distance_km=response.pickup_distance_km,
            pickup_eta_seconds=response.pickup_eta_seconds,
            created_at=response.created_at,
            expires_at=response.expires_at,
            responded_at=response.responded_at,
            driver=None,
        )
        if not include_driver:
            return payload
        return payload.model_copy(
            update={
                "driver": DriverIdentityService.public_identity(
                    db,
                    response.driver_id,
                )
            }
        )

    @staticmethod
    def list_responses(
        db: Session,
        ride_id: int,
        current_user: User,
    ) -> list[DriverResponseOut]:
        ride = db.query(RideRequest).filter(RideRequest.id == ride_id).first()
        if ride is None:
            raise HTTPException(status_code=404, detail="Ride not found.")
        viewer = MarketplaceService.require_ride_viewer(db, ride, current_user)
        query = db.query(DriverResponse).filter(DriverResponse.ride_id == ride.id)
        include_driver = viewer == "passenger"
        if viewer != "passenger":
            query = query.filter(DriverResponse.driver_id == current_user.id)
        rows = query.order_by(DriverResponse.created_at.asc()).all()
        return [
            MarketplaceService.serialize_driver_response(db, row, include_driver)
            for row in rows
        ]

    @staticmethod
    def list_negotiation(
        db: Session,
        ride_id: int,
        current_user: User,
    ) -> list[NegotiationEventOut]:
        ride = db.query(RideRequest).filter(RideRequest.id == ride_id).first()
        if ride is None:
            raise HTTPException(status_code=404, detail="Ride not found.")
        viewer = MarketplaceService.require_ride_viewer(db, ride, current_user)
        query = db.query(NegotiationEvent).filter(NegotiationEvent.ride_id == ride.id)
        if viewer != "passenger":
            query = query.filter(
                (NegotiationEvent.driver_id.is_(None))
                | (NegotiationEvent.driver_id == current_user.id)
            )
        rows = query.order_by(NegotiationEvent.created_at.asc(), NegotiationEvent.id.asc()).all()
        return [NegotiationEventOut.model_validate(row) for row in rows]

    # ==========================================================
    # Selection
    # ==========================================================

    @staticmethod
    def select_driver(
        db: Session,
        ride_id: int,
        current_user: User,
        response_id: int,
    ) -> RideRequest:
        ride = (
            db.query(RideRequest)
            .filter(RideRequest.id == ride_id)
            .first()
        )
        if ride is None:
            raise HTTPException(status_code=404, detail="Ride not found.")
        MarketplaceService.require_passenger_owner(db, ride, current_user)

        ride = MarketplaceService._require_open_marketplace_ride(db, ride_id)
        response = (
            db.query(DriverResponse)
            .filter(
                DriverResponse.id == response_id,
                DriverResponse.ride_id == ride.id,
            )
            .with_for_update()
            .first()
        )
        if response is None or response.status != DriverResponseStatus.OPEN:
            raise HTTPException(status_code=400, detail=_UNAVAILABLE)

        if response.response_type == DriverResponseType.COUNTER_OFFER:
            locked_fare = quantize_pula(response.amount)
            fare_action = NegotiationAction.PASSENGER_ACCEPTED_DRIVER_OFFER
        else:
            locked_fare = quantize_pula(ride.passenger_current_offer)
            fare_action = NegotiationAction.PASSENGER_SELECTED_DRIVER

        now = datetime.utcnow()
        try:
            driver_result = db.execute(
                update(User)
                .where(
                    User.id == response.driver_id,
                    User.availability_status == "available",
                    User.verification_status == VerificationStatus.APPROVED,
                )
                .values(availability_status="busy")
                .execution_options(synchronize_session=False)
            )
            if driver_result.rowcount != 1:
                db.rollback()
                raise HTTPException(
                    status_code=400,
                    detail="Driver is no longer available.",
                )

            ride_result = db.execute(
                update(RideRequest)
                .where(
                    RideRequest.id == ride.id,
                    RideRequest.status == RideStatus.PENDING,
                    RideRequest.accepted_driver_id.is_(None),
                    RideRequest.agreed_fare.is_(None),
                )
                .values(
                    accepted_driver_id=response.driver_id,
                    agreed_fare=locked_fare,
                    status=RideStatus.ACCEPTED,
                    selected_at=now,
                )
                .execution_options(synchronize_session=False)
            )
            if ride_result.rowcount != 1:
                db.rollback()
                raise HTTPException(status_code=400, detail=_UNAVAILABLE)

            winner_result = db.execute(
                update(DriverResponse)
                .where(
                    DriverResponse.id == response.id,
                    DriverResponse.ride_id == ride.id,
                    DriverResponse.driver_id == response.driver_id,
                    DriverResponse.status == DriverResponseStatus.OPEN,
                )
                .values(
                    status=DriverResponseStatus.SELECTED,
                    responded_at=now,
                )
                .execution_options(synchronize_session=False)
            )
            if winner_result.rowcount != 1:
                db.rollback()
                raise HTTPException(status_code=400, detail=_UNAVAILABLE)

            db.execute(
                update(DriverResponse)
                .where(
                    DriverResponse.ride_id == ride.id,
                    DriverResponse.status == DriverResponseStatus.OPEN,
                    DriverResponse.id != response.id,
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
                actor_type=NegotiationActorType.PASSENGER,
                actor_user_id=current_user.id,
                driver_id=response.driver_id,
                action=fare_action,
                amount=locked_fare,
                resulting_response_status=DriverResponseStatus.SELECTED,
            )
            MarketplaceService.record_event(
                db,
                ride=ride,
                actor_type=NegotiationActorType.SYSTEM,
                driver_id=response.driver_id,
                action=NegotiationAction.FARE_AGREED,
                amount=locked_fare,
                resulting_response_status=DriverResponseStatus.SELECTED,
            )
            MarketplaceService.record_event(
                db,
                ride=ride,
                actor_type=NegotiationActorType.SYSTEM,
                action=NegotiationAction.LOSER_CLOSED,
                resulting_response_status=DriverResponseStatus.CLOSED_LOSER,
            )
            db.commit()
        except HTTPException:
            db.rollback()
            raise
        except IntegrityError as exc:
            db.rollback()
            if MarketplaceService._is_unique_violation(
                exc,
                UQ_RIDE_REQUESTS_ONE_ACTIVE_PER_DRIVER,
            ):
                raise HTTPException(
                    status_code=400,
                    detail="Driver already has an active ride.",
                ) from exc
            if PaymentService.is_constraint_violation(exc):
                raise HTTPException(
                    status_code=400,
                    detail="Payment could not be recorded.",
                ) from exc
            raise

        db.refresh(ride)
        MarketplaceService._notify_selection(db, ride, response.id)
        return ride

    @staticmethod
    def _notify_selection(
        db: Session,
        ride: RideRequest,
        winner_response_id: int,
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
            response_id=winner_response_id,
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
        for row in responses:
            NotificationService.notify_marketplace_request_closed(
                driver_id=row.driver_id,
                ride_id=ride.id,
                event_id=closed_event_id,
                reason="selected",
                won=row.id == winner_response_id,
                agreed_fare=agreed,
                selected_driver_id=ride.accepted_driver_id,
            )

    # ==========================================================
    # Ignore / withdraw / expire / cancel
    # ==========================================================

    @staticmethod
    def ignore_response(
        db: Session,
        ride_id: int,
        response_id: int,
        current_user: User,
    ) -> RideRequest:
        ride = db.query(RideRequest).filter(RideRequest.id == ride_id).first()
        if ride is None:
            raise HTTPException(status_code=404, detail="Ride not found.")
        MarketplaceService.require_passenger_owner(db, ride, current_user)
        ride = MarketplaceService._require_open_marketplace_ride(db, ride_id)
        now = datetime.utcnow()
        result = db.execute(
            update(DriverResponse)
            .where(
                DriverResponse.id == response_id,
                DriverResponse.ride_id == ride.id,
                DriverResponse.status == DriverResponseStatus.OPEN,
            )
            .values(
                status=DriverResponseStatus.WITHDRAWN,
                responded_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(status_code=400, detail=_UNAVAILABLE)
        response = db.get(DriverResponse, response_id)
        MarketplaceService.record_event(
            db,
            ride=ride,
            actor_type=NegotiationActorType.PASSENGER,
            actor_user_id=current_user.id,
            driver_id=response.driver_id if response else None,
            action=NegotiationAction.DRIVER_IGNORED,
            resulting_response_status=DriverResponseStatus.WITHDRAWN,
        )
        db.commit()
        db.refresh(ride)
        if response is not None:
            NotificationService.notify_driver_response_withdrawn(
                passenger_id=ride.passenger_id,
                driver_id=response.driver_id,
                ride_id=ride.id,
                event_id=uuid4().hex,
                response_id=response.id,
                passenger_offer_version=ride.passenger_offer_version,
            )
        return ride

    @staticmethod
    def withdraw_response(
        db: Session,
        ride_id: int,
        current_user: User,
    ) -> RideRequest | None:
        if current_user.role != "driver":
            raise HTTPException(
                status_code=403,
                detail="Only drivers can withdraw a response.",
            )
        ride = db.query(RideRequest).filter(RideRequest.id == ride_id).first()
        if ride is None:
            return None
        now = datetime.utcnow()
        result = db.execute(
            update(DriverResponse)
            .where(
                DriverResponse.ride_id == ride_id,
                DriverResponse.driver_id == current_user.id,
                DriverResponse.status == DriverResponseStatus.OPEN,
            )
            .values(
                status=DriverResponseStatus.WITHDRAWN,
                responded_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            db.rollback()
            return None
        MarketplaceService.record_event(
            db,
            ride=ride,
            actor_type=NegotiationActorType.DRIVER,
            actor_user_id=current_user.id,
            driver_id=current_user.id,
            action=NegotiationAction.DRIVER_RESPONSE_WITHDRAWN,
            resulting_response_status=DriverResponseStatus.WITHDRAWN,
        )
        db.commit()
        db.refresh(ride)
        NotificationService.notify_driver_response_withdrawn(
            passenger_id=ride.passenger_id,
            driver_id=current_user.id,
            ride_id=ride.id,
            event_id=uuid4().hex,
            response_id=None,
            passenger_offer_version=ride.passenger_offer_version,
        )
        return ride

    @staticmethod
    def expire_open_response(
        db: Session,
        response_id: int,
    ) -> bool:
        now = datetime.utcnow()
        response = (
            db.query(DriverResponse)
            .filter(DriverResponse.id == response_id)
            .first()
        )
        if response is None:
            return False
        result = db.execute(
            update(DriverResponse)
            .where(
                DriverResponse.id == response_id,
                DriverResponse.status == DriverResponseStatus.OPEN,
            )
            .values(
                status=DriverResponseStatus.EXPIRED,
                responded_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            db.rollback()
            return False
        ride = db.get(RideRequest, response.ride_id)
        if ride is not None:
            MarketplaceService.record_event(
                db,
                ride=ride,
                actor_type=NegotiationActorType.SYSTEM,
                driver_id=response.driver_id,
                action=NegotiationAction.DRIVER_RESPONSE_EXPIRED,
                resulting_response_status=DriverResponseStatus.EXPIRED,
            )
        db.commit()
        if ride is not None:
            NotificationService.notify_driver_response_expired(
                passenger_id=ride.passenger_id,
                driver_id=response.driver_id,
                ride_id=ride.id,
                event_id=uuid4().hex,
                response_id=response_id,
                passenger_offer_version=ride.passenger_offer_version,
            )
        return True

    @staticmethod
    def close_open_responses_on_cancel(
        db: Session,
        ride: RideRequest,
        actor_user_id: int | None,
        actor_type: str = NegotiationActorType.PASSENGER,
    ) -> list[int]:
        now = datetime.utcnow()
        open_rows = (
            db.query(DriverResponse)
            .filter(
                DriverResponse.ride_id == ride.id,
                DriverResponse.status == DriverResponseStatus.OPEN,
            )
            .all()
        )
        driver_ids = [row.driver_id for row in open_rows]
        if open_rows:
            db.execute(
                update(DriverResponse)
                .where(
                    DriverResponse.ride_id == ride.id,
                    DriverResponse.status == DriverResponseStatus.OPEN,
                )
                .values(
                    status=DriverResponseStatus.WITHDRAWN,
                    responded_at=now,
                )
                .execution_options(synchronize_session=False)
            )
        MarketplaceService.record_event(
            db,
            ride=ride,
            actor_type=actor_type,
            actor_user_id=actor_user_id,
            driver_id=(
                ride.accepted_driver_id
                if actor_type == NegotiationActorType.DRIVER
                else None
            ),
            action=NegotiationAction.REQUEST_CANCELLED,
            resulting_response_status=DriverResponseStatus.WITHDRAWN,
        )
        return driver_ids

    @staticmethod
    def notify_request_cancelled(ride: RideRequest, driver_ids: list[int]) -> None:
        event_id = uuid4().hex
        for driver_id in driver_ids:
            NotificationService.notify_marketplace_request_closed(
                driver_id=driver_id,
                ride_id=ride.id,
                event_id=event_id,
                reason="cancelled",
                won=False,
                agreed_fare=None,
                selected_driver_id=None,
            )

    @staticmethod
    def withdraw_driver_open_responses(
        db: Session,
        driver_id: int,
    ) -> None:
        now = datetime.utcnow()
        db.execute(
            update(DriverResponse)
            .where(
                DriverResponse.driver_id == driver_id,
                DriverResponse.status == DriverResponseStatus.OPEN,
            )
            .values(
                status=DriverResponseStatus.WITHDRAWN,
                responded_at=now,
            )
            .execution_options(synchronize_session=False)
        )
