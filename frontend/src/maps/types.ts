export type MapPoint = {
  latitude: number
  longitude: number
  label?: string
}

export type MapSelectMode = 'pickup' | 'destination'

export type GpsWatchStatus =
  | 'idle'
  | 'requesting'
  | 'watching'
  | 'denied'
  | 'unavailable'
  | 'timeout'
  | 'error'

export function isValidLatitude(value: number): boolean {
  return Number.isFinite(value) && value >= -90 && value <= 90
}

export function isValidLongitude(value: number): boolean {
  return Number.isFinite(value) && value >= -180 && value <= 180
}

export function isValidLatLng(latitude: number, longitude: number): boolean {
  return isValidLatitude(latitude) && isValidLongitude(longitude)
}

export function toLatLng(point: MapPoint): [number, number] {
  return [point.latitude, point.longitude]
}
