import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { Card } from '../../components/Card'
import { LoadingState } from '../../components/LoadingState'
import { StatusBadge } from '../../components/StatusBadge'
import { useDriver } from '../../driver/DriverContext'
import { isHistoricalRide } from '../../types/ride'
import { paymentHistoryLabel } from '../../types/payment'
import { formatCurrency, formatPlace, formatWhen } from '../../utils/format'

export function DriverHistoryPage() {
  const { historyRides, loadHistory, ride } = useDriver()
  const [loading, setLoading] = useState(historyRides.length === 0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    void loadHistory()
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [loadHistory, ride?.id, ride?.status])

  if (loading) {
    return <LoadingState message="Loading ride history…" />
  }

  const history = historyRides.filter((item) => isHistoricalRide(item.status))

  return (
    <Card>
      <p className="eyebrow">Driver</p>
      <h2>Ride history</h2>
      <p className="muted">
        Completed trips for this account. Fare is the locked agreed cash fare.
      </p>
      {history.length === 0 ? (
        <p className="muted">No completed rides yet.</p>
      ) : (
        <ul className="ride-list">
          {history.map((item) => (
            <li key={item.id}>
              <Link to={`/driver/ride/${item.id}`} className="ride-list-item">
                <div>
                  <strong>
                    {formatPlace(
                      item.pickup_location,
                      item.pickup_latitude,
                      item.pickup_longitude,
                    )}{' '}
                    →{' '}
                    {formatPlace(
                      item.destination,
                      item.destination_latitude,
                      item.destination_longitude,
                    )}
                  </strong>
                  <p className="meta">
                    Fare:{' '}
                    {formatCurrency(
                      item.agreed_fare ??
                        item.passenger_current_offer ??
                        item.proposed_fare,
                    )}{' '}
                    · {formatWhen(item.requested_at)}
                    {paymentHistoryLabel(item.payment)
                      ? ` · ${paymentHistoryLabel(item.payment)}`
                      : ''}
                  </p>
                </div>
                <StatusBadge status={item.status} />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
