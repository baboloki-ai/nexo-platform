from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import exists, select, update
from sqlalchemy.orm import Session

from app.constants.ride_status import RideStatus
from app.constants.verification import VerificationStatus
from app.database.dependencies import get_db
from app.models.ride_request import RideRequest
from app.models.user import User
from app.models.vehicle import Vehicle
from app.schemas.driver import (
    DriverDemandResponse,
    DriverLocationUpdate,
    DriverOpenRequest,
    DriverPerformanceResponse,
    DriverProfileResponse,
    DriverProfileUpdate,
    DriverStatusResponse,
    DriverWalletResponse,
)
from app.schemas.ride_request import RideRequestResponse
from app.services.driver_identity_service import DriverIdentityService
from app.services.driver_insights_service import DriverInsightsService
from app.services.gps_service import GPSService
from app.services.marketplace_service import MarketplaceService
from app.services.ride_service import RideService
from app.services.wallet_service import WalletService
from app.utils.dependencies import get_current_user

router = APIRouter(
    prefix="/drivers",
    tags=["Drivers"]
)


def _require_driver(current_user: User) -> User:
    if current_user.role != "driver":
        raise HTTPException(
            status_code=403,
            detail="Only drivers can access this resource.",
        )
    return current_user


def _go_online_blocked_detail(status: str | None) -> str:
    if status == VerificationStatus.SUSPENDED:
        return "Driver account is suspended."
    return "Driver account is not approved."


@router.get("/me", response_model=DriverProfileResponse)
def get_driver_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    driver = _require_driver(current_user)
    return DriverIdentityService.profile_response(db, driver)


@router.patch("/me", response_model=DriverProfileResponse)
def update_driver_profile(
    payload: DriverProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    driver = _require_driver(current_user)

    if payload.display_name is not None:
        name = payload.display_name.strip()
        if not name:
            raise HTTPException(
                status_code=400,
                detail="Display name cannot be empty.",
            )
        driver.full_name = name

    if payload.phone_number is not None:
        phone = payload.phone_number.strip()
        if not phone:
            raise HTTPException(
                status_code=400,
                detail="Phone number cannot be empty.",
            )
        conflict = (
            db.query(User)
            .filter(
                User.phone_number == phone,
                User.id != driver.id,
            )
            .first()
        )
        if conflict is not None:
            raise HTTPException(
                status_code=400,
                detail="Phone number already in use.",
            )
        driver.phone_number = phone

    if payload.profile_photo_url is not None:
        url = payload.profile_photo_url.strip()
        driver.profile_photo_url = url or None

    driver.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(driver)
    return DriverIdentityService.profile_response(db, driver)


@router.get("/rides", response_model=list[RideRequestResponse])
def get_driver_rides(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rides = RideService.get_driver_rides(
        db=db,
        current_user=current_user,
    )
    return DriverIdentityService.serialize_rides(db, rides)


@router.get("/requests", response_model=list[DriverOpenRequest])
def get_marketplace_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    driver = _require_driver(current_user)
    return DriverInsightsService.list_open_requests(db, driver)


@router.get("/wallet", response_model=DriverWalletResponse)
def get_driver_wallet(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    driver = _require_driver(current_user)
    wallet = WalletService.ensure_wallet(db, driver.id)
    ledger = WalletService.list_ledger(db, driver.id)
    return WalletService.serialize_wallet(wallet, ledger=ledger)


@router.get("/wallet/ledger")
def get_driver_wallet_ledger(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    driver = _require_driver(current_user)
    entries = WalletService.list_ledger(db, driver.id)
    return [WalletService.serialize_ledger_entry(entry) for entry in entries]


@router.get("/performance", response_model=DriverPerformanceResponse)
def get_driver_performance(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    driver = _require_driver(current_user)
    return DriverInsightsService.performance(db, driver)


@router.get("/demand", response_model=DriverDemandResponse)
def get_driver_demand(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    driver = _require_driver(current_user)
    return DriverInsightsService.demand(db, driver)


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

    if current_user.verification_status != VerificationStatus.APPROVED:
        raise HTTPException(
            status_code=403,
            detail=_go_online_blocked_detail(current_user.verification_status),
        )

    approved_vehicle = (
        db.query(Vehicle)
        .filter(
            Vehicle.driver_id == current_user.id,
            Vehicle.verification_status == VerificationStatus.APPROVED,
        )
        .first()
    )
    if approved_vehicle is None:
        raise HTTPException(
            status_code=403,
            detail="Driver does not have an approved vehicle.",
        )

    active_assignment = (
        db.query(RideRequest)
        .filter(
            RideRequest.accepted_driver_id == current_user.id,
            RideRequest.status.in_(
                [
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
    if active_assignment is not None:
        if active_assignment.status == RideStatus.PENDING_DRIVER_ACCEPTANCE:
            raise HTTPException(
                status_code=400,
                detail="Driver has a pending ride assignment.",
            )
        raise HTTPException(
            status_code=400,
            detail="Driver has an active ride.",
        )

    WalletService.require_minimum_for_online(db, current_user.id)

    if (
        current_user.current_latitude is None
        or current_user.current_longitude is None
    ):
        raise HTTPException(
            status_code=400,
            detail="Current GPS location is required to go online.",
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

    # Atomically go offline only when no post-accept active ride exists.
    result = db.execute(
        update(User)
        .where(
            User.id == current_user.id,
            ~exists(
                select(RideRequest.id).where(
                    RideRequest.accepted_driver_id == current_user.id,
                    RideRequest.status.in_(
                        [
                            RideStatus.ACCEPTED,
                            RideStatus.DRIVER_ARRIVING,
                            RideStatus.DRIVER_ARRIVED,
                            RideStatus.IN_PROGRESS,
                        ]
                    ),
                )
            ),
        )
        .values(
            availability_status="offline",
            last_seen=datetime.utcnow(),
        )
        .execution_options(synchronize_session=False)
    )

    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Driver has an active ride.",
        )

    MarketplaceService.withdraw_driver_open_responses(db, current_user.id)

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

    driver = GPSService.update_driver_location(
        db=db,
        driver=current_user,
        latitude=location.latitude,
        longitude=location.longitude,
        accuracy=location.accuracy,
        speed=location.speed,
        heading=location.heading,
        timestamp=location.timestamp,
    )

    return {
        "message": "Location updated successfully.",
        "latitude": driver.current_latitude,
        "longitude": driver.current_longitude,
    }
