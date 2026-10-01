import { rideStatusLabel, rideStatusTone } from '../constants/rideStatus'

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`badge badge-${rideStatusTone(status)}`}>
      {rideStatusLabel(status)}
    </span>
  )
}

export function LiveBadge({
  connected,
  label,
}: {
  connected: boolean
  label: string
}) {
  return (
    <span className={`live-dot ${connected ? 'is-on' : 'is-off'}`}>
      <span className="live-dot-mark" />
      {label}
    </span>
  )
}
