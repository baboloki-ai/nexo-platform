import { useMemo } from 'react'

import type { MapPoint } from './types'
import { isValidLatLng } from './types'

type LiveLocation = {
  latitude: number
  longitude: number
} | null

/**
 * Turns a live driver_location payload into a map point.
 * Returns null until a valid WebSocket (or equivalent) position exists.
 * Does not fetch GPS and does not import auth or personal data.
 */
export function useLiveDriverLocation(location: LiveLocation): MapPoint | null {
  return useMemo(() => {
    if (!location) return null
    if (!isValidLatLng(location.latitude, location.longitude)) return null
    return {
      latitude: location.latitude,
      longitude: location.longitude,
      label: 'Driver',
    }
  }, [location])
}
