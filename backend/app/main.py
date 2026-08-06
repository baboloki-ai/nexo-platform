import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.database.base import Base
from app.database.database import engine

from app.routers import driver
from app.routers import passenger
from app.routers import ride_request
from app.routers import user
from app.routers import vehicle

from app.services.notification_service import NotificationService

from app.websocket.routes import router as websocket_router


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

    yield

    print("\n========================================")
    print("🛑 NEXO Backend Shutting Down...")
    print("========================================")


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
app.include_router(passenger.router)
app.include_router(vehicle.router)
app.include_router(ride_request.router)

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


# ==========================================================
# Database Test
# ==========================================================

@app.get("/db-test")
def db_test():

    try:

        with engine.connect() as connection:

            connection.execute(text("SELECT 1"))

        return {
            "database": "Connected successfully!"
        }

    except Exception as e:

        return {
            "error": str(e)
        }


# ==========================================================
# Database Info
# ==========================================================

@app.get("/db-info")
def db_info():

    return {
        "database_url": os.getenv("DATABASE_URL")
    }


# ==========================================================
# SQLAlchemy Tables
# ==========================================================

@app.get("/tables")
def tables():

    return list(Base.metadata.tables.keys())


# ==========================================================
# PostgreSQL Tables
# ==========================================================

@app.get("/list-db-tables")
def list_db_tables():

    with engine.connect() as connection:

        result = connection.execute(
            text("""
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public';
            """)
        )

        return [row[0] for row in result]


# ==========================================================
# Users in Database
# ==========================================================

@app.get("/users-db")
def users_db():

    with engine.connect() as connection:

        result = connection.execute(
            text("""
                SELECT
                    id,
                    full_name,
                    phone_number,
                    email
                FROM users
                ORDER BY id;
            """)
        )

        return [
            {
                "id": row[0],
                "full_name": row[1],
                "phone_number": row[2],
                "email": row[3],
            }
            for row in result
        ]