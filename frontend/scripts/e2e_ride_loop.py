"""C0 smoke: one ride through the Vite proxy (HTTP + WebSocket)."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

try:
    import websocket
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Install websocket-client: pip install websocket-client") from exc

ORIGIN = "http://localhost:5173"
WS_ORIGIN = "ws://localhost:5173"
STAMP = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def request(method: str, path: str, token: str | None = None, data=None, form=False):
    headers = {}
    body = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if form:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        body = data.encode()
    elif data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode()
    req = urllib.request.Request(ORIGIN + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as err:
        raw = err.read().decode()
        raise RuntimeError(f"{method} {path} -> {err.code} {raw}") from err


def login(email: str, password: str) -> str:
    status, payload = request(
        "POST",
        "/users/login",
        form=True,
        data=f"username={email}&password={password}",
    )
    assert status == 200, payload
    return payload["access_token"]


def wait_event(ws, name: str, timeout: float = 8.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        remaining = max(0.1, deadline - time.time())
        ws.settimeout(remaining)
        raw = ws.recv()
        payload = json.loads(raw)
        if payload.get("event") == name:
            return payload
    raise TimeoutError(f"Did not receive {name}")


def approve_driver(driver_id: int) -> None:
    """Controlled local approval — not a public self-approve API."""
    import os
    from pathlib import Path

    from dotenv import dotenv_values

    backend_env = Path(__file__).resolve().parents[2] / "backend" / ".env"
    secret = (
        os.getenv("NEXO_INTERNAL_VERIFY_SECRET")
        or dotenv_values(backend_env).get("NEXO_INTERNAL_VERIFY_SECRET")
        or ""
    ).strip()
    if secret:
        headers = {
            "Content-Type": "application/json",
            "X-NEXO-INTERNAL-SECRET": secret,
        }
        body = json.dumps({"status": "approved"}).encode()
        req = urllib.request.Request(
            f"{ORIGIN}/internal/drivers/{driver_id}/verification",
            data=body,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode())
        assert payload["verification_status"] == "approved"
        print("driver approved via internal secret")
        return

    sys_path_setup()
    from sqlalchemy import create_engine, text

    engine = create_engine(os.environ["DATABASE_URL"])
    try:
        with engine.begin() as connection:
            result = connection.execute(
                text(
                    "UPDATE users SET verification_status = 'approved' "
                    "WHERE id = :id AND role = 'driver'"
                ),
                {"id": driver_id},
            )
            if result.rowcount != 1:
                raise RuntimeError(f"Could not approve driver {driver_id}")
    finally:
        engine.dispose()
    print("driver approved via local database")


def sys_path_setup() -> None:
    import os
    from pathlib import Path
    from urllib.parse import unquote

    from dotenv import dotenv_values
    from sqlalchemy.engine import URL

    backend_root = Path(__file__).resolve().parents[2] / "backend"
    values = dotenv_values(backend_root / ".env")
    raw = values.get("DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not raw:
        raise SystemExit("DATABASE_URL is not set; cannot approve driver.")
    drivername, remainder = raw.split("://", 1)
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
    os.environ["DATABASE_URL"] = URL.create(
        drivername=drivername,
        username=username,
        password=unquote(password),
        host=host,
        port=port,
        database=database,
    ).render_as_string(hide_password=False)


def main() -> None:
    passenger_email = f"c0.pass.{STAMP}@example.com"
    driver_email = f"c0.drv.{STAMP}@example.com"
    password = "C0DemoPass123!"

    request(
        "POST",
        "/users/",
        data={
            "full_name": "C0 Passenger",
            "phone_number": f"+26771{STAMP[-6:]}",
            "email": passenger_email,
            "password": password,
            "role": "passenger",
        },
    )
    _, driver_create = request(
        "POST",
        "/users/",
        data={
            "full_name": "C0 Driver",
            "phone_number": f"+26772{STAMP[-6:]}",
            "email": driver_email,
            "password": password,
            "role": "driver",
        },
    )
    assert driver_create["verification_status"] == "pending"

    passenger_token = login(passenger_email, password)
    driver_token = login(driver_email, password)

    _, passenger_me = request("GET", "/users/me", token=passenger_token)
    _, driver_me = request("GET", "/users/me", token=driver_token)
    assert passenger_me["role"] == "passenger"
    assert driver_me["role"] == "driver"

    blocked = None
    try:
        request("PUT", "/drivers/go-online", token=driver_token)
    except RuntimeError as err:
        blocked = str(err)
    assert blocked and "403" in blocked, blocked
    print("pending driver cannot go online")

    approve_driver(driver_me["id"])


    _, profile = request(
        "POST",
        "/passengers/",
        token=passenger_token,
        data={
            "first_name": "C0",
            "last_name": "Passenger",
            "phone": f"+26771{STAMP[-6:]}",
            "email": passenger_email,
        },
    )
    passenger_id = profile["id"]
    driver_id = driver_me["id"]

    request(
        "POST",
        "/vehicles/",
        token=driver_token,
        data={
            "make": "Toyota",
            "model": "Corolla",
            "year": 2021,
            "color": "White",
            "registration_number": f"C0{STAMP[-6:]}",
            "vehicle_type": "sedan",
        },
    )

    driver_ws = websocket.create_connection(
        f"{WS_ORIGIN}/ws/driver/{driver_id}?token={driver_token}",
        timeout=8,
    )
    passenger_ws = websocket.create_connection(
        f"{WS_ORIGIN}/ws/passenger/{passenger_id}?token={passenger_token}",
        timeout=8,
    )
    wait_event(driver_ws, "connected")
    wait_event(passenger_ws, "connected")

    request(
        "PUT",
        "/drivers/location",
        token=driver_token,
        data={"latitude": -24.6550, "longitude": 25.9090},
    )
    request("PUT", "/drivers/go-online", token=driver_token)

    _, ride = request(
        "POST",
        "/rides/",
        token=passenger_token,
        data={
            "pickup_location": "Main Mall, Gaborone",
            "pickup_latitude": -24.6545,
            "pickup_longitude": 25.9086,
            "destination": "Airport Junction, Gaborone",
            "destination_latitude": -24.6278,
            "destination_longitude": 25.9059,
            "proposed_fare": 150,
        },
    )
    ride_id = ride["id"]
    print("created ride", ride_id, ride["status"])
    assert ride["status"] == "pending"
    assert ride["agreed_fare"] is None

    created_event = wait_event(driver_ws, "marketplace_request_created")
    assert created_event["ride_id"] == ride_id
    print("driver received marketplace_request_created")

    _, responded = request(
        "PUT",
        f"/rides/{ride_id}/respond",
        token=driver_token,
        data={"response_type": "accept_passenger_offer"},
    )
    assert responded["status"] == "pending"
    assert responded["accepted_driver_id"] is None
    print("driver accepted passenger offer (response only)")

    received = wait_event(passenger_ws, "driver_response_received")
    assert received["ride_id"] == ride_id
    print("passenger received driver_response_received")

    _, responses = request(
        "GET",
        f"/rides/{ride_id}/responses",
        token=passenger_token,
    )
    assert len(responses) == 1
    response_id = responses[0]["id"]

    _, selected = request(
        "PUT",
        f"/rides/{ride_id}/select",
        token=passenger_token,
        data={"response_id": response_id},
    )
    assert selected["status"] == "accepted"
    assert selected["accepted_driver_id"] == driver_id
    assert selected["agreed_fare"] == 150
    identity = selected.get("assigned_driver") or {}
    assert identity.get("display_name") == "C0 Driver"
    assert identity.get("verification_status") == "approved"
    assert identity.get("vehicle", {}).get("registration_number", "").startswith("C0")
    assert "phone_number" not in identity
    agreed_event = wait_event(passenger_ws, "ride_agreed")
    assert agreed_event["driver_id"] == driver_id
    assert agreed_event["agreed_fare"] == 150
    print("passenger selected driver; agreed fare locked")

    for path, expected in (
        ("arrive", "driver_arriving"),
        ("driver-arrived", "driver_arrived"),
        ("start", "in_progress"),
    ):
        _, updated = request("PUT", f"/rides/{ride_id}/{path}", token=driver_token)
        assert updated["status"] == expected, updated
        print("lifecycle", path, updated["status"])

    request(
        "PUT",
        "/drivers/location",
        token=driver_token,
        data={"latitude": -24.6553, "longitude": 25.9093},
    )
    location_event = wait_event(passenger_ws, "driver_location")
    assert location_event["driver_id"] == driver_id
    print("passenger received driver_location")

    _, completed = request("PUT", f"/rides/{ride_id}/complete", token=driver_token)
    assert completed["status"] == "completed"
    assert completed["agreed_fare"] == 150
    print("lifecycle complete", completed["status"])

    _, wallet = request("GET", "/drivers/wallet", token=driver_token)
    # Launch seed P40 minus 8% of P150 = P12.00 → P28.00
    assert abs(wallet["available_balance"] - 28.0) < 0.001
    print("wallet after 8% commission", wallet["available_balance"])

    _, trip = request("GET", f"/trips/{ride_id}", token=passenger_token)
    assert trip["status"] == "completed"
    assert trip["assigned_driver"]["display_name"] == "C0 Driver"
    _, history = request("GET", "/rides/my", token=passenger_token)
    assert any(item["id"] == ride_id and item["status"] == "completed" for item in history)
    print("passenger history contains completed ride")

    _, driver_history = request("GET", "/drivers/rides", token=driver_token)
    assert any(
        item["id"] == ride_id and item["status"] == "completed"
        for item in driver_history
    )
    print("driver history contains completed ride")

    driver_ws.close()
    passenger_ws.close()
    print("L3 MARKETPLACE PROXY LOOP OK")


if __name__ == "__main__":
    main()
