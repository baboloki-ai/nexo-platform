import type { ReactNode } from 'react'

import { rideStatusLabel } from '../constants/rideStatus'
import { RideStatus, isAssignedStatus, type Ride } from '../types/ride'
import {
  formatCoord,
  formatCurrency,
  formatEta,
  formatKm,
  formatPlace,
  formatWhen,
} from '../utils/format'
import { assignedDriverName } from '../utils/driverIdentity'
import { CashPaymentNotice } from './CashPaymentNotice'
import { StatusBadge } from './StatusBadge'

export function RideSummary({
  ride,
  extra,
  driverLocation,
  showCash = true,
}: {
  ride: Ride
  extra?: ReactNode
  driverLocation?: { latitude: number; longitude: number } | null
  showCash?: boolean
}) {
  const driverName = assignedDriverName(ride)

  return (
    <div className="ride-summary">
      <div className="ride-summary-top">
        <div>
          <p className="eyebrow">Trip</p>
          <h3 className="ride-title">{rideStatusLabel(ride.status)}</h3>
          <StatusBadge status={ride.status} />
        </div>
        {driverName ? (
          <p className="meta">{driverName}</p>
        ) : ride.accepted_driver_id != null ? (
          <p className="meta">Driver assigned</p>
        ) : (
          <p className="meta">No driver assigned yet</p>
        )}
      </div>
      <dl className="kv-grid">
        <div>
          <dt>Pickup</dt>
          <dd>
            {formatPlace(
              ride.pickup_location,
              ride.pickup_latitude,
              ride.pickup_longitude,
            )}
          </dd>
          <dd className="mono">
            {formatCoord(ride.pickup_latitude)}, {formatCoord(ride.pickup_longitude)}
          </dd>
        </div>
        <div>
          <dt>Destination</dt>
          <dd>
            {formatPlace(
              ride.destination,
              ride.destination_latitude,
              ride.destination_longitude,
            )}
          </dd>
          <dd className="mono">
            {formatCoord(ride.destination_latitude)},{' '}
            {formatCoord(ride.destination_longitude)}
          </dd>
        </div>
        <div>
          <dt>Estimated trip distance</dt>
          <dd>{formatKm(ride.trip_distance_km)}</dd>
        </div>
        {ride.recommended_fare != null && ride.agreed_fare == null ? (
          <div>
            <dt>Recommended fare</dt>
            <dd>{formatCurrency(ride.recommended_fare)}</dd>
          </div>
        ) : null}
        {ride.agreed_fare == null ? (
          <div>
            <dt>Current offer</dt>
            <dd>
              {formatCurrency(
                ride.passenger_current_offer ?? ride.proposed_fare,
              )}
            </dd>
          </div>
        ) : (
          <div>
            <dt>Agreed fare</dt>
            <dd>{formatCurrency(ride.agreed_fare)}</dd>
          </div>
        )}
        {ride.pickup_eta_seconds != null &&
        (isAssignedStatus(ride.status) ||
          ride.status === RideStatus.DRIVER_ARRIVING) ? (
          <div>
            <dt>Pickup ETA</dt>
            <dd>{formatEta(ride.pickup_eta_seconds)}</dd>
          </div>
        ) : null}
        {ride.pickup_distance_km != null &&
        (isAssignedStatus(ride.status) ||
          ride.status === RideStatus.DRIVER_ARRIVING) ? (
          <div>
            <dt>Pickup distance</dt>
            <dd>{formatKm(ride.pickup_distance_km)}</dd>
          </div>
        ) : null}
        <div>
          <dt>Requested</dt>
          <dd>{formatWhen(ride.requested_at)}</dd>
        </div>
        {driverLocation ? (
          <div>
            <dt>Driver location</dt>
            <dd className="mono">
              {formatCoord(driverLocation.latitude)},{' '}
              {formatCoord(driverLocation.longitude)}
            </dd>
          </div>
        ) : null}
      </dl>
      {showCash ? <CashPaymentNotice compact /> : null}
      {extra}
    </div>
  )
}
