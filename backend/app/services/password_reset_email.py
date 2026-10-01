import smtplib
from email.message import EmailMessage

from app import config


def send_password_reset_email(
    recipient_email: str,
    reset_token: str,
) -> None:
    if not all(
        [
            config.SMTP_HOST,
            config.SMTP_USERNAME,
            config.SMTP_PASSWORD,
            config.SMTP_FROM_EMAIL,
        ]
    ):
        raise RuntimeError("Password reset email service is not configured.")

    reset_url = f"{config.FRONTEND_URL}/reset-password?token={reset_token}"

    message = EmailMessage()
    message["Subject"] = "NEXO Ride - Reset Your Password"
    message["From"] = config.SMTP_FROM_EMAIL
    message["To"] = recipient_email
    message.set_content(
        f"""Hello,

We received a request to reset your NEXO Ride password.

Use the link below to create a new password:

{reset_url}

This link expires in 30 minutes and can only be used once.

If you did not request a password reset, you can safely ignore this email.

NEXO Ride
"""
    )

    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as smtp:
        if config.SMTP_USE_TLS:
            smtp.starttls()

        smtp.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
        smtp.send_message(message)
