from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.services.driver_service import DriverService
from app.database.dependencies import get_db
from app.models.user import User
from app.schemas.ride_request import (
    RideRequestCreate,
    RideRequestResponse,
)
from app.services.ride_service import RideService
from app.utils.dependencies import get_current_user
from fastapi import APIRouter, Depends, HTTPException
router = APIRouter(
    prefix="/rides",
    tags=["Ride Requests"]
)


@router.post("/", response_model=RideRequestResponse)
def create_ride_request(
    ride: RideRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return RideService.create_ride(
        db=db,
        current_user=current_user,
        pickup_location=ride.pickup_location,
        destination=ride.destination,
        proposed_fare=ride.proposed_fare
    )


@router.get("/available", response_model=list[RideRequestResponse])
def get_available_rides(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return RideService.get_available_rides(db)


@router.get("/my", response_model=list[RideRequestResponse])
def get_my_rides(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return RideService.get_passenger_rides(
        db=db,
        current_user=current_user
    )


@router.put("/{ride_id}/accept", response_model=RideRequestResponse)
def accept_ride(
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return RideService.accept_ride(
        db=db,
        ride_id=ride_id,
        current_user=current_user
    )
@router.put("/{ride_id}/reject")
def reject_ride(
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ride = DriverService.reject_ride(
        db=db,
        ride_id=ride_id,
        driver_id=current_user.id
    )

    if ride is None:
        raise HTTPException(
            status_code=404,
            detail="Ride not found or cannot be rejected."
        )

    return {
        "message": "Ride rejected successfully.",
        "ride": ride
    }

@router.put("/{ride_id}/arrive", response_model=RideRequestResponse)
def arrive_at_pickup(
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return RideService.arrive_at_pickup(
        db=db,
        ride_id=ride_id,
        current_user=current_user
    )
@router.put(
    "/{ride_id}/driver-arrived",
    response_model=RideRequestResponse
)
def driver_arrived(
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return RideService.driver_arrived(
        db=db,
        ride_id=ride_id,
        current_user=current_user
    )

@router.put("/{ride_id}/start", response_model=RideRequestResponse)
def start_ride(
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return RideService.start_ride(
        db=db,
        ride_id=ride_id,
        current_user=current_user
    )


@router.put("/{ride_id}/complete", response_model=RideRequestResponse)
def complete_ride(
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return RideService.complete_ride(
        db=db,
        ride_id=ride_id,
        current_user=current_user
    )