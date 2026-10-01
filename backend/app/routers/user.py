from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.constants.verification import VerificationStatus
from app.database.dependencies import get_db
from app.models.user import User
from app.schemas.user import (
    UserCreate,
    UserResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
)
from app.utils.dependencies import get_current_user
from app.utils.jwt import create_access_token
from app.utils.security import hash_password, verify_password
from app.services.wallet_service import WalletService
from app.services.password_reset_service import (
    create_password_reset_token,
    get_valid_password_reset_token,
    consume_password_reset_token,
)
from app.services.password_reset_email import send_password_reset_email

router = APIRouter(
    prefix="/users",
    tags=["Users"]
)


@router.post("/", response_model=UserResponse)
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db)
):
    hashed_password = hash_password(user.password)

    new_user = User(
        full_name=user.full_name,
        phone_number=user.phone_number,
        email=user.email,
        password=hashed_password,
        role=user.role,
        verification_status=(
            VerificationStatus.PENDING if user.role == "driver" else None
        ),
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    if new_user.role == "driver":
        WalletService.ensure_wallet(db, new_user.id)
        db.commit()
        db.refresh(new_user)

    return new_user


@router.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = (
        db.query(User)
        .filter(User.email == form_data.username)
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found."
        )

    password_ok = verify_password(
        form_data.password,
        user.password
    )

    if not password_ok:
        raise HTTPException(
            status_code=401,
            detail="Incorrect password."
        )

    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "email": user.email,
            "role": user.role
        }
    )

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }


@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
)
def forgot_password(
    request: ForgotPasswordRequest,
    db: Session = Depends(get_db),
):
    user = (
        db.query(User)
        .filter(User.email == request.email)
        .first()
    )

    generic_message = (
        "If an account exists for that email address, "
        "a password reset link has been sent."
    )

    if user is None:
        return {"message": generic_message}

    reset_token = create_password_reset_token(db, user)

    try:
        send_password_reset_email(user.email, reset_token)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Password reset email service is temporarily unavailable.",
        )

    return {"message": generic_message}


@router.post(
    "/reset-password",
    response_model=ResetPasswordResponse,
)
def reset_password(
    request: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    reset_token = get_valid_password_reset_token(db, request.token)

    if reset_token is None:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired password reset link.",
        )

    if len(request.new_password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters long.",
        )

    user = db.query(User).filter(User.id == reset_token.user_id).first()

    if user is None:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired password reset link.",
        )

    user.password = hash_password(request.new_password)
    consume_password_reset_token(db, reset_token)
    db.commit()

    return {
        "message": "Your password has been reset successfully."
    }


@router.get("/me", response_model=UserResponse)
def get_me(
    current_user: User = Depends(get_current_user)
):
    return current_user
