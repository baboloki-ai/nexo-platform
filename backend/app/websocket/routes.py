from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.websocket.manager import manager

router = APIRouter(
    tags=["WebSockets"]
)


@router.websocket("/ws/driver/{driver_id}")
async def driver_socket(
    websocket: WebSocket,
    driver_id: int
):
    await manager.connect_driver(
        driver_id,
        websocket
    )

    try:
        while True:
            # Keep the connection alive
            await websocket.receive_text()

    except WebSocketDisconnect:
        manager.disconnect_driver(driver_id)


@router.websocket("/ws/passenger/{passenger_id}")
async def passenger_socket(
    websocket: WebSocket,
    passenger_id: int
):
    await manager.connect_passenger(
        passenger_id,
        websocket
    )

    try:
        while True:
            # Keep the connection alive
            await websocket.receive_text()

    except WebSocketDisconnect:
        manager.disconnect_passenger(passenger_id)