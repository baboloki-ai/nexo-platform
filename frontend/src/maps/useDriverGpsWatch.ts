import { useEffect, useRef, useState } from 'react'

import type { GpsWatchStatus, MapPoint } from './types'
import { isValidLatLng } from './types'

const MIN_INTERVAL_MS = 7000
const MIN_MOVE_METERS = 25

type WatchArgs = {
  enabled: boolean
  onPosition: (point: {
    latitude: number
    longitude: number
    accuracy: number | null
    speed: number | null
    heading: number | null
    timestamp: number
  }) => void
}

function haversineMeters(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
): number {
  const toRad = (value: number) => (value * Math.PI) / 180
  const earth = 6371000
  const dLat = toRad(lat2 - lat1)
  const dLon = toRad(lon2 - lon1)
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2
  return 2 * earth * Math.asin(Math.min(1, Math.sqrt(a)))
}

function shouldEmit(
  previous: { latitude: number; longitude: number; at: number } | null,
  latitude: number,
  longitude: number,
  now: number,
): boolean {
  if (!previous) return true
  const moved = haversineMeters(
    previous.latitude,
    previous.longitude,
    latitude,
    longitude,
  )
  const elapsed = now - previous.at
  return moved >= MIN_MOVE_METERS || elapsed >= MIN_INTERVAL_MS
}

export function gpsWatchStatusLabel(status: GpsWatchStatus): string {
  switch (status) {
    case 'requesting':
      return 'Requesting permission…'
    case 'watching':
      return 'Location tracking on'
    case 'denied':
      return 'Location permission blocked'
    case 'unavailable':
      return 'Position unavailable'
    case 'timeout':
      return 'Location timed out'
    case 'error':
      return 'Could not track location'
    default:
      return 'Location tracking off'
  }
}

/**
 * Browser geolocation watch. Reports coordinates only — callers send them
 * to the existing PUT /drivers/location. Does not import auth or tokens.
 */
export function useDriverGpsWatch({ enabled, onPosition }: WatchArgs): {
  status: GpsWatchStatus
  lastPosition: MapPoint | null
  errorMessage: string | null
} {
  const [status, setStatus] = useState<GpsWatchStatus>('idle')
  const [lastPosition, setLastPosition] = useState<MapPoint | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const onPositionRef = useRef(onPosition)
  onPositionRef.current = onPosition
  const lastEmitRef = useRef<{
    latitude: number
    longitude: number
    at: number
  } | null>(null)

  useEffect(() => {
    if (!enabled) {
      lastEmitRef.current = null
      setStatus('idle')
      setErrorMessage(null)
      return
    }

    if (!navigator.geolocation) {
      setStatus('unavailable')
      setErrorMessage('Geolocation is not available in this browser.')
      return
    }

    setStatus('requesting')
    const watchId = navigator.geolocation.watchPosition(
      (position) => {
        const latitude = position.coords.latitude
        const longitude = position.coords.longitude
        if (!isValidLatLng(latitude, longitude)) return

        const next: MapPoint = { latitude, longitude, label: 'Driver' }
        setLastPosition(next)
        setStatus('watching')
        setErrorMessage(null)

        const now = Date.now()
        if (!shouldEmit(lastEmitRef.current, latitude, longitude, now)) {
          return
        }
        lastEmitRef.current = { latitude, longitude, at: now }
        onPositionRef.current({
          latitude,
          longitude,
          accuracy: position.coords.accuracy ?? null,
          speed: position.coords.speed ?? null,
          heading: position.coords.heading ?? null,
          timestamp: position.timestamp,
        })
      },
      (error) => {
        if (error.code === error.PERMISSION_DENIED) {
          setStatus('denied')
          setErrorMessage('Location permission was blocked.')
          return
        }
        if (error.code === error.POSITION_UNAVAILABLE) {
          setStatus('unavailable')
          setErrorMessage('Current position is unavailable.')
          return
        }
        if (error.code === error.TIMEOUT) {
          setStatus('timeout')
          setErrorMessage('Location request timed out.')
          return
        }
        setStatus('error')
        setErrorMessage('Could not read browser location.')
      },
      {
        enableHighAccuracy: true,
        timeout: 15_000,
        maximumAge: 5_000,
      },
    )

    return () => {
      navigator.geolocation.clearWatch(watchId)
    }
  }, [enabled])

  return { status, lastPosition, errorMessage }
}
