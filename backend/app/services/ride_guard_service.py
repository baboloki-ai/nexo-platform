import json
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.constants.ride_guard import (
    RideGuardEventType,
    RideGuardSeverity,
    RideGuardStatus,
)
from app.models.ride_guard_event import RideGuardEvent


class RideGuardService:
    """
    Records and manages RideGuard safety events.
    Detection rules are kept outside this persistence layer.
    """

    @staticmethod
    def record_event(
        db: Session,
        ride_id: int,
        event_type: str,
        severity: str,
        driver_id: int | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        speed_kmh: float | None = None,
        accuracy_meters: float | None = None,
        heading_degrees: float | None = None,
        message: str | None = None,
        metadata: dict | None = None,
        status: str = RideGuardStatus.OPEN,
    ) -> RideGuardEvent:
        event = RideGuardEvent(
            ride_id=ride_id,
            driver_id=driver_id,
            event_type=event_type,
            severity=severity,
            status=status,
            latitude=latitude,
            longitude=longitude,
            speed_kmh=speed_kmh,
            accuracy_meters=accuracy_meters,
            heading_degrees=heading_degrees,
            message=message,
            metadata_json=json.dumps(metadata) if metadata is not None else None,
        )

        db.add(event)
        db.flush()

        return event

    @staticmethod
    def record_gps_update(
        db: Session,
        ride_id: int,
        driver_id: int,
        latitude: float,
        longitude: float,
        speed_kmh: float | None = None,
        accuracy_meters: float | None = None,
        heading_degrees: float | None = None,
        device_timestamp: float | None = None,
    ) -> RideGuardEvent:
        latest = (
            db.query(RideGuardEvent)
            .filter(
                RideGuardEvent.ride_id == ride_id,
                RideGuardEvent.event_type == RideGuardEventType.GPS_UPDATE,
            )
            .order_by(RideGuardEvent.created_at.desc())
            .first()
        )

        now = datetime.utcnow()
        if latest and latest.created_at and now - latest.created_at < timedelta(seconds=30):
            return latest

        return RideGuardService.record_event(
            db=db,
            ride_id=ride_id,
            driver_id=driver_id,
            event_type=RideGuardEventType.GPS_UPDATE,
            severity=RideGuardSeverity.INFO,
            status=RideGuardStatus.ACKNOWLEDGED,
            latitude=latitude,
            longitude=longitude,
            speed_kmh=speed_kmh,
            accuracy_meters=accuracy_meters,
            heading_degrees=heading_degrees,
            metadata={
                "device_timestamp": device_timestamp,
            } if device_timestamp is not None else None,
        )
