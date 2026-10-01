from unittest.mock import patch

from app.models.password_reset_token import PasswordResetToken


def test_forgot_password_unknown_email_is_generic(client):
    response = client.post(
        "/users/forgot-password",
        json={"email": "doesnotexist@test.nexo"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "message": "If an account exists for that email address, a password reset link has been sent."
    }


def test_forgot_password_existing_email_sends_email(
    client,
    passenger_user,
):
    with patch(
        "app.routers.user.send_password_reset_email"
    ) as mock_send:
        response = client.post(
            "/users/forgot-password",
            json={"email": passenger_user.email},
        )

    assert response.status_code == 200
    assert response.json() == {
        "message": "If an account exists for that email address, a password reset link has been sent."
    }

    mock_send.assert_called_once()

    reset_token = (
        client.app.state.test_reset_token
        if hasattr(client.app.state, "test_reset_token")
        else None
    )

    assert mock_send.call_args.args[0] == passenger_user.email


def test_reset_password_endpoint(client, passenger_user, db_session):
    with patch(
        "app.routers.user.send_password_reset_email"
    ) as mock_send:
        response = client.post(
            "/users/forgot-password",
            json={"email": passenger_user.email},
        )

    assert response.status_code == 200

    sent_token = mock_send.call_args.args[1]

    response = client.post(
        "/users/reset-password",
        json={
            "token": sent_token,
            "new_password": "ResetPassword456!",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "message": "Your password has been reset successfully."
    }

    response = client.post(
        "/users/reset-password",
        json={
            "token": sent_token,
            "new_password": "AnotherPassword789!",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid or expired password reset link."
