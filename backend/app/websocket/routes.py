from fastapi import APIRouter, WebSocket, WebSocketDisconnect

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
    driver_id: int
):
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

        manager.disconnect_driver(driver_id)


# ==========================================================
# Passenger WebSocket
# ==========================================================

@router.websocket("/ws/passenger/{passenger_id}")
async def passenger_socket(
    websocket: WebSocket,
    passenger_id: int
):
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

        manager.disconnect_passenger(passenger_id)