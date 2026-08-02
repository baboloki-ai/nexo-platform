from math import radians, sin, cos, sqrt, atan2


class LocationService:
    """
    Handles all GPS calculations for NEXO.
    """

    EARTH_RADIUS_KM = 6371

    @staticmethod
    def calculate_distance(
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float
    ) -> float:
        """
        Calculate the distance between two GPS coordinates
        using the Haversine formula.

        Returns:
            Distance in kilometers.
        """

        lat1 = radians(lat1)
        lon1 = radians(lon1)

        lat2 = radians(lat2)
        lon2 = radians(lon2)

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = (
            sin(dlat / 2) ** 2
            + cos(lat1)
            * cos(lat2)
            * sin(dlon / 2) ** 2
        )

        c = 2 * atan2(
            sqrt(a),
            sqrt(1 - a)
        )

        return LocationService.EARTH_RADIUS_KM * c