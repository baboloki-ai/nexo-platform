from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.database.dependencies import get_db
from app.websocket.auth import (
    authenticate_driver_socket,
    authenticate_passenger_socket,
    reject_websocket,
)
from app.websocket.manager import manager

router = APIRouter(
    tags=["WebSockets"]
)


# ==========================================================
# Driver WebSocket
# ==========================================================

@router.websocket("/ws/driver/{driver_id}")
async def driver_socket(
    websocket: WebSocket,
    driver_id: int,
    db: Session = Depends(get_db),
):
    user = authenticate_driver_socket(websocket, db, driver_id)
    if user is None:
        await reject_websocket(websocket)
        return

    await manager.connect_driver(
        driver_id,
        websocket
    )

    await manager.send_to_driver(
        driver_id,
        {
            "event": "connected",
            "message": "Driver connected successfully."
        }
    )

    try:
        while True:
            data = await websocket.receive_text()

            print(
                f"📨 Driver {driver_id}: {data}"
            )

    except WebSocketDisconnect:

        manager.disconnect_driver(driver_id, websocket)


# ==========================================================
# Passenger WebSocket
# ==========================================================

@router.websocket("/ws/passenger/{passenger_id}")
async def passenger_socket(
    websocket: WebSocket,
    passenger_id: int,
    db: Session = Depends(get_db),
):
    user = authenticate_passenger_socket(websocket, db, passenger_id)
    if user is None:
        await reject_websocket(websocket)
        return

    await manager.connect_passenger(
        passenger_id,
        websocket
    )

    await manager.send_to_passenger(
        passenger_id,
        {
            "event": "connected",
            "message": "Passenger connected successfully."
        }
    )

    try:
        while True:
            data = await websocket.receive_text()

            print(
                f"📨 Passenger {passenger_id}: {data}"
            )

    except WebSocketDisconnect:

        manager.disconnect_passenger(passenger_id, websocket)
