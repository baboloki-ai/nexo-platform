from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.constants.ride_status import RideStatus
from app.models.passenger import Passenger
from app.models.ride_request import RideRequest
from app.models.user import User
from app.services.location_service import LocationService

_RIDE_NOT_FOUND = "Ride not found."
_RIDE_NOT_IN_PROGRESS = "Ride is not in progress."
_NOT_ASSIGNED_DRIVER = "You are not assigned to this ride."
_CANDIDATE_NOT_FOUND = "Candidate ride not found."
_CANDIDATE_NOT_ELIGIBLE = "Candidate is not eligible for a shared ride."
_PASSENGER_PROFILE_NOT_FOUND = "Passenger profile not found."
_NOT_RIDE_PASSENGER = "You are not authorized to access this ride."
_CONSENT_UNAVAILABLE = "Shared ride consent is not available."
_CANDIDATE_UNAVAILABLE = "Shared ride candidate is no longer available."


class SharedRideService:
    """
    Shared Ride pilot.

    A driver with an IN_PROGRESS ride can propose an ordinary
    pending passenger whose destination is sufficiently close
    and whose pickup is reasonably close to the current ride's pickup.
    Next Ride requests are explicitly excluded.
    """

    DESTINATION_MATCH_KM = 1.0
    PICKUP_MATCH_KM = 5.0

    @staticmethod
    def find_candidates(
        db: Session,
        current_ride: RideRequest,
        driver: User,
    ) -> list[RideRequest]:

        if current_ride.status != RideStatus.IN_PROGRESS:
            return []

        if current_ride.accepted_driver_id != driver.id:
            return []

        if (
            current_ride.destination_latitude is None
            or current_ride.destination_longitude is None
            or current_ride.pickup_latitude is None
            or current_ride.pickup_longitude is None
        ):
            return []

        candidates = (
            db.query(RideRequest)
            .filter(
                RideRequest.status == RideStatus.PENDING,
                RideRequest.accepted_driver_id.is_(None),
                RideRequest.is_next_ride.is_(False),
                RideRequest.shared_ride_with_id.is_(None),
                RideRequest.id != current_ride.id,
                RideRequest.destination_latitude.is_not(None),
                RideRequest.destination_longitude.is_not(None),
                RideRequest.pickup_latitude.is_not(None),
                RideRequest.pickup_longitude.is_not(None),
            )
            .order_by(RideRequest.requested_at.asc())
            .all()
        )

        matches: list[RideRequest] = []

        for candidate in candidates:
            destination_distance = LocationService.calculate_distance(
                current_ride.destination_latitude,
                current_ride.destination_longitude,
                candidate.destination_latitude,
                candidate.destination_longitude,
            )

            if destination_distance > SharedRideService.DESTINATION_MATCH_KM:
                continue

            pickup_distance = LocationService.calculate_distance(
                current_ride.pickup_latitude,
                current_ride.pickup_longitude,
                candidate.pickup_latitude,
                candidate.pickup_longitude,
            )

            if pickup_distance > SharedRideService.PICKUP_MATCH_KM:
                continue

            matches.append(candidate)

        return matches

    @staticmethod
    def propose(
        db: Session,
        ride_id: int,
        candidate_id: int,
        current_user: User,
    ) -> RideRequest:
        try:
            current_ride = SharedRideService._lock_ride(db, ride_id)
            if current_ride is None:
                raise HTTPException(status_code=404, detail=_RIDE_NOT_FOUND)
            if current_ride.status != RideStatus.IN_PROGRESS:
                raise HTTPException(status_code=400, detail=_RIDE_NOT_IN_PROGRESS)
            if current_ride.accepted_driver_id != current_user.id:
                raise HTTPException(status_code=403, detail=_NOT_ASSIGNED_DRIVER)

            candidate = SharedRideService._lock_ride(db, candidate_id)
            if candidate is None:
                raise HTTPException(status_code=404, detail=_CANDIDATE_NOT_FOUND)
            if not SharedRideService._candidate_is_open(candidate):
                raise HTTPException(status_code=400, detail=_CANDIDATE_NOT_ELIGIBLE)

            eligible_ids = {
                item.id
                for item in SharedRideService.find_candidates(
                    db,
                    current_ride,
                    current_user,
                )
            }
            if candidate.id not in eligible_ids:
                raise HTTPException(status_code=400, detail=_CANDIDATE_NOT_ELIGIBLE)

            current_ride.shared_ride_with_id = candidate.id
            current_ride.shared_ride_consent = False
            db.commit()
        except HTTPException:
            db.rollback()
            raise

        db.refresh(current_ride)
        return current_ride

    @staticmethod
    def record_consent(
        db: Session,
        ride_id: int,
        current_user: User,
        consent: bool,
    ) -> RideRequest:
        try:
            current_ride = SharedRideService._lock_ride(db, ride_id)
            if current_ride is None:
                raise HTTPException(status_code=404, detail=_RIDE_NOT_FOUND)

            SharedRideService._require_passenger_owner(
                db,
                current_ride,
                current_user,
            )
            if current_ride.status != RideStatus.IN_PROGRESS:
                raise HTTPException(status_code=400, detail=_RIDE_NOT_IN_PROGRESS)
            if current_ride.shared_ride_with_id is None:
                raise HTTPException(status_code=400, detail=_CONSENT_UNAVAILABLE)

            if not consent:
                current_ride.shared_ride_consent = False
                current_ride.shared_ride_with_id = None
            else:
                SharedRideService._accept_shared_candidate(db, current_ride)

            db.commit()
        except HTTPException:
            db.rollback()
            raise
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail=_CANDIDATE_UNAVAILABLE,
            ) from exc

        db.refresh(current_ride)
        return current_ride

    @staticmethod
    def _accept_shared_candidate(
        db: Session,
        current_ride: RideRequest,
    ) -> None:
        driver_id = current_ride.accepted_driver_id

        if driver_id is None:
            raise HTTPException(
                status_code=400,
                detail=_CANDIDATE_UNAVAILABLE,
            )

        candidate = SharedRideService._lock_ride(
            db,
            current_ride.shared_ride_with_id,
        )

        if candidate is None:
            raise HTTPException(
                status_code=400,
                detail=_CANDIDATE_UNAVAILABLE,
            )

        if (
            candidate.status != RideStatus.PENDING
            or candidate.accepted_driver_id is not None
            or candidate.is_next_ride
            or (
                candidate.shared_ride_with_id is not None
                and candidate.shared_ride_with_id != current_ride.id
            )
        ):
            raise HTTPException(
                status_code=400,
                detail=_CANDIDATE_UNAVAILABLE,
            )

        current_ride.shared_ride_consent = True

        candidate.accepted_driver_id = driver_id
        candidate.status = RideStatus.ACCEPTED
        candidate.shared_ride_with_id = current_ride.id
        candidate.shared_ride_consent = True
    @staticmethod
    def _candidate_is_open(candidate: RideRequest) -> bool:
        return (
            candidate.status == RideStatus.PENDING
            and candidate.accepted_driver_id is None
            and not candidate.is_next_ride
            and candidate.shared_ride_with_id is None
        )

    @staticmethod
    def _require_passenger_owner(
        db: Session,
        ride: RideRequest,
        current_user: User,
    ) -> None:
        passenger = (
            db.query(Passenger)
            .filter(Passenger.user_id == current_user.id)
            .first()
        )
        if passenger is None:
            raise HTTPException(
                status_code=404,
                detail=_PASSENGER_PROFILE_NOT_FOUND,
            )
        if ride.passenger_id != passenger.id:
            raise HTTPException(status_code=403, detail=_NOT_RIDE_PASSENGER)

    @staticmethod
    def _lock_ride(db: Session, ride_id: int) -> RideRequest | None:
        return (
            db.query(RideRequest)
            .filter(RideRequest.id == ride_id)
            .with_for_update()
            .first()
        )

