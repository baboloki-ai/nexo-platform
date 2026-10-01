class RideGuardEventType:
    TRIP_STARTED = "trip_started"
    GPS_UPDATE = "gps_update"
    LONG_STOP = "long_stop"
    ROUTE_DEVIATION = "route_deviation"
    GPS_LOST = "gps_lost"
    POSSIBLE_CRASH = "possible_crash"
    SOS_TRIGGERED = "sos_triggered"
    SAFETY_CHECK = "safety_check"
    SAFETY_CONFIRMED = "safety_confirmed"
    HELP_REQUESTED = "help_requested"
    TRIP_ENDED = "trip_ended"


class RideGuardSeverity:
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class RideGuardStatus:
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"
