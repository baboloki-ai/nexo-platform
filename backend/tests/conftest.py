"""
Pytest configuration for the NEXO backend.

Isolated test database strategy
-------------------------------
- Tests require TEST_DATABASE_URL (a dedicated PostgreSQL database).
- The URL must contain the word "test" and must NOT match DATABASE_URL in .env.
- Before importing application modules, DATABASE_URL is overridden so SQLAlchemy
  binds to the test database only during pytest runs.
- Schema is created once per session via Base.metadata.create_all() against the
  test database only; development data is never read or written by fixtures.
"""
from __future__ import annotations

import os
from decimal import Decimal
from collections.abc import Generator
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import pytest
from dotenv import dotenv_values, load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text, update
from sqlalchemy.engine import Engine, URL
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = BACKEND_ROOT / ".env"
TEST_DATABASE_NAME = "nexo_test"

# Load backend/.env for local pytest runs. Existing process env (shell/CI) wins.
load_dotenv(ENV_FILE)


def _parse_database_url(url: str) -> tuple[str, str, str, str, int | None, str]:
    """
    Split a SQLAlchemy/PostgreSQL URL into components.

    Standard parsers break when the password contains an unencoded '@'.
    Use the final '@' as the userinfo/host separator, then decode the password.
    """
    if "://" not in url or "@" not in url:
        pytest.exit(
            "Database URL must look like "
            "postgresql://user:password@host:port/database.",
            returncode=1,
        )

    drivername, remainder = url.split("://", 1)
    userinfo, host_and_path = remainder.rsplit("@", 1)
    username, separator, password = userinfo.partition(":")
    if not separator:
        password = ""

    host_port, _, path = host_and_path.partition("/")
    if not host_port:
        pytest.exit("Database URL is missing a host.", returncode=1)

    host: str
    port: int | None
    if ":" in host_port:
        host, port_text = host_port.rsplit(":", 1)
        try:
            port = int(port_text)
        except ValueError:
            host = host_port
            port = None
    else:
        host = host_port
        port = None

    database = path.split("?", 1)[0]
    return drivername, username, unquote(password), host, port, database


def _render_database_url(
    drivername: str,
    username: str,
    password: str,
    host: str,
    port: int | None,
    database: str,
) -> str:
    """Build a valid SQLAlchemy URL with password encoding handled by URL.create."""
    return URL.create(
        drivername=drivername,
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
    ).render_as_string(hide_password=False)


def _normalize_database_url(url: str, database_name: str | None = None) -> str:
    drivername, username, password, host, port, database = _parse_database_url(url)
    target_database = database_name if database_name is not None else database
    if not target_database:
        pytest.exit("Database URL is missing a database name.", returncode=1)
    return _render_database_url(
        drivername,
        username,
        password,
        host,
        port,
        target_database,
    )


def _require_test_database_url() -> str:
    explicit = os.getenv("TEST_DATABASE_URL")
    if explicit:
        # Shell/CI override: re-parse and re-render so raw '@' in passwords is safe.
        test_url = _normalize_database_url(explicit)
    else:
        # Prefer credentials from backend/.env; point them at the dedicated test DB.
        database_url = dotenv_values(ENV_FILE).get("DATABASE_URL") or os.getenv(
            "DATABASE_URL"
        )
        if not database_url:
            pytest.exit(
                "DATABASE_URL is not set. "
                "Cannot derive a test database URL for pytest.",
                returncode=1,
            )
        test_url = _normalize_database_url(
            database_url,
            database_name=TEST_DATABASE_NAME,
        )

    if "test" not in test_url.lower():
        pytest.exit(
            "TEST_DATABASE_URL must reference a dedicated test database "
            "(the URL must contain 'test').",
            returncode=1,
        )

    dev_url = dotenv_values(ENV_FILE).get("DATABASE_URL")
    if dev_url and (
        dev_url == test_url
        or _parse_database_url(dev_url)[3:] == _parse_database_url(test_url)[3:]
    ):
        # Reject identical URL strings and same host/port/database (encoding-safe).
        pytest.exit(
            "TEST_DATABASE_URL must not equal DATABASE_URL from .env.",
            returncode=1,
        )

    return test_url


