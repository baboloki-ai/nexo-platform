from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.constants.verification import VerificationStatus
from app.database.dependencies import get_db
from app.models.user import User
from app.models.vehicle import Vehicle
from app.schemas.vehicle import (
    VehicleCreate,
    VehicleResponse,
    VehicleUpdate,
)
from app.utils.dependencies import require_driver

router = APIRouter(
    prefix="/vehicles",
    tags=["Vehicles"],
)


@router.post("/", response_model=VehicleResponse)
def create_vehicle(
    vehicle: VehicleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_driver),
):
    new_vehicle = Vehicle(
        driver_id=current_user.id,
        make=vehicle.make,
        model=vehicle.model,
        year=vehicle.year,
        color=vehicle.color,
        registration_number=vehicle.registration_number,
        vehicle_type=vehicle.vehicle_type,
        verification_status=VerificationStatus.PENDING,
    )

    db.add(new_vehicle)
    db.commit()
    db.refresh(new_vehicle)

    return new_vehicle


@router.get("/", response_model=List[VehicleResponse])
@router.get("/my", response_model=List[VehicleResponse])
def get_my_vehicles(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_driver),
):
    vehicles = (
        db.query(Vehicle)
        .filter(Vehicle.driver_id == current_user.id)
        .all()
    )

    return vehicles


@router.get("/{vehicle_id}", response_model=VehicleResponse)
def get_vehicle(
    vehicle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_driver),
):
    vehicle = (
        db.query(Vehicle)
        .filter(
            Vehicle.id == vehicle_id,
            Vehicle.driver_id == current_user.id,
        )
        .first()
    )

    if vehicle is None:
        raise HTTPException(
            status_code=404,
            detail="Vehicle not found",
        )

    return vehicle


@router.put("/{vehicle_id}", response_model=VehicleResponse)
def update_vehicle(
    vehicle_id: int,
    update: VehicleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_driver),
):
    vehicle = (
        db.query(Vehicle)
        .filter(
            Vehicle.id == vehicle_id,
            Vehicle.driver_id == current_user.id,
        )
        .first()
    )

    if vehicle is None:
        raise HTTPException(
            status_code=404,
            detail="Vehicle not found",
        )

    vehicle.make = update.make
    vehicle.model = update.model
    vehicle.year = update.year
    vehicle.color = update.color
    vehicle.registration_number = update.registration_number
    vehicle.vehicle_type = update.vehicle_type

    db.commit()
    db.refresh(vehicle)

    return vehicle


@router.delete("/{vehicle_id}")
def delete_vehicle(
    vehicle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_driver),
):
    vehicle = (
        db.query(Vehicle)
        .filter(
            Vehicle.id == vehicle_id,
            Vehicle.driver_id == current_user.id,
        )
        .first()
    )

    if vehicle is None:
        raise HTTPException(
            status_code=404,
            detail="Vehicle not found",
        )

    db.delete(vehicle)
    db.commit()

    return {"message": "Vehicle deleted successfully"}