import { Marker, Popup } from 'react-leaflet'
import L from 'leaflet'

import type { MapPoint } from './types'
import { toLatLng } from './types'

const driverIcon = L.divIcon({
  className: 'nexo-marker nexo-marker-driver',
  html: '<span aria-hidden="true">🚗</span>',
  iconSize: [32, 32],
  iconAnchor: [16, 30],
  popupAnchor: [0, -24],
})

export function DriverMarker({ point }: { point: MapPoint }) {
  return (
    <Marker position={toLatLng(point)} icon={driverIcon}>
      <Popup>{point.label ?? 'Driver'}</Popup>
    </Marker>
  )
}
