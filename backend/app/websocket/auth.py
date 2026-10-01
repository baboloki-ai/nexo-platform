"""
WebSocket handshake authentication for NEXO realtime channels.

Token may be supplied as:
- query parameter: ?token=<jwt>
- Authorization header: Bearer <jwt>
"""
from __future__ import annotations

from fastapi import WebSocket
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import ALGORITHM, SECRET_KEY
from app.models.passenger import Passenger
from app.models.user import User

# Policy violation — unauthorized / forbidden identity for this channel.
WS_CLOSE_UNAUTHORIZED = 1008


def extract_websocket_token(websocket: WebSocket) -> str | None:
    """Return the JWT from query params or Authorization header, if present."""
    token = websocket.query_params.get("token")
    if token:
        return token

    authorization = websocket.headers.get("authorization")
    if authorization is None:
        return None

    scheme, _, credentials = authorization.partition(" ")
    if scheme.lower() != "bearer" or not credentials:
        return None

    return credentials.strip() or None


def load_user_from_token(db: Session, token: str) -> User | None:
    """Decode a JWT and return the matching User, or None if invalid."""
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )
    except JWTError:
        return None

    user_id = payload.get("sub")
    if user_id is None:
        return None

    try:
        parsed_id = int(user_id)
    except (TypeError, ValueError):
        return None

    return db.query(User).filter(User.id == parsed_id).first()


async def reject_websocket(websocket: WebSocket) -> None:
    """Reject the handshake without registering a ConnectionManager entry."""
    await websocket.close(code=WS_CLOSE_UNAUTHORIZED)


def authenticate_driver_socket(
    websocket: WebSocket,
    db: Session,
    driver_id: int,
) -> User | None:
    """
    Require a valid JWT for a user with role driver whose id matches driver_id.
    Returns the user on success; None if the connection must be rejected.
    """
    token = extract_websocket_token(websocket)
    if token is None:
        return None

    user = load_user_from_token(db, token)
    if user is None:
        return None

    if user.role != "driver":
        return None

    if user.id != driver_id:
        return None

    return user


def authenticate_passenger_socket(
    websocket: WebSocket,
    db: Session,
    passenger_id: int,
) -> User | None:
    """
    Require a valid JWT for a passenger whose profile id matches passenger_id.

    Path passenger_id is passengers.id (not users.id), matching NotificationService.
    """
    token = extract_websocket_token(websocket)
    if token is None:
        return None

    user = load_user_from_token(db, token)
    if user is None:
        return None

    if user.role != "passenger":
        return None

    profile = (
        db.query(Passenger)
        .filter(
            Passenger.id == passenger_id,
            Passenger.user_id == user.id,
        )
        .first()
    )
    if profile is None:
        return None

    return user