TEST_DATABASE_URL = _require_test_database_url()
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
# Prevent lifespan sweep from racing tests that backdate offered_at.
os.environ["NEXO_DISABLE_RIDE_OFFER_EXPIRY_SWEEP"] = "1"

from app.database.base import Base  # noqa: E402
from app.database.database import SessionLocal  # noqa: E402
from app.database.dependencies import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.constants.verification import VerificationStatus  # noqa: E402
from app.models.passenger import Passenger  # noqa: E402
from app.models.driver_wallet import DriverWallet  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.vehicle import Vehicle  # noqa: E402
from app.services.wallet_service import WalletService  # noqa: E402
from app.utils.jwt import create_access_token  # noqa: E402
from app.utils.security import hash_password  # noqa: E402


def _truncate_all(engine: Engine) -> None:
    table_names = ", ".join(
        f'"{table.name}"' for table in Base.metadata.sorted_tables
    )
    if not table_names:
        return
    with engine.begin() as connection:
        connection.execute(
            text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE")
        )


@pytest.fixture(scope="session")
def test_engine() -> Generator[Engine, None, None]:
    engine = create_engine(TEST_DATABASE_URL, poolclass=NullPool)
    Base.metadata.create_all(bind=engine)
    SessionLocal.configure(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def test_session_factory(test_engine: Engine) -> sessionmaker:
    return sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(autouse=True)
def _clean_test_tables(test_engine: Engine) -> Generator[None, None, None]:
    _truncate_all(test_engine)
    yield


@pytest.fixture
def db_session(
    test_session_factory: sessionmaker,
    _clean_test_tables: None,
) -> Generator[Session, None, None]:
    session = test_session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(
        data={
            "sub": str(user.id),
            "email": user.email,
            "role": user.role,
        }
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def passenger_user(db_session: Session) -> User:
    user = User(
        full_name="Test Passenger User",
        phone_number="+15550000001",
        email="passenger.user@test.nexo",
        password=hash_password("TestPassenger123!"),
        role="passenger",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def driver_user(db_session: Session) -> User:
    user = User(
        full_name="Test Driver User",
        phone_number="+15550000002",
        email="driver.user@test.nexo",
        password=hash_password("TestDriver123!"),
        role="driver",
        verification_status="approved",
        availability_status="available",
        current_latitude=-26.2041,
        current_longitude=28.0473,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    WalletService.ensure_wallet(db_session, user.id)
    db_session.commit()
    db_session.expire_all()
    db_session.execute(
        update(DriverWallet)
        .where(DriverWallet.driver_id == user.id)
        .values(available_balance=Decimal("1000.00"))
        .execution_options(synchronize_session="fetch")
    )
    db_session.commit()
    db_session.add(
        Vehicle(
            driver_id=user.id,
            make="Toyota",
            model="Corolla",
            year=2021,
            color="White",
            registration_number="B413FIX",
            vehicle_type="sedan",
            verification_status=VerificationStatus.APPROVED,
        )
    )
    db_session.commit()
    return user


@pytest.fixture
def passenger_profile(db_session: Session, passenger_user: User) -> Passenger:
    profile = Passenger(
        user_id=passenger_user.id,
        first_name="Test",
        last_name="Passenger",
        phone="+15550000003",
        email="passenger.profile@test.nexo",
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)
    return profile


@pytest.fixture
def authenticated_passenger(
    client: TestClient,
    passenger_user: User,
    passenger_profile: Passenger,
) -> dict[str, Any]:
    return {
        "client": client,
        "user": passenger_user,
        "passenger": passenger_profile,
        "headers": _auth_headers(passenger_user),
    }


@pytest.fixture
def authenticated_driver(
    client: TestClient,
    driver_user: User,
) -> dict[str, Any]:
    return {
        "client": client,
        "user": driver_user,
        "headers": _auth_headers(driver_user),
    }


@pytest.fixture
def development_database_url() -> str | None:
    raw = dotenv_values(ENV_FILE).get("DATABASE_URL")
    if not raw:
        return None
    # Same credentials as .env, with password encoding so the smoke check can connect.
    return _normalize_database_url(raw)
