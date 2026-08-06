import asyncio
from collections.abc import Coroutine
from typing import Any, Literal

from app.websocket.manager import manager

Recipient = Literal["driver", "passenger"]


class NotificationService:
    """
    Handles all outbound real-time notifications.

    This service is the ONLY layer allowed to communicate with the
    ConnectionManager.

    DispatchService, RideService, GPSService, etc. should call this service only.
    """

    _event_loop: asyncio.AbstractEventLoop | None = None

    @classmethod
    def bind_event_loop(
        cls,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        cls._event_loop = loop

        print("\n========== NOTIFICATION ==========")
        print("✅ Event loop bound.")
        print("==================================\n")

    @classmethod
    def _schedule(
        cls,
        coro: Coroutine[Any, Any, None],
    ) -> None:

        print("\n========== NOTIFICATION ==========")
        print("Scheduling notification...")

        try:
            loop = asyncio.get_running_loop()

            print("✅ Running event loop found.")
            loop.create_task(coro)

            print("✅ Coroutine scheduled.")
            print("==================================\n")
            return

        except RuntimeError:
            print("⚠ No running event loop.")

        if cls._event_loop is not None:

            print("Using stored event loop...")

            if cls._event_loop.is_running():

                asyncio.run_coroutine_threadsafe(
                    coro,
                    cls._event_loop,
                )

                print("✅ Coroutine submitted.")
                print("==================================\n")
                return

            print("❌ Stored event loop is NOT running.")

        print("❌ Notification skipped.")
        print("==================================\n")

    @staticmethod
    async def _send(
        recipient: Recipient,
        entity_id: int,
        message: dict,
    ) -> None:

        print("\n========== NOTIFICATION ==========")
        print("Executing _send()")
        print(f"Recipient : {recipient}")
        print(f"Entity ID : {entity_id}")
        print(f"Payload   : {message}")

        if recipient == "driver":

            print("➡ Sending to driver...")

            await manager.send_to_driver(
                entity_id,
                message,
            )

            print("✅ Driver send completed.")
            print("==================================\n")
            return

        print("➡ Sending to passenger...")

        await manager.send_to_passenger(
            entity_id,
            message,
        )

        print("✅ Passenger send completed.")
        print("==================================\n")

    @staticmethod
    def send_ride_offer(
        driver_id: int,
        ride_id: int,
        pickup: str,
        destination: str,
        fare: float,
    ) -> None:

        print("\n========== RIDE OFFER ==========")
        print("Preparing ride offer...")
        print(f"Driver      : {driver_id}")
        print(f"Ride        : {ride_id}")
        print(f"Pickup      : {pickup}")
        print(f"Destination : {destination}")
        print(f"Fare        : {fare}")
        print("================================\n")

        NotificationService._schedule(
            NotificationService._send(
                "driver",
                driver_id,
                {
                    "event": "ride_offer",
                    "ride_id": ride_id,
                    "pickup": pickup,
                    "destination": destination,
                    "fare": fare,
                },
            )
        )

    @staticmethod
    def notify_driver(
        driver_id: int,
        message: str,
    ) -> None:

        print(f"Driver notification -> {driver_id}")

        NotificationService._schedule(
            NotificationService._send(
                "driver",
                driver_id,
                {
                    "event": "notification",
                    "message": message,
                },
            )
        )

    @staticmethod
    def notify_passenger(
        passenger_id: int,
        message: str,
    ) -> None:

        print(f"Passenger notification -> {passenger_id}")

        NotificationService._schedule(
            NotificationService._send(
                "passenger",
                passenger_id,
                {
                    "event": "notification",
                    "message": message,
                },
            )
        )

    @staticmethod
    def send_driver_location(
        passenger_id: int,
        driver_id: int,
        latitude: float,
        longitude: float,
    ) -> None:
        """
        Sends the driver's live GPS coordinates to the passenger.
        """

        print("\n========== DRIVER LOCATION ==========")
        print(f"Passenger : {passenger_id}")
        print(f"Driver    : {driver_id}")
        print(f"Latitude  : {latitude}")
        print(f"Longitude : {longitude}")
        print("=====================================\n")

        NotificationService._schedule(
            NotificationService._send(
                "passenger",
                passenger_id,
                {
                    "event": "driver_location",
                    "driver_id": driver_id,
                    "latitude": latitude,
                    "longitude": longitude,
                },
            )
        )