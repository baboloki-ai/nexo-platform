from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.dependencies import get_db
from app.models.user import User
from app.schemas.payment import PaymentPublic
from app.services.payment_service import PaymentService
from app.utils.dependencies import get_current_user

router = APIRouter(
    prefix="/payments",
    tags=["Payments"],
)


@router.post(
    "/{payment_id}/confirm-cash",
    response_model=PaymentPublic,
)
def confirm_cash(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return PaymentService.confirm_cash(db, payment_id, current_user)
