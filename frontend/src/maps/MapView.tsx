import { useEffect, useMemo, useRef } from 'react'
import { MapContainer, TileLayer, useMap, useMapEvents } from 'react-leaflet'
import L from 'leaflet'

import { DestinationMarker } from './DestinationMarker'
import { DriverMarker } from './DriverMarker'
import { PickupMarker } from './PickupMarker'
import {
  DEFAULT_MAP_CENTER,
  DEFAULT_MAP_ZOOM,
  MAP_ATTRIBUTION,
  MAP_TILE_URL,
} from './tiles'
import type { MapPoint } from './types'
import { isValidLatLng, toLatLng } from './types'

import 'leaflet/dist/leaflet.css'

type MapViewProps = {
  pickup?: MapPoint | null
  destination?: MapPoint | null
  driver?: MapPoint | null
  onMapClick?: (point: { latitude: number; longitude: number }) => void
  fitNonce?: number
  className?: string
}

function validPoint(point: MapPoint | null | undefined): MapPoint | null {
  if (!point) return null
  return isValidLatLng(point.latitude, point.longitude) ? point : null
}

function ClickHandler({
  onMapClick,
}: {
  onMapClick?: (point: { latitude: number; longitude: number }) => void
}) {
  useMapEvents({
    click(event) {
      if (!onMapClick) return
      const { lat, lng } = event.latlng
      if (!isValidLatLng(lat, lng)) return
      onMapClick({ latitude: lat, longitude: lng })
    },
  })
  return null
}

function ResizeFix() {
  const map = useMap()
  useEffect(() => {
    const container = map.getContainer()
    const observer = new ResizeObserver(() => {
      map.invalidateSize()
    })
    observer.observe(container)
    map.invalidateSize()
    return () => observer.disconnect()
  }, [map])
  return null
}

function FitRideBounds({
  pickup,
  destination,
  driver,
  fitNonce,
}: {
  pickup: MapPoint | null
  destination: MapPoint | null
  driver: MapPoint | null
  fitNonce: number
}) {
  const map = useMap()
  const pickupRef = useRef(pickup)
  const destinationRef = useRef(destination)
  const driverRef = useRef(driver)
  pickupRef.current = pickup
  destinationRef.current = destination
  driverRef.current = driver

  const sceneKey = `${fitNonce}:${pickup ? 'p' : ''}${destination ? 'd' : ''}${
    !pickup && !destination && driver ? 'v' : ''
  }`

  useEffect(() => {
    const points: [number, number][] = []
    if (pickupRef.current) points.push(toLatLng(pickupRef.current))
    if (destinationRef.current) points.push(toLatLng(destinationRef.current))
    if (points.length === 0 && driverRef.current) {
      points.push(toLatLng(driverRef.current))
    }

    if (points.length >= 2) {
      map.fitBounds(L.latLngBounds(points), {
        padding: [36, 36],
        maxZoom: 15,
      })
      return
    }
    if (points.length === 1) {
      map.setView(points[0], 14)
    }
  }, [map, sceneKey])

  return null
}

export function MapView({
  pickup,
  destination,
  driver,
  onMapClick,
  fitNonce = 0,
  className = '',
}: MapViewProps) {
  const pickupPoint = validPoint(pickup)
  const destinationPoint = validPoint(destination)
  const driverPoint = validPoint(driver)

  const center = useMemo<[number, number]>(() => {
    if (pickupPoint) return toLatLng(pickupPoint)
    if (destinationPoint) return toLatLng(destinationPoint)
    if (driverPoint) return toLatLng(driverPoint)
    return [DEFAULT_MAP_CENTER.latitude, DEFAULT_MAP_CENTER.longitude]
  }, [pickupPoint, destinationPoint, driverPoint])

  return (
    <div className={`nexo-map ${className}`.trim()}>
      <MapContainer
        center={center}
        zoom={DEFAULT_MAP_ZOOM}
        scrollWheelZoom
        className="nexo-map-canvas"
      >
        <TileLayer attribution={MAP_ATTRIBUTION} url={MAP_TILE_URL} />
        <ResizeFix />
        <FitRideBounds
          pickup={pickupPoint}
          destination={destinationPoint}
          driver={driverPoint}
          fitNonce={fitNonce}
        />
        <ClickHandler onMapClick={onMapClick} />
        {pickupPoint ? <PickupMarker point={pickupPoint} /> : null}
        {destinationPoint ? (
          <DestinationMarker point={destinationPoint} />
        ) : null}
        {driverPoint ? <DriverMarker point={driverPoint} /> : null}
      </MapContainer>
    </div>
  )
}
