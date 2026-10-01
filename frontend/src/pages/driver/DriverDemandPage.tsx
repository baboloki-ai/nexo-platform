import { useEffect, useMemo, useState } from 'react'

import { getDriverDemand } from '../../api/drivers'
import { toUserMessage } from '../../api/client'
import { Card } from '../../components/Card'
import { LoadingState } from '../../components/LoadingState'
import { MapView } from '../../maps/MapView'
import type { MapPoint } from '../../maps/types'
import type { DriverDemand } from '../../types/marketplace'
import { useDriver } from '../../driver/DriverContext'

export function DriverDemandPage() {
  const { setError } = useDriver()
  const [demand, setDemand] = useState<DriverDemand | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    void getDriverDemand()
      .then((next) => {
        if (!cancelled) setDemand(next)
      })
      .catch((err) => {
        if (!cancelled) setError(toUserMessage(err))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [setError])

  const points = useMemo(() => {
    if (!demand) return { pickup: null as MapPoint | null }
    const cells = demand.cells.map((cell) => ({
      latitude: cell.latitude,
      longitude: cell.longitude,
      label: `${cell.count} pickup${cell.count === 1 ? '' : 's'}`,
    }))
    const self = demand.online_drivers.find((item) => item.self)
    return {
      pickup: self
        ? {
            latitude: self.latitude,
            longitude: self.longitude,
            label: 'You',
          }
        : cells[0] ?? null,
    }
  }, [demand])

  if (loading) return <LoadingState message="Loading Gaborone demand…" />

  return (
    <>
      <Card className="hero-card">
        <p className="eyebrow">Demand</p>
        <h2>Gaborone activity</h2>
        <p className="muted">
          Real NEXO pickups from the last {demand?.window_minutes ?? 60} minutes.
          Empty cells mean no requests in that window.
        </p>
      </Card>
      <Card>
        <MapView pickup={points.pickup} destination={null} />
        <p className="muted">
          {demand?.cells.length
            ? `${demand.cells.reduce((sum, cell) => sum + cell.count, 0)} pickup(s) across ${demand.cells.length} area(s).`
            : 'No recent pickups.'}{' '}
          {demand?.online_drivers.length ?? 0} driver(s) currently online.
        </p>
        {demand?.cells.length ? (
          <ul className="plain-list">
            {demand.cells.map((cell) => (
              <li key={`${cell.latitude}:${cell.longitude}`}>
                {cell.count} pickup{cell.count === 1 ? '' : 's'} near{' '}
                {cell.latitude.toFixed(3)}, {cell.longitude.toFixed(3)}
              </li>
            ))}
          </ul>
        ) : null}
      </Card>
    </>
  )
}
