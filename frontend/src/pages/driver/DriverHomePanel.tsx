import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { getDriverWallet } from '../../api/drivers'
import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { Input } from '../../components/Input'
import { RideSummary } from '../../components/RideSummary'
import { StatusBadge } from '../../components/StatusBadge'
import { MIN_DRIVER_WALLET } from '../../constants/fare'
import { rideStatusLabel } from '../../constants/rideStatus'
import { useDriver } from '../../driver/DriverContext'
import { gpsWatchStatusLabel } from '../../maps/useDriverGpsWatch'
import { isActiveRide } from '../../types/ride'
import type { DriverWallet } from '../../types/marketplace'
import type { VehicleCreate } from '../../types/vehicle'
import { formatCoord, formatCurrency, formatPhone } from '../../utils/format'
import { gpsPermissionLabel } from '../../utils/geolocation'
import { formatVehicleLine, driverVerificationLabel, vehicleVerificationLabel } from '../../utils/driverIdentity'

const emptyVehicle = (): VehicleCreate => ({
  make: 'Toyota',
  model: 'Corolla',
  year: 2020,
  color: 'White',
  registration_number: '',
  vehicle_type: 'sedan',
})

function locationStatusLabel(status: string): string {
  switch (status) {
    case 'sending':
      return 'Sending…'
    case 'ok':
      return 'Last update succeeded'
    case 'error':
      return 'Last update failed'
    default:
      return 'Not sent yet'
  }
}

