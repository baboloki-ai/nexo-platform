import os
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

from dotenv import load_dotenv

load_dotenv()


def _env_decimal(name: str, default: str) -> Decimal:
    raw = (os.getenv(name) or default).strip()
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError):
        value = Decimal(default)
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES")
)
RIDE_OFFER_TTL_SECONDS = int(os.getenv("RIDE_OFFER_TTL_SECONDS", "300"))
RIDE_OFFER_EXPIRY_SWEEP_INTERVAL_SECONDS = int(
    os.getenv("RIDE_OFFER_EXPIRY_SWEEP_INTERVAL_SECONDS", "30")
)

INTERNAL_VERIFY_SECRET = (
    os.getenv("NEXO_INTERNAL_VERIFY_SECRET", "").strip() or None
)

NEXO_BASE_FARE = _env_decimal("NEXO_BASE_FARE", "20")
NEXO_FARE_PER_KM = _env_decimal("NEXO_FARE_PER_KM", "2.50")

VAPID_PUBLIC_KEY = (os.getenv("VAPID_PUBLIC_KEY") or "").strip() or None
VAPID_PRIVATE_KEY = (os.getenv("VAPID_PRIVATE_KEY") or "").strip() or None
VAPID_CLAIM_EMAIL = (
    os.getenv("VAPID_CLAIM_EMAIL") or "mailto:nexo@localhost"
).strip()

# Password-reset email delivery.
SMTP_HOST = (os.getenv("SMTP_HOST") or "").strip() or None
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = (os.getenv("SMTP_USERNAME") or "").strip() or None
SMTP_PASSWORD = (os.getenv("SMTP_PASSWORD") or "").strip() or None
SMTP_FROM_EMAIL = (os.getenv("SMTP_FROM_EMAIL") or "").strip() or None
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").strip().lower() == "true"
FRONTEND_URL = (
    os.getenv("FRONTEND_URL") or "http://localhost:5173"
).strip().rstrip("/")

print("ALGORITHM:", ALGORITHM)
print("ACCESS_TOKEN_EXPIRE_MINUTES:", ACCESS_TOKEN_EXPIRE_MINUTES)
print("RIDE_OFFER_TTL_SECONDS:", RIDE_OFFER_TTL_SECONDS)
