import { Link } from 'react-router-dom'

import { Card } from '../../components/Card'
import { LoadingState } from '../../components/LoadingState'
import { StatusBadge } from '../../components/StatusBadge'
import { usePassenger } from '../../passenger/PassengerContext'
import { isHistoricalRide } from '../../types/ride'
import { paymentHistoryLabel } from '../../types/payment'
import { formatCurrency, formatPlace, formatWhen } from '../../utils/format'
import { assignedDriverName } from '../../utils/driverIdentity'

export function PassengerHistoryPage() {
  const { rides, loading, profile } = usePassenger()

  if (loading) {
    return <LoadingState message="Loading ride history…" />
  }

  const history = rides.filter((ride) => isHistoricalRide(ride.status))

  return (
    <Card>
      <p className="eyebrow">Passenger</p>
      <h2>Ride history</h2>
      <p className="muted">Completed, cancelled, and expired trips.</p>
      {history.length === 0 ? (
        <p className="muted">
          {profile ? 'No completed rides yet.' : 'Create a passenger profile first.'}
        </p>
      ) : (
        <ul className="ride-list">
          {history.map((ride) => (
            <li key={ride.id}>
              <Link to={`/passenger/ride/${ride.id}`} className="ride-list-item">
                <div>
                  <strong>
                    {formatPlace(
                      ride.pickup_location,
                      ride.pickup_latitude,
                      ride.pickup_longitude,
                    )}{' '}
                    →{' '}
                    {formatPlace(
                      ride.destination,
                      ride.destination_latitude,
                      ride.destination_longitude,
                    )}
                  </strong>
                  <p className="meta">
                    Fare:{' '}
                    {formatCurrency(
                      ride.agreed_fare ??
                        ride.passenger_current_offer ??
                        ride.proposed_fare,
                    )}{' '}
                    · {formatWhen(ride.requested_at)}
                    {assignedDriverName(ride)
                      ? ` · ${assignedDriverName(ride)}`
                      : ''}
                    {paymentHistoryLabel(ride.payment)
                      ? ` · ${paymentHistoryLabel(ride.payment)}`
                      : ''}
                  </p>
                </div>
                <StatusBadge status={ride.status} />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
