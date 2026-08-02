from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.dependencies import get_db
from app.models.user import User
from app.schemas.driver import (
    DriverLocationUpdate,
    DriverStatusResponse,
)
from app.utils.dependencies import get_current_user

router = APIRouter(
    prefix="/drivers",
    tags=["Drivers"]
)


@router.put(
    "/go-online",
    response_model=DriverStatusResponse,
)
def go_online(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "driver":
        raise HTTPException(
            status_code=403,
            detail="Only drivers can go online.",
        )

    current_user.availability_status = "available"
    current_user.last_seen = datetime.utcnow()

    db.commit()
    db.refresh(current_user)

    return DriverStatusResponse(
        message="Driver is now online.",
        status=current_user.availability_status,
    )


@router.put(
    "/go-offline",
    response_model=DriverStatusResponse,
)
def go_offline(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "driver":
        raise HTTPException(
            status_code=403,
            detail="Only drivers can go offline.",
        )

    current_user.availability_status = "offline"
    current_user.last_seen = datetime.utcnow()

    db.commit()
    db.refresh(current_user)

    return DriverStatusResponse(
        message="Driver is now offline.",
        status=current_user.availability_status,
    )


@router.put("/location")
def update_location(
    location: DriverLocationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "driver":
        raise HTTPException(
            status_code=403,
            detail="Only drivers can update their location.",
        )

    current_user.current_latitude = location.latitude
    current_user.current_longitude = location.longitude
    current_user.last_seen = datetime.utcnow()

    db.commit()
    db.refresh(current_user)

    return {
        "message": "Location updated successfully.",
        "latitude": current_user.current_latitude,
        "longitude": current_user.current_longitude,
    }