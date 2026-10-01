import { Outlet } from 'react-router-dom'

import { AppHeader } from '../components/AppHeader'
import { ErrorMessage, InfoBanner } from '../components/ErrorMessage'
import { socketStatusLabel } from '../utils/rideEvents'
import { PassengerProvider, usePassenger } from './PassengerContext'

function PassengerShell() {
  const { profile, socketStatus, error, info, setError } = usePassenger()

  return (
    <div className="app-shell">
      <AppHeader
        title="Passenger"
        socketConnected={socketStatus === 'connected'}
        socketLabel={socketStatusLabel(socketStatus)}
        nav={
          profile
            ? [
                { to: '/passenger', label: 'Home', end: true },
                { to: '/passenger/request', label: 'Request' },
                { to: '/passenger/history', label: 'History' },
              ]
            : []
        }
      />
      <main className="page">
        {socketStatus === 'disconnected' ? (
          <InfoBanner message="Reconnecting to live updates. Your ride status will catch up automatically." />
        ) : null}
        <ErrorMessage message={error} onDismiss={() => setError(null)} />
        <InfoBanner message={info} />
        <Outlet />
      </main>
    </div>
  )
}

export function PassengerLayout() {
  return (
    <PassengerProvider>
      <PassengerShell />
    </PassengerProvider>
  )
}
