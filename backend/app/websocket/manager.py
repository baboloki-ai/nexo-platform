from fastapi import WebSocket


class ConnectionManager:
    """
    Manages all active WebSocket connections.

    We keep separate connections for:
    - Drivers
    - Passengers
    """

    def __init__(self):
        self.driver_connections: dict[int, WebSocket] = {}
        self.passenger_connections: dict[int, WebSocket] = {}

    # -----------------------------
    # Driver Connections
    # -----------------------------

    async def connect_driver(
        self,
        driver_id: int,
        websocket: WebSocket
    ):
        await websocket.accept()
        self.driver_connections[driver_id] = websocket

    def disconnect_driver(
        self,
        driver_id: int
    ):
        self.driver_connections.pop(driver_id, None)

    async def send_to_driver(
        self,
        driver_id: int,
        message: dict
    ):
        websocket = self.driver_connections.get(driver_id)

        if websocket:
            await websocket.send_json(message)

    # -----------------------------
    # Passenger Connections
    # -----------------------------

    async def connect_passenger(
        self,
        passenger_id: int,
        websocket: WebSocket
    ):
        await websocket.accept()
        self.passenger_connections[passenger_id] = websocket

    def disconnect_passenger(
        self,
        passenger_id: int
    ):
        self.passenger_connections.pop(passenger_id, None)

    async def send_to_passenger(
        self,
        passenger_id: int,
        message: dict
    ):
        websocket = self.passenger_connections.get(passenger_id)

        if websocket:
            await websocket.send_json(message)


manager = ConnectionManager()