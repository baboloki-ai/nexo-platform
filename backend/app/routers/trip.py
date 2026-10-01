from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.dependencies import get_db
from app.models.passenger import Passenger
from app.models.ride_request import RideRequest
from app.models.user import User
from app.schemas.ride_request import RideRequestResponse
from app.services.driver_identity_service import DriverIdentityService
from app.services.driver_service import DriverService
from app.services.marketplace_service import MarketplaceService
from app.utils.dependencies import get_current_user

router = APIRouter(
    prefix="/trips",
    tags=["Trips"],
)


@router.get("/ping")
def ping():
    return {
        "message": "Trip router is working!"
    }


@router.get(
    "/{ride_id}",
    response_model=RideRequestResponse,
)
def get_trip(
    ride_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    ride = (
        db.query(RideRequest)
        .filter(RideRequest.id == ride_id)
        .first()
    )

    if ride is None:
        raise HTTPException(
            status_code=404,
            detail="Trip not found.",
        )

    MarketplaceService.require_ride_viewer(db, ride, current_user)

    return DriverIdentityService.serialize_ride(db, ride)


@router.post(
    "/{ride_id}/accept",
    response_model=RideRequestResponse,
)
def accept_trip(
    ride_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):

    if current_user.role != "driver":
        raise HTTPException(
            status_code=403,
            detail="Only drivers can accept rides.",
        )

    ride = DriverService.accept_ride(
        db=db,
        ride_id=ride_id,
        driver_id=current_user.id,
    )

    if ride is None:
        raise HTTPException(
            status_code=404,
            detail="Ride not found or cannot be accepted.",
        )

    return DriverIdentityService.serialize_ride(db, ride)
