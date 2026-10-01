import { Outlet } from 'react-router-dom'

import { AppHeader } from '../components/AppHeader'
import { ErrorMessage, InfoBanner } from '../components/ErrorMessage'
import { RideStatus, isActiveRide } from '../types/ride'
import { socketStatusLabel } from '../utils/rideEvents'
import { DriverProvider, useDriver } from './DriverContext'

function DriverShell() {
  const { socketStatus, error, info, setError, ride } = useDriver()
  const assigned =
    ride != null &&
    isActiveRide(ride.status) &&
    ride.status !== RideStatus.PENDING &&
    ride.status !== RideStatus.PENDING_DRIVER_ACCEPTANCE

  return (
    <div className="app-shell">
      <AppHeader
        title="Driver"
        socketConnected={socketStatus === 'connected'}
        socketLabel={socketStatusLabel(socketStatus)}
        nav={[
          { to: '/driver', label: 'Requests', end: true },
          { to: '/driver/demand', label: 'Demand' },
          { to: '/driver/performance', label: 'Performance' },
          { to: '/driver/history', label: 'History' },
        ]}
      />
      <main className="page">
        {socketStatus === 'disconnected' ? (
          <InfoBanner message="Reconnecting to live updates. Incoming requests will resume when the connection is back." />
        ) : null}
        {assigned ? (
          <InfoBanner
            message={`You have an assigned trip. Open ride ${ride.id}.`}
          />
        ) : null}
        <ErrorMessage message={error} onDismiss={() => setError(null)} />
        <InfoBanner message={info} />
        <Outlet />
      </main>
    </div>
  )
}

export function DriverLayout() {
  return (
    <DriverProvider>
      <DriverShell />
    </DriverProvider>
  )
}
