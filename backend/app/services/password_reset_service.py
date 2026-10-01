from datetime import datetime, timedelta, timezone
import hashlib
import secrets

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.password_reset_token import PasswordResetToken
from app.models.user import User


RESET_TOKEN_EXPIRE_MINUTES = 30


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_password_reset_token(db: Session, user: User) -> str:
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    db.execute(
        delete(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
    )

    raw_token = secrets.token_urlsafe(48)

    reset_token = PasswordResetToken(
        user_id=user.id,
        token_hash=_hash_token(raw_token),
        expires_at=now + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES),
    )

    db.add(reset_token)
    db.flush()

    return raw_token


def get_valid_password_reset_token(
    db: Session,
    raw_token: str,
) -> PasswordResetToken | None:
    token_hash = _hash_token(raw_token)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    token = db.scalar(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at.is_(None),
        )
    )

    if token is None or token.expires_at <= now:
        return None

    return token


def consume_password_reset_token(
    db: Session,
    token: PasswordResetToken,
) -> None:
    token.used_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.flush()
