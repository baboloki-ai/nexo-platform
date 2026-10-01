from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.dependencies import get_db
from app.models.passenger import Passenger
from app.models.ride_request import RideRequest
from app.models.user import User
from app.schemas.passenger import (
    PassengerCreate,
    PassengerResponse,
    PassengerUpdate,
)
from app.utils.dependencies import get_current_user

router = APIRouter(
    prefix="/passengers",
    tags=["Passengers"],
)


@router.post("/", response_model=PassengerResponse)
def create_passenger(
    passenger: PassengerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    new_passenger = Passenger(
        user_id=current_user.id,
        first_name=passenger.first_name,
        last_name=passenger.last_name,
        phone=passenger.phone,
        email=passenger.email,
    )

    db.add(new_passenger)
    db.commit()
    db.refresh(new_passenger)

    return new_passenger


@router.get("/my", response_model=List[PassengerResponse])
def get_my_passengers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(Passenger)
        .filter(Passenger.user_id == current_user.id)
        .all()
    )


@router.get("/{passenger_id}", response_model=PassengerResponse)
def get_passenger(
    passenger_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    passenger = (
        db.query(Passenger)
        .filter(
            Passenger.id == passenger_id,
            Passenger.user_id == current_user.id,
        )
        .first()
    )

    if passenger is None:
        raise HTTPException(
            status_code=404,
            detail="Passenger not found",
        )

    return passenger


@router.put("/{passenger_id}", response_model=PassengerResponse)
def update_passenger(
    passenger_id: int,
    update: PassengerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    passenger = (
        db.query(Passenger)
        .filter(
            Passenger.id == passenger_id,
            Passenger.user_id == current_user.id,
        )
        .first()
    )

    if passenger is None:
        raise HTTPException(
            status_code=404,
            detail="Passenger not found",
        )

    passenger.first_name = update.first_name
    passenger.last_name = update.last_name
    passenger.phone = update.phone
    passenger.email = update.email

    db.commit()
    db.refresh(passenger)

    return passenger


@router.delete("/{passenger_id}")
def delete_passenger(
    passenger_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    passenger = (
        db.query(Passenger)
        .filter(
            Passenger.id == passenger_id,
            Passenger.user_id == current_user.id,
        )
        .first()
    )

    if passenger is None:
        raise HTTPException(
            status_code=404,
            detail="Passenger not found",
        )

    ride_history = (
        db.query(RideRequest)
        .filter(RideRequest.passenger_id == passenger.id)
        .first()
    )
    if ride_history is not None:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete passenger profile with ride history.",
        )

    db.delete(passenger)
    db.commit()

    return {"message": "Passenger deleted successfully"}