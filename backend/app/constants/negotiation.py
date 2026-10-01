class NegotiationActorType:
    PASSENGER = "passenger"
    DRIVER = "driver"
    SYSTEM = "system"

    ALL = (PASSENGER, DRIVER, SYSTEM)


class NegotiationAction:
    PASSENGER_OFFER_CREATED = "passenger_offer_created"
    PASSENGER_OFFER_INCREASED = "passenger_offer_increased"
    PASSENGER_OFFER_MAINTAINED = "passenger_offer_maintained"
    DRIVER_ACCEPTED_PASSENGER_OFFER = "driver_accepted_passenger_offer"
    DRIVER_SUBMITTED_OFFER = "driver_submitted_offer"
    DRIVER_RESPONSE_REPLACED = "driver_response_replaced"
    PASSENGER_ACCEPTED_DRIVER_OFFER = "passenger_accepted_driver_offer"
    PASSENGER_SELECTED_DRIVER = "passenger_selected_driver"
    FARE_AGREED = "fare_agreed"
    DRIVER_RESPONSE_EXPIRED = "driver_response_expired"
    DRIVER_RESPONSE_WITHDRAWN = "driver_response_withdrawn"
    LOSER_CLOSED = "loser_closed"
    DRIVER_IGNORED = "driver_ignored"
    REQUEST_CANCELLED = "request_cancelled"
    REQUEST_EXPIRED = "request_expired"

    ALL = (
        PASSENGER_OFFER_CREATED,
        PASSENGER_OFFER_INCREASED,
        PASSENGER_OFFER_MAINTAINED,
        DRIVER_ACCEPTED_PASSENGER_OFFER,
        DRIVER_SUBMITTED_OFFER,
        DRIVER_RESPONSE_REPLACED,
        PASSENGER_ACCEPTED_DRIVER_OFFER,
        PASSENGER_SELECTED_DRIVER,
        FARE_AGREED,
        DRIVER_RESPONSE_EXPIRED,
        DRIVER_RESPONSE_WITHDRAWN,
        LOSER_CLOSED,
        DRIVER_IGNORED,
        REQUEST_CANCELLED,
        REQUEST_EXPIRED,
    )


class PassengerOfferAction:
    INCREASE = "increase"
    MAINTAIN = "maintain"

    ALL = (INCREASE, MAINTAIN)
