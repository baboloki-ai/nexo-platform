from datetime import datetime, timedelta

from app.models.password_reset_token import PasswordResetToken
from app.services.password_reset_service import (
    create_password_reset_token,
    get_valid_password_reset_token,
    consume_password_reset_token,
)
from app.utils.security import verify_password


def test_password_reset_token_is_hashed_and_valid(db_session, passenger_user):
    raw_token = create_password_reset_token(db_session, passenger_user)
    db_session.commit()

    token = (
        db_session.query(PasswordResetToken)
        .filter(PasswordResetToken.user_id == passenger_user.id)
        .first()
    )

    assert token is not None
    assert token.token_hash != raw_token
    assert len(token.token_hash) == 64
    assert get_valid_password_reset_token(db_session, raw_token) is not None


def test_password_reset_token_expires(db_session, passenger_user):
    raw_token = create_password_reset_token(db_session, passenger_user)
    db_session.commit()

    token = (
        db_session.query(PasswordResetToken)
        .filter(PasswordResetToken.user_id == passenger_user.id)
        .first()
    )

    token.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db_session.commit()

    assert get_valid_password_reset_token(db_session, raw_token) is None


def test_password_reset_token_can_only_be_used_once(db_session, passenger_user):
    raw_token = create_password_reset_token(db_session, passenger_user)
    db_session.commit()

    token = get_valid_password_reset_token(db_session, raw_token)
    assert token is not None

    consume_password_reset_token(db_session, token)
    db_session.commit()

    assert get_valid_password_reset_token(db_session, raw_token) is None


def test_new_password_replaces_old_password(db_session, passenger_user):
    old_password = "TestPassenger123!"
    new_password = "NewSecurePassword456!"

    raw_token = create_password_reset_token(db_session, passenger_user)
    db_session.commit()

    token = get_valid_password_reset_token(db_session, raw_token)
    assert token is not None

    passenger_user.password = __import__(
        "app.utils.security",
        fromlist=["hash_password"],
    ).hash_password(new_password)

    consume_password_reset_token(db_session, token)
    db_session.commit()

    assert verify_password(new_password, passenger_user.password)
    assert not verify_password(old_password, passenger_user.password)
