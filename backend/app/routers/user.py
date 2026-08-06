from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database.dependencies import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse
from app.utils.dependencies import get_current_user
from app.utils.jwt import create_access_token
from app.utils.security import hash_password, verify_password

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
        role=user.role
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


@router.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    print("========== LOGIN START ==========")

    user = (
        db.query(User)
        .filter(User.email == form_data.username)
        .first()
    )

    print("User:", user)

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found."
        )

    password_ok = verify_password(
        form_data.password,
        user.password
    )

    print("Password OK:", password_ok)

    if not password_ok:
        raise HTTPException(
            status_code=401,
            detail="Incorrect password."
        )

    print("Creating JWT...")

    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "email": user.email,
            "role": user.role
        }
    )

    print("JWT created successfully")

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }


@router.get("/me", response_model=UserResponse)
def get_me(
    current_user: User = Depends(get_current_user)
):
    return current_user


@router.get("/", response_model=List[UserResponse])
def get_users(
    db: Session = Depends(get_db)
):
    return db.query(User).all()