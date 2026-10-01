class DriverResponseType:
    ACCEPT_PASSENGER_OFFER = "accept_passenger_offer"
    COUNTER_OFFER = "counter_offer"

    ALL = (ACCEPT_PASSENGER_OFFER, COUNTER_OFFER)


class DriverResponseStatus:
    OPEN = "open"
    SELECTED = "selected"
    CLOSED_LOSER = "closed_loser"
    EXPIRED = "expired"
    WITHDRAWN = "withdrawn"

    ALL = (OPEN, SELECTED, CLOSED_LOSER, EXPIRED, WITHDRAWN)
    TERMINAL = (SELECTED, CLOSED_LOSER, EXPIRED, WITHDRAWN)
