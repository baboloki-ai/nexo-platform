from typing import Dict

from fastapi import WebSocket


class ConnectionManager:
    """
    Manages all active WebSocket connections for NEXO.

    Separate connection pools are maintained for:
    - Drivers
    - Passengers
    """

    def __init__(self):
        self.driver_connections: Dict[int, WebSocket] = {}
        self.passenger_connections: Dict[int, WebSocket] = {}

    # ==========================================================
    # Driver Connections
    # ==========================================================

    async def connect_driver(
        self,
        driver_id: int,
        websocket: WebSocket
    ):
        await websocket.accept()

        self.driver_connections[driver_id] = websocket

        print("\n========== DRIVER CONNECTED ==========")
        print(f"Driver ID      : {driver_id}")
        print(f"Connected      : {list(self.driver_connections.keys())}")
        print("======================================\n")

    def disconnect_driver(
        self,
        driver_id: int
    ):
        self.driver_connections.pop(driver_id, None)

        print("\n========== DRIVER DISCONNECTED ==========")
        print(f"Driver ID      : {driver_id}")
        print(f"Connected      : {list(self.driver_connections.keys())}")
        print("=========================================\n")

    async def send_to_driver(
        self,
        driver_id: int,
        message: dict
    ):
        print("\n========== DRIVER MESSAGE ==========")
        print(f"Target Driver  : {driver_id}")
        print(f"Payload        : {message}")
        print(f"Connected      : {list(self.driver_connections.keys())}")
        print(f"Manager ID    : {id(self)}")
        websocket = self.driver_connections.get(driver_id)

        if websocket is None:
            print("❌ Driver is NOT connected.")
            print("====================================\n")
            return

        try:
            print("📤 Sending JSON to driver...")
            await websocket.send_json(message)
            print(f"✅ Message successfully sent to Driver {driver_id}")
            print("====================================\n")

        except Exception as e:
            print(f"❌ Failed sending to Driver {driver_id}")
            print(f"Exception      : {repr(e)}")
            print("Removing stale WebSocket connection...")
            self.disconnect_driver(driver_id)

    # ==========================================================
    # Passenger Connections
    # ==========================================================

    async def connect_passenger(
        self,
        passenger_id: int,
        websocket: WebSocket
    ):
        await websocket.accept()
        print(f"Manager ID: {id(self)}")
        self.passenger_connections[passenger_id] = websocket

        print("\n========== PASSENGER CONNECTED ==========")
        print(f"Passenger ID   : {passenger_id}")
        print(f"Connected      : {list(self.passenger_connections.keys())}")
        print("=========================================\n")

    def disconnect_passenger(
        self,
        passenger_id: int
    ):
        self.passenger_connections.pop(passenger_id, None)

        print("\n======= PASSENGER DISCONNECTED =======")
        print(f"Passenger ID   : {passenger_id}")
        print(f"Connected      : {list(self.passenger_connections.keys())}")
        print("======================================\n")

    async def send_to_passenger(
        self,
        passenger_id: int,
        message: dict
    ):
        print("\n========== PASSENGER MESSAGE ==========")
        print(f"Target Passenger : {passenger_id}")
        print(f"Payload          : {message}")
        print(f"Connected        : {list(self.passenger_connections.keys())}")

        websocket = self.passenger_connections.get(passenger_id)

        if websocket is None:
            print("❌ Passenger is NOT connected.")
            print("=======================================\n")
            return

        try:
            print("📤 Sending JSON to passenger...")
            await websocket.send_json(message)
            print(f"✅ Message successfully sent to Passenger {passenger_id}")
            print("=======================================\n")

        except Exception as e:
            print(f"❌ Failed sending to Passenger {passenger_id}")
            print(f"Exception        : {repr(e)}")
            print("Removing stale WebSocket connection...")
            self.disconnect_passenger(passenger_id)


manager = ConnectionManager()