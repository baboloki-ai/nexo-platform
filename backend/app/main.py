import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import INTERNAL_VERIFY_SECRET, RIDE_OFFER_EXPIRY_SWEEP_INTERVAL_SECONDS
from app.database.database import SessionLocal
import app.models  # noqa: F401  — register all models on Base.metadata

from app.routers import driver
from app.routers import driver_push
from app.routers import internal
from app.routers import passenger
from app.routers import payment
from app.routers import ride_request
from app.routers import trip
from app.routers import user
from app.routers import vehicle

from app.services.notification_service import NotificationService
from app.services.ride_offer_expiry_service import RideOfferExpiryService

from app.websocket.routes import router as websocket_router


# ==========================================================
# Background: RideOffer TTL expiry sweep
# ==========================================================

async def _ride_offer_expiry_loop(stop_event: asyncio.Event) -> None:
    """
    Periodically expire stale pending RideOffers without blocking startup.
    Uses a dedicated DB session per sweep; stops cleanly on shutdown.
    """
    interval = RIDE_OFFER_EXPIRY_SWEEP_INTERVAL_SECONDS
    while not stop_event.is_set():
        try:
            db = SessionLocal()
            try:
                expired = await asyncio.to_thread(
                    RideOfferExpiryService.expire_stale_offers,
                    db,
                )
                if expired:
                    print(f"⏰ Expired {expired} stale RideOffer(s).")
            finally:
                db.close()
        except Exception as exc:
            print(f"⚠️ RideOffer expiry sweep failed: {exc}")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


# ==========================================================
# Application Lifespan
# ==========================================================

@asynccontextmanager
async def lifespan(app: FastAPI):

    print("\n========================================")
    print("🚖 NEXO Backend Starting...")
    print("========================================")

    NotificationService.bind_event_loop(
        asyncio.get_running_loop()
    )

    print("✅ NotificationService initialized.")

    if INTERNAL_VERIFY_SECRET:
        print("✅ Internal verification endpoint enabled.")
    else:
        print(
            "⚠ NEXO_INTERNAL_VERIFY_SECRET is unset. "
            "Internal driver/vehicle verification and wallet credit are disabled. "
            "Production ops must configure this secret."
        )

    stop_event = asyncio.Event()
    expiry_task = None
    disable_sweep = os.getenv(
        "NEXO_DISABLE_RIDE_OFFER_EXPIRY_SWEEP", ""
    ).lower() in ("1", "true", "yes")

    if not disable_sweep:
        expiry_task = asyncio.create_task(
            _ride_offer_expiry_loop(stop_event),
            name="ride-offer-expiry-loop",
        )
        print("✅ RideOffer expiry sweep started.")
    else:
        print("⏭ RideOffer expiry sweep disabled.")

    yield

    print("\n========================================")
    print("🛑 NEXO Backend Shutting Down...")
    print("========================================")

    stop_event.set()
    if expiry_task is not None:
        expiry_task.cancel()
        try:
            await expiry_task
        except asyncio.CancelledError:
            pass
        print("✅ RideOffer expiry sweep stopped.")


app = FastAPI(
    title="NEXO Ride API",
    version="3.0.0",
    lifespan=lifespan,
)

# ==========================================================
# Routers
# ==========================================================

app.include_router(user.router)
app.include_router(driver.router)
app.include_router(driver_push.router)
app.include_router(passenger.router)
app.include_router(vehicle.router)
app.include_router(ride_request.router)
app.include_router(trip.router)
app.include_router(payment.router)
app.include_router(internal.router)
# WebSocket Routes
app.include_router(websocket_router)

# ==========================================================
# Home
# ==========================================================

@app.get("/")
def home():
    return {
        "company": "NEXO Technologies",
        "product": "NEXO Ride",
        "message": "The Future of Mobility"
    }


# ==========================================================
# Health Check
# ==========================================================

@app.get("/health")
def health():
    return {
        "status": "OK"
    }