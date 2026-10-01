import asyncio
from collections.abc import Coroutine
from typing import Any, Literal

from app.websocket.manager import manager


Recipient = Literal["driver", "passenger"]


class NotificationService:
    """
    Handles all outbound real-time notifications.

    This service is the ONLY layer allowed to communicate
    with the ConnectionManager.

    DispatchService, RideService, GPSService, etc.
    should call this service only.
    """

    _event_loop: asyncio.AbstractEventLoop | None = None

    # ==========================================================
    # EVENT LOOP
    # ==========================================================

    @classmethod
    def bind_event_loop(
        cls,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        cls._event_loop = loop

        print("\n========== NOTIFICATION ==========")
        print("✅ Event loop bound.")
        print("==================================\n")

    # ==========================================================
    # SCHEDULE NOTIFICATION
    # ==========================================================

    @classmethod
    def _schedule(
        cls,
        coro: Coroutine[Any, Any, None],
    ) -> None:

        print("\n========== NOTIFICATION ==========")
        print("Scheduling notification...")

        scheduled = False
        try:
            try:
                loop = asyncio.get_running_loop()

                print("✅ Running event loop found.")

                loop.create_task(coro)
                scheduled = True

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
                    scheduled = True

                    print("✅ Coroutine submitted.")
                    print("==================================\n")

                    return

                print("❌ Stored event loop is NOT running.")

            print("❌ Notification skipped.")
            print("==================================\n")
        finally:
            if not scheduled:
                coro.close()

    # ==========================================================
    # SEND NOTIFICATION
    # ==========================================================

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

    # ==========================================================
    # RIDE OFFER
    # ==========================================================

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

    # ==========================================================
    # DRIVER NOTIFICATION
    # ==========================================================

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

    # ==========================================================
    # PASSENGER NOTIFICATION
    # ==========================================================

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

    # ==========================================================
    # DRIVER LIVE LOCATION
    # ==========================================================

    @staticmethod
    def send_driver_location(
        passenger_id: int,
        driver_id: int,
        latitude: float,
        longitude: float,
    ) -> None:
        """
        Sends the driver's live GPS coordinates
        to the passenger.
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

    # ==========================================================
    # RIDE ACCEPTED
    # ==========================================================

    @staticmethod
    def notify_ride_accepted(
        passenger_id: int,
        ride_id: int,
        driver_id: int,
    ) -> None:
        """
        Notifies the passenger that a driver
        has accepted the ride.
        """

        print("\n========== RIDE ACCEPTED ==========")
        print(f"Passenger : {passenger_id}")
        print(f"Ride      : {ride_id}")
        print(f"Driver    : {driver_id}")
        print("===================================\n")

        NotificationService._schedule(
            NotificationService._send(
                "passenger",
                passenger_id,
                {
                    "event": "ride_accepted",
                    "ride_id": ride_id,
                    "driver_id": driver_id,
                    "message": "Your driver has accepted the ride.",
                },
            )
        )

    # ==========================================================
    # NO DRIVER AVAILABLE
    # ==========================================================

    @staticmethod
    def notify_no_driver_available(
        passenger_id: int,
        ride_id: int,
    ) -> None:
        """
        Notifies the passenger that dispatch exhausted the eligible
        driver pool and the ride was terminalized.
        """

        print("\n========== NO DRIVER AVAILABLE ==========")
        print(f"Passenger : {passenger_id}")
        print(f"Ride      : {ride_id}")
        print("=========================================\n")

        NotificationService._schedule(
            NotificationService._send(
                "passenger",
                passenger_id,
                {
                    "event": "no_driver_available",
                    "ride_id": ride_id,
                    "message": "No drivers are available for your ride.",
                },
            )
        )

    # ==========================================================
    # L3 MARKETPLACE EVENTS
    # ==========================================================

    @staticmethod
    def notify_marketplace_request_created(
        driver_id: int,
        ride_id: int,
        event_id: str,
        passenger_offer_version: int,
        passenger_current_offer: float | None,
        pickup: str,
        destination: str,
        trip_distance_km: float | None,
        pickup_distance_km: float | None,
        pickup_eta_seconds: int | None,
    ) -> None:
        NotificationService._schedule(
            NotificationService._send(
                "driver",
                driver_id,
                {
                    "event": "marketplace_request_created",
                    "event_id": event_id,
                    "ride_id": ride_id,
                    "passenger_offer_version": passenger_offer_version,
                    "passenger_current_offer": passenger_current_offer,
                    "pickup": pickup,
                    "destination": destination,
                    "trip_distance_km": trip_distance_km,
                    "pickup_distance_km": pickup_distance_km,
                    "pickup_eta_seconds": pickup_eta_seconds,
                },
            )
        )
        try:
            from app.services.push_notification_service import (
                PushNotificationService,
            )

            PushNotificationService.send_ride_request(
                driver_id=driver_id,
                ride_id=ride_id,
            )
        except Exception as exc:
            print(f"⚠️ Ride-request push failed: {exc}")

    @staticmethod
    def notify_passenger_offer_updated(
        driver_id: int,
        ride_id: int,
        event_id: str,
        passenger_offer_version: int,
        passenger_current_offer: float | None,
        action: str,
    ) -> None:
        NotificationService._schedule(
            NotificationService._send(
                "driver",
                driver_id,
                {
                    "event": "passenger_offer_updated",
                    "event_id": event_id,
                    "ride_id": ride_id,
                    "passenger_offer_version": passenger_offer_version,
                    "passenger_current_offer": passenger_current_offer,
                    "action": action,
                },
            )
        )

    @staticmethod
    def notify_driver_response_received(
        passenger_id: int,
        ride_id: int,
        event_id: str,
        passenger_offer_version: int,
        response_id: int,
        driver_id: int,
        response_type: str,
        amount: float | None,
        pickup_distance_km: float | None,
        pickup_eta_seconds: int | None,
        driver_identity: Any,
    ) -> None:
        identity = None
        if driver_identity is not None:
            identity = (
                driver_identity.model_dump()
                if hasattr(driver_identity, "model_dump")
                else driver_identity
            )
        NotificationService._schedule(
            NotificationService._send(
                "passenger",
                passenger_id,
                {
                    "event": "driver_response_received",
                    "event_id": event_id,
                    "ride_id": ride_id,
                    "passenger_offer_version": passenger_offer_version,
                    "response_id": response_id,
                    "driver_id": driver_id,
                    "response_type": response_type,
                    "amount": amount,
                    "pickup_distance_km": pickup_distance_km,
                    "pickup_eta_seconds": pickup_eta_seconds,
                    "driver": identity,
                },
            )
        )

    @staticmethod
    def notify_driver_response_withdrawn(
        passenger_id: int,
        driver_id: int,
        ride_id: int,
        event_id: str,
        response_id: int | None,
        passenger_offer_version: int,
    ) -> None:
        payload = {
            "event": "driver_response_withdrawn",
            "event_id": event_id,
            "ride_id": ride_id,
            "passenger_offer_version": passenger_offer_version,
            "response_id": response_id,
            "driver_id": driver_id,
        }
        NotificationService._schedule(
            NotificationService._send("passenger", passenger_id, payload)
        )
        NotificationService._schedule(
            NotificationService._send("driver", driver_id, payload)
        )

    @staticmethod
    def notify_driver_response_expired(
        passenger_id: int,
        driver_id: int,
        ride_id: int,
        event_id: str,
        response_id: int,
        passenger_offer_version: int,
    ) -> None:
        payload = {
            "event": "driver_response_expired",
            "event_id": event_id,
            "ride_id": ride_id,
            "passenger_offer_version": passenger_offer_version,
            "response_id": response_id,
            "driver_id": driver_id,
        }
        NotificationService._schedule(
            NotificationService._send("passenger", passenger_id, payload)
        )
        NotificationService._schedule(
            NotificationService._send("driver", driver_id, payload)
        )

    @staticmethod
    def notify_ride_agreed(
        passenger_id: int,
        ride_id: int,
        event_id: str,
        passenger_offer_version: int,
        driver_id: int | None,
        agreed_fare: float | None,
        response_id: int,
    ) -> None:
        NotificationService._schedule(
            NotificationService._send(
                "passenger",
                passenger_id,
                {
                    "event": "ride_agreed",
                    "event_id": event_id,
                    "ride_id": ride_id,
                    "passenger_offer_version": passenger_offer_version,
                    "driver_id": driver_id,
                    "agreed_fare": agreed_fare,
                    "response_id": response_id,
                },
            )
        )

    @staticmethod
    def notify_payment_updated(
        passenger_id: int,
        driver_id: int | None,
        ride_id: int,
        payment_id: int,
        status: str,
    ) -> None:
        payload = {
            "event": "payment_updated",
            "ride_id": ride_id,
            "payment_id": payment_id,
            "status": status,
        }
        NotificationService._schedule(
            NotificationService._send("passenger", passenger_id, payload)
        )
        if driver_id is not None:
            NotificationService._schedule(
                NotificationService._send("driver", driver_id, payload)
            )

    @staticmethod
    def notify_marketplace_request_closed(
        driver_id: int,
        ride_id: int,
        event_id: str,
        reason: str,
        won: bool,
        agreed_fare: float | None,
        selected_driver_id: int | None,
    ) -> None:
        NotificationService._schedule(
            NotificationService._send(
                "driver",
                driver_id,
                {
                    "event": "marketplace_request_closed",
                    "event_id": event_id,
                    "ride_id": ride_id,
                    "reason": reason,
                    "won": won,
                    "agreed_fare": agreed_fare,
                    "selected_driver_id": selected_driver_id,
                },
            )
        )