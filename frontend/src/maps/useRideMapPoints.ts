import { useMemo } from 'react'

import type { MapPoint } from './types'
import { isValidLatLng } from './types'

type RideCoordinates = {
  pickup_latitude?: number | null
  pickup_longitude?: number | null
  destination_latitude?: number | null
  destination_longitude?: number | null
}

export function useRideMapPoints(ride: RideCoordinates | null | undefined): {
  pickup: MapPoint | null
  destination: MapPoint | null
} {
  return useMemo(() => {
    const pickupLat = ride?.pickup_latitude
    const pickupLng = ride?.pickup_longitude
    const destLat = ride?.destination_latitude
    const destLng = ride?.destination_longitude

    return {
      pickup:
        pickupLat != null &&
        pickupLng != null &&
        isValidLatLng(pickupLat, pickupLng)
          ? { latitude: pickupLat, longitude: pickupLng, label: 'Pickup' }
          : null,
      destination:
        destLat != null && destLng != null && isValidLatLng(destLat, destLng)
          ? { latitude: destLat, longitude: destLng, label: 'Destination' }
          : null,
    }
  }, [
    ride?.pickup_latitude,
    ride?.pickup_longitude,
    ride?.destination_latitude,
    ride?.destination_longitude,
  ])
}
