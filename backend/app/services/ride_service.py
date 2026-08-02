from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.constants.ride_status import RideStatus
from app.models.passenger import Passenger
from app.models.ride_request import RideRequest
from app.models.user import User
from app.services.dispatch_service import DispatchService


class RideService:

    @staticmethod
    def create_ride(
        db: Session,
        current_user: User,
        pickup_location: str,
        destination: str,
        proposed_fare: float
    ):
        passenger = db.query(Passenger).filter(
            Passenger.user_id == current_user.id
        ).first()

        if passenger is None:
            raise HTTPException(
                status_code=404,
                detail="Passenger profile not found."
            )

        active_ride = db.query(RideRequest).filter(
            RideRequest.passenger_id == passenger.id,
            RideRequest.status.in_([
    RideStatus.PENDING,
    RideStatus.PENDING_DRIVER_ACCEPTANCE,
    RideStatus.ACCEPTED,
    RideStatus.DRIVER_ARRIVING,
    RideStatus.DRIVER_ARRIVED,
    RideStatus.IN_PROGRESS,
])
        ).first()

        if active_ride:
            raise HTTPException(
                status_code=400,
                detail="You already have an active ride."
            )

        ride = RideRequest(
            passenger_id=passenger.id,
            pickup_location=pickup_location,
            destination=destination,
            proposed_fare=proposed_fare,
            status=RideStatus.PENDING
        )

        db.add(ride)
        db.commit()
        db.refresh(ride)

        # Automatically attempt to assign a driver.
        ride = DispatchService.assign_driver(
            db=db,
            ride=ride
        )

        return ride

    @staticmethod
    def get_available_rides(db: Session):
        return db.query(RideRequest).filter(
            RideRequest.status == "pending"
        ).all()

    @staticmethod
    def get_passenger_rides(
        db: Session,
        current_user: User
    ):
        passenger = db.query(Passenger).filter(
            Passenger.user_id == current_user.id
        ).first()

        if passenger is None:
            raise HTTPException(
                status_code=404,
                detail="Passenger profile not found."
            )

        return (
            db.query(RideRequest)
            .filter(RideRequest.passenger_id == passenger.id)
            .order_by(RideRequest.requested_at.desc())
            .all()
        )

    @staticmethod
    def accept_ride(
        db: Session,
        ride_id: int,
        current_user: User
    ):
        ride = db.query(RideRequest).filter(
            RideRequest.id == ride_id
        ).first()

        if ride is None:
            raise HTTPException(
                status_code=404,
                detail="Ride not found."
            )

        if ride.status != RideStatus.PENDING_DRIVER_ACCEPTANCE:
            raise HTTPException(
                status_code=400,
                detail="Ride is no longer available."
            )

        ride.accepted_driver_id = current_user.id
        ride.status = RideStatus.ACCEPTED

        db.commit()
        db.refresh(ride)

        return ride

    @staticmethod
    def arrive_at_pickup(
        db: Session,
        ride_id: int,
        current_user: User
    ):
        ride = db.query(RideRequest).filter(
            RideRequest.id == ride_id
        ).first()

        if ride is None:
            raise HTTPException(
                status_code=404,
                detail="Ride not found."
            )

        if ride.accepted_driver_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="You are not assigned to this ride."
            )

        if ride.status != RideStatus.ACCEPTED:
            raise HTTPException(
                status_code=400,
                detail="Ride is not in the accepted state."
            )

        ride.status = RideStatus.DRIVER_ARRIVING

        db.commit()
        db.refresh(ride)

        return ride

    @staticmethod
    def start_ride(
        db: Session,
        ride_id: int,
        current_user: User
    ):
        ride = db.query(RideRequest).filter(
            RideRequest.id == ride_id
        ).first()

        if ride is None:
            raise HTTPException(
                status_code=404,
                detail="Ride not found."
            )

        if ride.accepted_driver_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="You are not assigned to this ride."
            )

        if ride.status != RideStatus.DRIVER_ARRIVING:
            raise HTTPException(
                status_code=400,
                detail="Ride is not ready to start."
            )

        ride.status = RideStatus.IN_PROGRESS

        db.commit()
        db.refresh(ride)

        return ride

    @staticmethod
    def complete_ride(
        db: Session,
        ride_id: int,
        current_user: User
    ):
        ride = db.query(RideRequest).filter(
            RideRequest.id == ride_id
        ).first()

        if ride is None:
            raise HTTPException(
                status_code=404,
                detail="Ride not found."
            )

        if ride.accepted_driver_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="You are not assigned to this ride."
            )

        if ride.status != RideStatus.IN_PROGRESS:
            raise HTTPException(
                status_code=400,
                detail="Ride is not currently in progress."
            )

        ride.status = RideStatus.COMPLETED

        # Driver becomes available again after completing the ride.
        driver = db.query(User).filter(
            User.id == current_user.id
        ).first()

        if driver:
            driver.availability_status = "available"

        db.commit()
        db.refresh(ride)

        return ride