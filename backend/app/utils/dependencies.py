from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import SECRET_KEY, ALGORITHM
from app.database.dependencies import get_db
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/users/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    print("========== AUTH ==========")
    print("Received Token:", token)

    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
    )

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )

        print("Decoded Payload:", payload)

        user_id = payload.get("sub")

        if user_id is None:
            print("No user_id in token")
            raise credentials_exception

    except JWTError as e:
        print("JWT ERROR:", e)
        raise credentials_exception

    user = db.query(User).filter(User.id == int(user_id)).first()

    print("Database User:", user)

    if user is None:
        raise credentials_exception

    return user