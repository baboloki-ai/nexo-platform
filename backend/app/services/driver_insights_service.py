from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.constants.ride_status import RideStatus
from app.constants.verification import VerificationStatus
from app.models.driver_response import DriverResponse
from app.models.ride_request import RideRequest
from app.models.user import User
from app.services.marketplace_service import MarketplaceService
from app.services.wallet_service import WalletService
from app.utils.money import MIN_DRIVER_WALLET, money_float, quantize_pula

GABORONE_TZ = ZoneInfo("Africa/Gaborone")
DEMAND_WINDOW_MINUTES = 60
# ~1.1 km cells around Gaborone.
DEMAND_CELL_DEGREES = Decimal("0.01")


class DriverInsightsService:
    @staticmethod
    def list_open_requests(db: Session, current_user: User) -> list[dict]:
        if current_user.role != "driver":
            return []
        rides = (
            db.query(RideRequest)
            .filter(
                RideRequest.status == RideStatus.PENDING,
                RideRequest.accepted_driver_id.is_(None),
                RideRequest.agreed_fare.is_(None),
            )
            .order_by(RideRequest.requested_at.desc())
            .all()
        )
        my_responses = {
            row.ride_id: row
            for row in db.query(DriverResponse)
            .filter(DriverResponse.driver_id == current_user.id)
            .all()
        }
        payload = []
        for ride in rides:
            pickup_distance_km, pickup_eta_seconds = (
                MarketplaceService._pickup_decision_support(ride, current_user)
            )
            response = my_responses.get(ride.id)
            payload.append(
                {
                    "ride_id": ride.id,
                    "pickup_location": ride.pickup_location,
                    "pickup_latitude": ride.pickup_latitude,
                    "pickup_longitude": ride.pickup_longitude,
                    "destination": ride.destination,
                    "destination_latitude": ride.destination_latitude,
                    "destination_longitude": ride.destination_longitude,
                    "passenger_current_offer": money_float(
                        ride.passenger_current_offer
                    ),
                    "passenger_offer_version": ride.passenger_offer_version,
                    "trip_distance_km": money_float(ride.trip_distance_km),
                    "pickup_distance_km": money_float(pickup_distance_km),
                    "pickup_eta_seconds": pickup_eta_seconds,
                    "requested_at": ride.requested_at,
                    "cash": True,
                    "my_response": (
                        MarketplaceService.serialize_driver_response(
                            db,
                            response,
                            include_driver=False,
                        ).model_dump(mode="json")
                        if response is not None
                        else None
                    ),
                }
            )
        return payload

    @staticmethod
    def performance(db: Session, current_user: User) -> dict:
        wallet = WalletService.ensure_wallet(db, current_user.id)
        completed = (
            db.query(RideRequest)
            .filter(
                RideRequest.accepted_driver_id == current_user.id,
                RideRequest.status == RideStatus.COMPLETED,
            )
            .all()
        )
        now = datetime.now(GABORONE_TZ)
        start_of_today = datetime(
            now.year, now.month, now.day, tzinfo=GABORONE_TZ
        ).astimezone(timezone.utc).replace(tzinfo=None)

        today_rides = [
            ride
            for ride in completed
            if ride.completed_at is not None and ride.completed_at >= start_of_today
        ]
        today_gross = quantize_pula(
            sum((quantize_pula(ride.agreed_fare or 0) for ride in today_rides), Decimal("0"))
        )
        today_ids = [ride.id for ride in today_rides]
        today_commission_signed = WalletService.commission_total_for_rides(
            db,
            current_user.id,
            today_ids,
        )
        today_commission = quantize_pula(abs(today_commission_signed))
        return {
            "completed_rides": len(completed),
            "today_gross": money_float(today_gross),
            "today_commission": money_float(today_commission),
            "today_net": money_float(today_gross - today_commission),
            "wallet_balance": money_float(wallet.available_balance),
            "wallet_minimum": money_float(MIN_DRIVER_WALLET),
            "meets_wallet_minimum": WalletService.meets_minimum(
                wallet.available_balance
            ),
            "commission_rate": 0.08,
        }

    @staticmethod
    def demand(db: Session, current_user: User) -> dict:
        since = datetime.utcnow() - timedelta(minutes=DEMAND_WINDOW_MINUTES)
        rides = (
            db.query(RideRequest)
            .filter(
                RideRequest.pickup_latitude.isnot(None),
                RideRequest.pickup_longitude.isnot(None),
                RideRequest.requested_at >= since,
            )
            .all()
        )
        cells: dict[tuple[str, str], dict] = {}
        for ride in rides:
            lat = Decimal(str(ride.pickup_latitude))
            lng = Decimal(str(ride.pickup_longitude))
            cell_lat = (lat / DEMAND_CELL_DEGREES).to_integral_value() * DEMAND_CELL_DEGREES
            cell_lng = (lng / DEMAND_CELL_DEGREES).to_integral_value() * DEMAND_CELL_DEGREES
            key = (str(cell_lat), str(cell_lng))
            cell = cells.setdefault(
                key,
                {
                    "latitude": float(cell_lat),
                    "longitude": float(cell_lng),
                    "count": 0,
                },
            )
            cell["count"] += 1

        drivers = (
            db.query(User)
            .filter(
                User.role == "driver",
                User.availability_status == "available",
                User.verification_status == VerificationStatus.APPROVED,
                User.current_latitude.isnot(None),
                User.current_longitude.isnot(None),
            )
            .all()
        )
        return {
            "window_minutes": DEMAND_WINDOW_MINUTES,
            "cells": list(cells.values()),
            "online_drivers": [
                {
                    "driver_id": driver.id,
                    "latitude": driver.current_latitude,
                    "longitude": driver.current_longitude,
                    "last_seen": driver.last_seen,
                    "self": driver.id == current_user.id,
                }
                for driver in drivers
            ],
        }
