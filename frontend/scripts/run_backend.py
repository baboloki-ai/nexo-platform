"""Start the existing backend for local C0 development.

Pytest already re-encodes DATABASE_URL when the password contains '@'.
The live app does not. This launcher applies the same encoding, then
imports models before app.main to avoid a circular import on Windows.
It does not change backend production code.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import unquote

from dotenv import dotenv_values
from sqlalchemy.engine import URL

BACKEND_ROOT = Path(__file__).resolve().parents[2] / "backend"
ENV_FILE = BACKEND_ROOT / ".env"


def parse_database_url(url: str) -> tuple[str, str, str, str, int | None, str]:
    drivername, remainder = url.split("://", 1)
    userinfo, host_and_path = remainder.rsplit("@", 1)
    username, separator, password = userinfo.partition(":")
    if not separator:
        password = ""
    host_port, _, path = host_and_path.partition("/")
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


def encode_database_url(url: str) -> str:
    drivername, username, password, host, port, database = parse_database_url(url)
    return URL.create(
        drivername=drivername,
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
    ).render_as_string(hide_password=False)


def main() -> None:
    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    values = dotenv_values(ENV_FILE)
    raw = values.get("DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not raw:
        raise SystemExit("DATABASE_URL is not set.")
    os.environ["DATABASE_URL"] = encode_database_url(raw)
    sys.path.insert(0, str(BACKEND_ROOT))
    os.chdir(BACKEND_ROOT)

    from app.database.base import Base  # noqa: F401
    from app.main import app
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
