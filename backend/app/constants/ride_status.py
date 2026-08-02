class RideStatus:
    PENDING = "pending"
    PENDING_DRIVER_ACCEPTANCE = "pending_driver_acceptance"
    ACCEPTED = "accepted"
    DRIVER_ARRIVING = "driver_arriving"
    DRIVER_ARRIVED = "driver_arrived"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"

    CANCELLED_BY_PASSENGER = "cancelled_by_passenger"
    CANCELLED_BY_DRIVER = "cancelled_by_driver"

    EXPIRED = "expired"
    NO_DRIVER_AVAILABLE = "no_driver_available"