export type GpsPermission =
  | 'unknown'
  | 'prompt'
  | 'granted'
  | 'denied'
  | 'unavailable'

export type BrowserLocation = {
  latitude: number
  longitude: number
}

export function gpsPermissionLabel(status: GpsPermission): string {
  switch (status) {
    case 'granted':
      return 'Allowed'
    case 'denied':
      return 'Blocked'
    case 'prompt':
      return 'Not asked yet'
    case 'unavailable':
      return 'Not available in this browser'
    default:
      return 'Unknown'
  }
}

export async function queryGpsPermission(): Promise<GpsPermission> {
  if (!navigator.geolocation) return 'unavailable'
  if (!navigator.permissions?.query) return 'unknown'
  try {
    const result = await navigator.permissions.query({ name: 'geolocation' })
    if (
      result.state === 'granted' ||
      result.state === 'denied' ||
      result.state === 'prompt'
    ) {
      return result.state
    }
    return 'unknown'
  } catch {
    return 'unknown'
  }
}

export function getBrowserLocation(
  timeoutMs = 8000,
): Promise<BrowserLocation | null> {
  if (!navigator.geolocation) return Promise.resolve(null)

  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (position) => {
        resolve({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
        })
      },
      () => resolve(null),
      {
        enableHighAccuracy: true,
        timeout: timeoutMs,
        maximumAge: 10_000,
      },
    )
  })
}
