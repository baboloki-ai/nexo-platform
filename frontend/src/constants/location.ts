function readNumberEnv(value: string | undefined, fallback: number): number {
  if (value == null || value.trim() === '') return fallback
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

/** Gaborone CBD. Map fallback and example pickup. */
export const NEXO_DEFAULT_LAT = readNumberEnv(
  import.meta.env.VITE_MAP_DEFAULT_LAT,
  -24.6545,
)
export const NEXO_DEFAULT_LNG = readNumberEnv(
  import.meta.env.VITE_MAP_DEFAULT_LNG,
  25.9086,
)

export const EXAMPLE_PICKUP = {
  label: 'Main Mall, Gaborone',
  latitude: NEXO_DEFAULT_LAT,
  longitude: NEXO_DEFAULT_LNG,
}

export const EXAMPLE_DESTINATION = {
  label: 'Airport Junction, Gaborone',
  latitude: -24.6278,
  longitude: 25.9059,
}

export const FALLBACK_DRIVER_GPS = {
  latitude: NEXO_DEFAULT_LAT + 0.0005,
  longitude: NEXO_DEFAULT_LNG + 0.0004,
}

