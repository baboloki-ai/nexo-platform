import { Link } from 'react-router-dom'

import { DriverRequestCard } from '../../components/DriverRequestCard'
import { DriverSharedRideSection } from '../../components/SharedRideSection'
import { useDriver } from '../../driver/DriverContext'
import { RideStatus, isActiveRide } from '../../types/ride'
import { DriverHomePanel } from './DriverHomePanel'

export function DriverDashboard() {
  const {
    requests,
    busy,
    refreshRequests,
    refreshTrip,
    setError,
    ride,
    nextRide,
    online,
    acceptNextRequest,
  } = useDriver()
  const activeRide = ride && isActiveRide(ride.status) ? ride : null
  const canAcceptNext =
    ride?.status === RideStatus.IN_PROGRESS && nextRide == null
  const canRespond = activeRide == null

  return (
    <>
      {activeRide && activeRide.status !== 'pending' ? (
        <p className="muted">
          Current ride {activeRide.id} is {activeRide.status}.{' '}
          <Link to={`/driver/ride/${activeRide.id}`}>Open current ride</Link>
        </p>
      ) : null}
      {nextRide ? (
        <p className="muted">
          Next Ride {nextRide.id} is accepted.{' '}
          <Link to={`/driver/ride/${nextRide.id}`}>Open next ride</Link>
        </p>
      ) : null}
      {ride?.status === RideStatus.IN_PROGRESS ? (
        <DriverSharedRideSection
          ride={ride}
          disabled={busy}
          onProposed={async () => refreshTrip(ride.id)}
          onError={setError}
        />
      ) : null}
      {online && requests.length === 0 ? (
        <p className="muted">No open passenger requests right now.</p>
      ) : null}
      {requests.map((request) => (
        <DriverRequestCard
          key={request.ride_id}
          request={request}
          busy={busy}
          canRespond={canRespond}
          canAcceptNext={canAcceptNext}
          onResponded={() => refreshRequests().then(() => undefined)}
          onAcceptNext={() =>
            acceptNextRequest(request.ride_id).then(() => undefined)
          }
          onError={setError}
        />
      ))}
      <DriverHomePanel />
    </>
  )
}
