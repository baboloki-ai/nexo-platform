import { RideStatus } from '../types/ride'

export function rideUpdateMessage(status: string): string {
  switch (status) {
    case RideStatus.PENDING:
    case RideStatus.PENDING_DRIVER_ACCEPTANCE:
      return 'Still looking for a driver.'
    case RideStatus.ACCEPTED:
      return 'Driver assigned.'
    case RideStatus.DRIVER_ARRIVING:
      return 'Your driver is on the way.'
    case RideStatus.DRIVER_ARRIVED:
      return 'Your driver has arrived.'
    case RideStatus.IN_PROGRESS:
      return 'Your trip is in progress.'
    case RideStatus.COMPLETED:
      return 'Your trip is complete.'
    case RideStatus.CANCELLED_BY_PASSENGER:
      return 'This ride was cancelled.'
    case RideStatus.CANCELLED_BY_DRIVER:
      return 'The driver cancelled this ride.'
    case RideStatus.EXPIRED:
      return 'This ride offer expired.'
    case RideStatus.NO_DRIVER_AVAILABLE:
      return 'No drivers are available right now.'
    default:
      return 'Ride updated.'
  }
}

const LABELS: Record<string, string> = {
  [RideStatus.PENDING]: 'Searching for a driver',
  [RideStatus.PENDING_DRIVER_ACCEPTANCE]: 'Waiting for driver to accept',
  [RideStatus.ACCEPTED]: 'Driver assigned',
  [RideStatus.DRIVER_ARRIVING]: 'Driver arriving',
  [RideStatus.DRIVER_ARRIVED]: 'Driver arrived',
  [RideStatus.IN_PROGRESS]: 'Trip in progress',
  [RideStatus.COMPLETED]: 'Trip completed',
  [RideStatus.CANCELLED_BY_PASSENGER]: 'Cancelled by passenger',
  [RideStatus.CANCELLED_BY_DRIVER]: 'Cancelled by driver',
  [RideStatus.EXPIRED]: 'Expired',
  [RideStatus.NO_DRIVER_AVAILABLE]: 'No driver available',
}

export function rideStatusLabel(status: string): string {
  return LABELS[status] ?? status.replaceAll('_', ' ')
}

export function rideStatusTone(
  status: string,
): 'neutral' | 'info' | 'ok' | 'warn' | 'danger' {
  switch (status) {
    case RideStatus.COMPLETED:
      return 'ok'
    case RideStatus.NO_DRIVER_AVAILABLE:
    case RideStatus.CANCELLED_BY_PASSENGER:
    case RideStatus.CANCELLED_BY_DRIVER:
    case RideStatus.EXPIRED:
      return 'danger'
    case RideStatus.PENDING:
    case RideStatus.PENDING_DRIVER_ACCEPTANCE:
      return 'warn'
    case RideStatus.ACCEPTED:
    case RideStatus.DRIVER_ARRIVING:
    case RideStatus.DRIVER_ARRIVED:
    case RideStatus.IN_PROGRESS:
      return 'info'
    default:
      return 'neutral'
  }
}
