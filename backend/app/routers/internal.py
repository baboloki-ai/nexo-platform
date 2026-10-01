import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app import config
from app.constants.ride_status import RideStatus
from app.constants.verification import VerificationStatus
from app.database.dependencies import get_db
from app.models.ride_request import RideRequest
from app.models.user import User
from app.models.vehicle import Vehicle
from app.schemas.driver import DriverProfileResponse, DriverVerificationUpdate, DriverWalletCreditRequest
from app.schemas.vehicle import VehicleResponse, VehicleVerificationUpdate
from app.services.driver_identity_service import DriverIdentityService
from app.services.wallet_service import WalletService

router = APIRouter(
    prefix="/internal",
    tags=["Internal"],
    include_in_schema=False,
)

_ACTIVE_ASSIGNMENT_STATUSES = (
    RideStatus.PENDING_DRIVER_ACCEPTANCE,
    RideStatus.ACCEPTED,
    RideStatus.DRIVER_ARRIVING,
    RideStatus.DRIVER_ARRIVED,
    RideStatus.IN_PROGRESS,
)


def _require_internal_secret(
    x_nexo_internal_secret: str | None,
) -> None:
    expected = config.INTERNAL_VERIFY_SECRET
    if not expected:
        raise HTTPException(status_code=404, detail="Not found.")
    provided = x_nexo_internal_secret or ""
    if len(provided) != len(expected) or not secrets.compare_digest(
        provided,
        expected,
    ):
        raise HTTPException(status_code=401, detail="Unauthorized.")


@router.post(
    "/drivers/{driver_id}/verification",
    response_model=DriverProfileResponse,
)
def set_driver_verification(
    driver_id: int,
    payload: DriverVerificationUpdate,
    db: Session = Depends(get_db),
    x_nexo_internal_secret: str | None = Header(
        default=None,
        alias="X-NEXO-INTERNAL-SECRET",
    ),
):
    """
    Controlled development/test mechanism for driver verification.

    Disabled unless NEXO_INTERNAL_VERIFY_SECRET is configured.
    Not a public self-approve API and not authenticated as the driver.
    """
    _require_internal_secret(x_nexo_internal_secret)

    status = payload.status.strip().lower()
    if status not in VerificationStatus.ALL:
        raise HTTPException(
            status_code=400,
            detail="Invalid verification status.",
        )

    driver = (
        db.query(User)
        .filter(User.id == driver_id, User.role == "driver")
        .first()
    )
    if driver is None:
        raise HTTPException(status_code=404, detail="Driver not found.")

    driver.verification_status = status

    if status in (VerificationStatus.SUSPENDED, VerificationStatus.REJECTED):
        active = (
            db.query(RideRequest)
            .filter(
                RideRequest.accepted_driver_id == driver.id,
                RideRequest.status.in_(_ACTIVE_ASSIGNMENT_STATUSES),
            )
            .first()
        )
        if active is None and driver.availability_status in (
            "available",
            "reserved",
        ):
            driver.availability_status = "offline"

    db.commit()
    db.refresh(driver)
    return DriverIdentityService.profile_response(db, driver)


@router.post(
    "/vehicles/{vehicle_id}/verification",
    response_model=VehicleResponse,
)
def set_vehicle_verification(
    vehicle_id: int,
    payload: VehicleVerificationUpdate,
    db: Session = Depends(get_db),
    x_nexo_internal_secret: str | None = Header(
        default=None,
        alias="X-NEXO-INTERNAL-SECRET",
    ),
):
    """
    Controlled development/test/ops mechanism for vehicle verification.

    Disabled unless NEXO_INTERNAL_VERIFY_SECRET is configured.
    Not a public self-approve API and not authenticated as the driver.
    Updates only the target vehicle's verification_status.
    """
    _require_internal_secret(x_nexo_internal_secret)

    status = payload.status.strip().lower()
    if status not in VerificationStatus.ALL:
        raise HTTPException(
            status_code=400,
            detail="Invalid verification status.",
        )

    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Vehicle not found.")

    vehicle.verification_status = status
    db.commit()
    db.refresh(vehicle)
    return vehicle


@router.post("/drivers/{driver_id}/wallet/credit")
def credit_driver_wallet(
    driver_id: int,
    payload: DriverWalletCreditRequest,
    db: Session = Depends(get_db),
    x_nexo_internal_secret: str | None = Header(
        default=None,
        alias="X-NEXO-INTERNAL-SECRET",
    ),
):
    """Ops/test wallet credit. Disabled unless NEXO_INTERNAL_VERIFY_SECRET is set."""
    _require_internal_secret(x_nexo_internal_secret)
    driver = (
        db.query(User)
        .filter(User.id == driver_id, User.role == "driver")
        .first()
    )
    if driver is None:
        raise HTTPException(status_code=404, detail="Driver not found.")
    wallet = WalletService.credit(
        db,
        driver_id=driver.id,
        amount=payload.amount,
    )
    return WalletService.serialize_wallet(wallet)

