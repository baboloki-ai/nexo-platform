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

    # Pilot: passenger may cancel until the driver starts the trip.
    PASSENGER_CANCELLABLE = (
        PENDING,
        PENDING_DRIVER_ACCEPTANCE,
        ACCEPTED,
        DRIVER_ARRIVING,
        DRIVER_ARRIVED,
    )
    # Pilot: assigned driver may cancel until the trip starts.
    DRIVER_CANCELLABLE = (
        ACCEPTED,
        DRIVER_ARRIVING,
        DRIVER_ARRIVED,
    )
    # Cash confirmation is blocked once the ride is no longer live.
    PAYMENT_CONFIRMATION_BLOCKED = (
        CANCELLED_BY_PASSENGER,
        CANCELLED_BY_DRIVER,
        EXPIRED,
    )