export function DriverHomePanel() {
  const {
    online,
    latitude,
    longitude,
    setLatitude,
    setLongitude,
    gpsPermission,
    gpsSource,
    gpsMode,
    gpsConfirmed,
    gpsWatchStatus,
    gpsWatchError,
    locationStatus,
    ride,
    nextRide,
    vehicles,
    profile,
    approved,
    busy,
    goOnlineNow,
    goOfflineNow,
    sendLocationNow,
    useLiveGps,
    useDemoGps,
    addVehicle,
  } = useDriver()
  const [vehicleForm, setVehicleForm] = useState<VehicleCreate>(emptyVehicle)
  const [wallet, setWallet] = useState<DriverWallet | null>(null)
  const activeRide = ride && isActiveRide(ride.status) ? ride : null
  const verification = profile?.verification_status ?? null
  const awaitingVerification = profile != null && !approved
  const listedVehicle =
  vehicles.find((vehicle) => vehicle.verification_status === 'approved') ??
  profile?.vehicle ??
  vehicles[0] ??
  null
  const hasApprovedVehicle = [listedVehicle, ...vehicles].some(
    (item) => item != null && item.verification_status === 'approved',
  )
  const walletBelowMinimum = wallet != null && !wallet.meets_minimum

  useEffect(() => {
    let cancelled = false
    void getDriverWallet()
      .then((next) => {
        if (!cancelled) setWallet(next)
      })
      .catch(() => {
        // Home still works if the wallet endpoint is briefly unavailable.
      })
    return () => {
      cancelled = true
    }
  }, [online, approved])

  async function onAddVehicle(event: FormEvent) {
    event.preventDefault()
    try {
      await addVehicle({
        ...vehicleForm,
        year: Number(vehicleForm.year),
      })
      setVehicleForm(emptyVehicle())
    } catch {
      // Layout shows the API error.
    }
  }

  return (
    <>
      <Card className="hero-card">
        <p className="eyebrow">Driver</p>
        <h2>{profile?.display_name ?? 'Driver'}</h2>
        {profile?.phone_number ? (
          <p className="muted">{formatPhone(profile.phone_number)}</p>
        ) : null}
        <div className="status-row">
          <span className={`status-pill ${approved ? 'is-ok' : ''}`}>
            {driverVerificationLabel(verification)}
          </span>
          <span className={`status-pill ${online ? 'is-ok' : ''}`}>
            {online ? 'Online' : 'Offline'}
          </span>
          <span className={`status-pill ${gpsConfirmed ? 'is-ok' : ''}`}>
            GPS {gpsConfirmed ? 'ready' : 'needed'}
          </span>
          <span
            className={`status-pill ${gpsWatchStatus === 'watching' ? 'is-ok' : ''}`}
          >
            {gpsWatchStatusLabel(gpsWatchStatus)}
          </span>
        </div>
        {awaitingVerification ? (
          <div className="verify-banner">
            <p>
              {verification === 'suspended'
                ? 'Your driver account is suspended.'
                : verification === 'rejected'
                  ? 'Your driver account was not approved.'
                  : 'Your driver account is awaiting verification.'}
            </p>
            <p className="muted">
              You cannot go online or receive passenger requests until an
              approved operator marks your account as verified. Wallet balance
              must be above P{MIN_DRIVER_WALLET}. An approved vehicle is
              also required before you can go online.
            </p>
          </div>
        ) : (
          <p className="muted">
            Go online to receive marketplace requests. Accept the passenger
            offer or tap a generated counter-offer. The passenger chooses the
            driver.
          </p>
        )}
        {wallet ? (
          <div className={walletBelowMinimum ? 'verify-banner' : undefined}>
            <p className="meta">
              Wallet {formatCurrency(wallet.available_balance)} · Minimum
              operating balance {formatCurrency(wallet.minimum_balance)}
            </p>
            {walletBelowMinimum ? (
              <>
                <p>
                  Your wallet balance is zero or negative. Contact NEXO support
                  to top up before going online.
                </p>
                <Link to="/driver/performance" className="btn btn-secondary">
                  Contact NEXO Support
                </Link>
              </>
            ) : null}
          </div>
        ) : null}
        {approved && !hasApprovedVehicle ? (
          <div className="verify-banner">
            <p>
              {listedVehicle
                ? 'Your vehicle is not approved yet. You cannot go online until an operator marks a vehicle as approved.'
                : 'Add a vehicle and wait for operator approval before going online.'}
            </p>
          </div>
        ) : null}
        <div className="btn-row wrap">
          <Button
            disabled={
              busy ||
              online ||
              profile == null ||
              !approved ||
              walletBelowMinimum ||
              !hasApprovedVehicle
            }
            onClick={() => void goOnlineNow().catch(() => undefined)}
          >
            Go online
          </Button>
          <Button
            variant="ghost"
            disabled={busy || !online}
            onClick={() => void goOfflineNow().catch(() => undefined)}
          >
            Go offline
          </Button>
        </div>
      </Card>

      {listedVehicle ? (
        <Card>
          <div className="section-head">
            <div>
              <p className="eyebrow">Vehicle</p>
              <h2>{formatVehicleLine(listedVehicle)}</h2>
            </div>
          </div>
          <dl className="kv-grid">
            <div>
              <dt>Make / model</dt>
              <dd>
                {listedVehicle.make} {listedVehicle.model}
              </dd>
            </div>
            <div>
              <dt>Colour</dt>
              <dd>{listedVehicle.color}</dd>
            </div>
            <div>
              <dt>Registration</dt>
              <dd className="mono">{listedVehicle.registration_number}</dd>
            </div>
            <div>
              <dt>Vehicle review</dt>
              <dd>{vehicleVerificationLabel(listedVehicle.verification_status)}</dd>
            </div>
          </dl>
          <p className="muted">
            An approved vehicle is required to go online. Passengers see this
            vehicle on an assigned trip; an operator marks it approved.
          </p>
        </Card>
      ) : null}

      <Card>
        <div className="section-head">
          <div>
            <p className="eyebrow">Location</p>
            <h2>GPS</h2>
          </div>
        </div>
        <dl className="kv-grid gps-panel">
          <div>
            <dt>Permission</dt>
            <dd>{gpsPermissionLabel(gpsPermission)}</dd>
          </div>
          <div>
            <dt>Latest latitude</dt>
            <dd className="mono">{formatCoord(Number(latitude))}</dd>
          </div>
          <div>
            <dt>Latest longitude</dt>
            <dd className="mono">{formatCoord(Number(longitude))}</dd>
          </div>
          <div>
            <dt>Update status</dt>
            <dd>{locationStatusLabel(locationStatus)}</dd>
          </div>
          <div>
            <dt>Source</dt>
            <dd>
              {gpsMode === 'demo'
                ? 'Gaborone fallback'
                : gpsSource === 'browser'
                  ? 'Live location'
                  : gpsSource === 'test'
                    ? 'Gaborone fallback'
                    : 'None yet'}
            </dd>
          </div>
          <div>
            <dt>Tracking</dt>
            <dd>{gpsWatchStatusLabel(gpsWatchStatus)}</dd>
          </div>
        </dl>
        {gpsWatchError ? <p className="muted">{gpsWatchError}</p> : null}
        <form
          className="stack"
          onSubmit={(event) => {
            event.preventDefault()
            void sendLocationNow().catch(() => undefined)
          }}
        >
          <div className="field-row">
            <Input
              label="Latitude"
              inputMode="decimal"
              value={latitude}
              onChange={(event) => setLatitude(event.target.value)}
              required
            />
            <Input
              label="Longitude"
              inputMode="decimal"
              value={longitude}
              onChange={(event) => setLongitude(event.target.value)}
              required
            />
          </div>
          <div className="btn-row wrap">
            <Button type="submit" variant="secondary" busy={busy}>
              {busy ? 'Updating…' : 'Send location'}
            </Button>
            <Button
              type="button"
              variant="ghost"
              disabled={busy}
              onClick={() => void useDemoGps().catch(() => undefined)}
            >
              Use Gaborone fallback
            </Button>
            <Button
              type="button"
              variant="ghost"
              disabled={busy || gpsMode === 'live'}
              onClick={useLiveGps}
            >
              Use live browser GPS
            </Button>
          </div>
        </form>
      </Card>

      <Card>
        <div className="section-head">
          <div>
            <p className="eyebrow">Current ride</p>
            <h2>{activeRide ? rideStatusLabel(activeRide.status) : 'None'}</h2>
          </div>
          {activeRide ? <StatusBadge status={activeRide.status} /> : null}
        </div>
        {activeRide ? (
          <RideSummary
            ride={activeRide}
            extra={
              <Link to={`/driver/ride/${activeRide.id}`} className="btn btn-primary">
                Open ride
              </Link>
            }
          />
        ) : (
          <p className="muted">
            No assigned ride. Open requests appear above after a passenger
            submits an offer.
          </p>
        )}
      </Card>

      <Card>
        <div className="section-head">
          <div>
            <p className="eyebrow">Next ride</p>
            <h2>{nextRide ? rideStatusLabel(nextRide.status) : 'None'}</h2>
          </div>
          {nextRide ? <StatusBadge status={nextRide.status} /> : null}
        </div>
        {nextRide ? (
          <RideSummary
            ride={nextRide}
            extra={
              <Link to={`/driver/ride/${nextRide.id}`} className="btn btn-ghost">
                Open next ride
              </Link>
            }
          />
        ) : (
          <p className="muted">
            After you start a trip you can accept one future request as your
            Next Ride.
          </p>
        )}
      </Card>

      <Card>
        <h2>Vehicles</h2>
        <p className="muted">Add the vehicle passengers will see on their trip.</p>
        {vehicles.length === 0 ? (
          <p className="muted">No vehicles on file.</p>
        ) : (
          <ul className="plain-list">
            {vehicles.map((vehicle) => (
              <li key={vehicle.id}>
                {vehicle.year} {vehicle.make} {vehicle.model} · {vehicle.color} ·{' '}
                {vehicle.registration_number} ·{' '}
                {vehicleVerificationLabel(vehicle.verification_status)}
              </li>
            ))}
          </ul>
        )}
        <form className="stack" onSubmit={onAddVehicle}>
          <div className="field-row">
            <Input
              label="Make"
              value={vehicleForm.make}
              onChange={(event) =>
                setVehicleForm((current) => ({ ...current, make: event.target.value }))
              }
              required
            />
            <Input
              label="Model"
              value={vehicleForm.model}
              onChange={(event) =>
                setVehicleForm((current) => ({
                  ...current,
                  model: event.target.value,
                }))
              }
              required
            />
          </div>
          <div className="field-row">
            <Input
              label="Year"
              inputMode="numeric"
              value={String(vehicleForm.year)}
              onChange={(event) =>
                setVehicleForm((current) => ({
                  ...current,
                  year: Number(event.target.value),
                }))
              }
              required
            />
            <Input
              label="Color"
              value={vehicleForm.color}
              onChange={(event) =>
                setVehicleForm((current) => ({
                  ...current,
                  color: event.target.value,
                }))
              }
              required
            />
          </div>
          <div className="field-row">
            <Input
              label="Registration"
              value={vehicleForm.registration_number}
              onChange={(event) =>
                setVehicleForm((current) => ({
                  ...current,
                  registration_number: event.target.value,
                }))
              }
              hint="Botswana plate, for example B123XYZ"
              required
            />
            <Input
              label="Type"
              value={vehicleForm.vehicle_type}
              onChange={(event) =>
                setVehicleForm((current) => ({
                  ...current,
                  vehicle_type: event.target.value,
                }))
              }
              required
            />
          </div>
          <Button type="submit" variant="ghost" busy={busy}>
            Add vehicle
          </Button>
        </form>
      </Card>
    </>
  )
}
