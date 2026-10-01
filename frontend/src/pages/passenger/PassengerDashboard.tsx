import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { useAuth } from '../../auth/AuthContext'
import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { Input } from '../../components/Input'
import { LoadingState } from '../../components/LoadingState'
import { RideSummary } from '../../components/RideSummary'
import { PassengerSharedRideConsent } from '../../components/SharedRideSection'
import { StatusBadge } from '../../components/StatusBadge'
import { rideStatusLabel } from '../../constants/rideStatus'
import { usePassenger } from '../../passenger/PassengerContext'
import { isSearchingStatus } from '../../types/ride'
import { formatPhone } from '../../utils/format'

export function PassengerDashboard() {
  const { user } = useAuth()
  const {
    profile,
    activeRide,
    driverLocation,
    loading,
    busy,
    saveProfile,
    refreshTrip,
    setError,
  } = usePassenger()
  const [firstName, setFirstName] = useState(user?.full_name.split(' ')[0] ?? '')
  const [lastName, setLastName] = useState(
    user?.full_name.split(' ').slice(1).join(' ') ?? '',
  )

  async function onCreateProfile(event: FormEvent) {
    event.preventDefault()
    try {
      await saveProfile(firstName, lastName)
    } catch {
      // Error is shown by the passenger layout.
    }
  }

  if (loading) {
    return <LoadingState message="Loading your dashboard…" />
  }

  if (!profile) {
    return (
      <Card>
        <p className="eyebrow">Welcome to NEXO</p>
        <h2>Create your passenger profile</h2>
        <p className="muted">
          A passenger profile is required before you can request a ride.
        </p>
        <form className="stack" onSubmit={onCreateProfile}>
          <div className="field-row">
            <Input
              label="First name"
              value={firstName}
              onChange={(event) => setFirstName(event.target.value)}
              required
            />
            <Input
              label="Last name"
              value={lastName}
              onChange={(event) => setLastName(event.target.value)}
              required
            />
          </div>
          <Button type="submit" busy={busy}>
            {busy ? 'Saving…' : 'Save profile'}
          </Button>
        </form>
      </Card>
    )
  }

  const availability = activeRide
    ? isSearchingStatus(activeRide.status)
      ? 'Finding a driver'
      : 'On a trip'
    : 'Ready to ride'

  return (
    <>
      <Card className="hero-card">
        <p className="eyebrow">Passenger</p>
        <h2>Hi, {profile.first_name}</h2>
        <p className="muted">
          {formatPhone(profile.phone)}
        </p>
        <div className="status-row">
          <span className="status-pill">{availability}</span>
        </div>
        {!activeRide ? (
          <Link to="/passenger/request" className="btn btn-primary btn-block">
            Request a ride
          </Link>
        ) : null}
      </Card>

      {activeRide ? (
        <PassengerSharedRideConsent
          ride={activeRide}
          disabled={busy}
          onRefresh={() => refreshTrip(activeRide.id)}
          onError={setError}
        />
      ) : null}

      {activeRide ? (
        <Card>
          <div className="section-head">
            <div>
              <p className="eyebrow">Active ride</p>
              <h2>{rideStatusLabel(activeRide.status)}</h2>
            </div>
            <StatusBadge status={activeRide.status} />
          </div>
          <RideSummary
            ride={activeRide}
            driverLocation={
              driverLocation
                ? {
                    latitude: driverLocation.latitude,
                    longitude: driverLocation.longitude,
                  }
                : null
            }
            extra={
              <Link
                to={`/passenger/ride/${activeRide.id}`}
                className="btn btn-primary"
              >
                Open ride
              </Link>
            }
          />
        </Card>
      ) : (
        <Card>
          <p className="eyebrow">No active ride</p>
          <h2>Where to?</h2>
          <p className="muted">
            Enter a pickup and destination when you are ready. Payment is cash —
            pay the driver directly after the trip.
          </p>
        </Card>
      )}

      <Card>
        <div className="section-head">
          <div>
            <p className="eyebrow">Past trips</p>
            <h2>Ride history</h2>
          </div>
          <Link to="/passenger/history" className="btn btn-ghost">
            View history
          </Link>
        </div>
        <p className="muted">Completed and cancelled rides appear here.</p>
      </Card>
    </>
  )
}
