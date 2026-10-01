const TOKEN_KEY = 'nexo.access_token'
const DRIVER_RIDE_KEY = 'nexo.driver.current_ride_id'
const DRIVER_GPS_KEY = 'nexo.driver.gps'
const DRIVER_ONLINE_KEY = 'nexo.driver.online'
const DRIVER_HISTORY_KEY = 'nexo.driver.history_ids'

export type StoredGps = {
  latitude: number
  longitude: number
}

let unauthorizedHandler: (() => void) | null = null

export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  sessionStorage.removeItem(TOKEN_KEY)
}

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler
}

export function notifyUnauthorized(): void {
  clearToken()
  unauthorizedHandler?.()
}

export function getDriverRideId(): number | null {
  const raw = sessionStorage.getItem(DRIVER_RIDE_KEY)
  if (!raw) return null
  const parsed = Number(raw)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
}

export function setDriverRideId(rideId: number | null): void {
  if (rideId == null) {
    sessionStorage.removeItem(DRIVER_RIDE_KEY)
    return
  }
  sessionStorage.setItem(DRIVER_RIDE_KEY, String(rideId))
}

export function getDriverGps(): StoredGps | null {
  const raw = sessionStorage.getItem(DRIVER_GPS_KEY)
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as StoredGps
    if (
      typeof parsed.latitude === 'number' &&
      typeof parsed.longitude === 'number'
    ) {
      return parsed
    }
  } catch {
    return null
  }
  return null
}

export function setDriverGps(gps: StoredGps): void {
  sessionStorage.setItem(DRIVER_GPS_KEY, JSON.stringify(gps))
}

export function getDriverOnlineHint(): boolean {
  return sessionStorage.getItem(DRIVER_ONLINE_KEY) === '1'
}

export function setDriverOnlineHint(online: boolean): void {
  if (online) {
    sessionStorage.setItem(DRIVER_ONLINE_KEY, '1')
    return
  }
  sessionStorage.removeItem(DRIVER_ONLINE_KEY)
}

export function getDriverHistoryIds(): number[] {
  const raw = sessionStorage.getItem(DRIVER_HISTORY_KEY)
  if (!raw) return []
  try {
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(
      (id): id is number => typeof id === 'number' && Number.isInteger(id) && id > 0,
    )
  } catch {
    return []
  }
}

export function addDriverHistoryId(rideId: number): void {
  const ids = getDriverHistoryIds().filter((id) => id !== rideId)
  sessionStorage.setItem(
    DRIVER_HISTORY_KEY,
    JSON.stringify([rideId, ...ids].slice(0, 50)),
  )
}

export function clearClientSession(): void {
  clearToken()
  sessionStorage.removeItem(DRIVER_RIDE_KEY)
  sessionStorage.removeItem(DRIVER_GPS_KEY)
  sessionStorage.removeItem(DRIVER_ONLINE_KEY)
  sessionStorage.removeItem(DRIVER_HISTORY_KEY)
}
