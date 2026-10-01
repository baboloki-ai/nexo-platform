import type { DriverPublicIdentity } from '../types/driver'
import {
  driverVerificationLabel,
  formatVehicleLine,
  vehicleVerificationLabel,
} from '../utils/driverIdentity'

export function DriverIdentityCard({
  identity,
  statusLabel,
  liveLocation,
}: {
  identity: DriverPublicIdentity
  statusLabel?: string
  liveLocation?: string | null
}) {
  const driverVerified = identity.verification_status === 'approved'
  const vehicleLine = formatVehicleLine(identity.vehicle)
  const vehicleStatus = identity.vehicle?.verification_status
  const vehicleApproved = vehicleStatus === 'approved'

  return (
    <div className="driver-card">
      <p className="eyebrow">Your driver</p>
      <div className="driver-card-head">
        <div className="driver-avatar" aria-hidden="true">
          {identity.display_name.trim().charAt(0).toUpperCase() || 'D'}
        </div>
        <div>
          <h3 className="driver-name">{identity.display_name}</h3>
          <span className={`status-pill ${driverVerified ? 'is-ok' : ''}`}>
            {driverVerificationLabel(identity.verification_status)}
          </span>
        </div>
      </div>
      {vehicleLine ? (
        <dl className="kv-grid">
          <div>
            <dt>Vehicle</dt>
            <dd>
              {identity.vehicle?.make} {identity.vehicle?.model}
            </dd>
          </div>
          <div>
            <dt>Colour</dt>
            <dd>{identity.vehicle?.color}</dd>
          </div>
          <div>
            <dt>Registration</dt>
            <dd className="mono">{identity.vehicle?.registration_number}</dd>
          </div>
          <div>
            <dt>Vehicle review</dt>
            <dd>
              <span className={`status-pill ${vehicleApproved ? 'is-ok' : ''}`}>
                {vehicleVerificationLabel(vehicleStatus)}
              </span>
            </dd>
          </div>
          {statusLabel ? (
            <div>
              <dt>Ride status</dt>
              <dd>{statusLabel}</dd>
            </div>
          ) : null}
        </dl>
      ) : (
        <p className="muted">Vehicle details will appear once on file.</p>
      )}
      {liveLocation ? <p className="mono">{liveLocation}</p> : null}
    </div>
  )
}
