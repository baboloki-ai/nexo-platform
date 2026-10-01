import { NEXO_DEFAULT_LAT, NEXO_DEFAULT_LNG } from '../constants/location'

/** Gaborone. Used only when a map has no ride coordinates. */
export const DEFAULT_MAP_CENTER = {
  latitude: NEXO_DEFAULT_LAT,
  longitude: NEXO_DEFAULT_LNG,
}

export const DEFAULT_MAP_ZOOM = 13

export const MAP_TILE_URL =
  import.meta.env.VITE_MAP_TILE_URL?.trim() ||
  'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'

export const MAP_ATTRIBUTION =
  import.meta.env.VITE_MAP_ATTRIBUTION?.trim() ||
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
