import { RideStatus, type Ride } from '../types/ride'

export const DRIVER_ACTIVE_ASSIGNED_STATUSES: readonly string[] = [
  RideStatus.ACCEPTED,
  RideStatus.DRIVER_ARRIVING,
  RideStatus.DRIVER_ARRIVED,
  RideStatus.IN_PROGRESS,
]

export function isActiveAssignedRide(status: string): boolean {
  return DRIVER_ACTIVE_ASSIGNED_STATUSES.includes(status)
}

export function isQueuedNextRide(ride: Ride): boolean {
  return ride.is_next_ride === true
}

export function selectActiveAssignedRide(
  rides: readonly Ride[],
  driverId: number,
  sessionStorageRideId: number | null = null,
): Ride | null {
  void sessionStorageRideId
  return (
    rides.find(
      (ride) =>
        isActiveAssignedRide(ride.status) &&
        ride.accepted_driver_id === driverId &&
        !isQueuedNextRide(ride) &&
        !(ride.shared_ride_with_id != null && ride.shared_ride_consent === true && ride.status === 'accepted'),
    ) ?? null
  )
}

export function selectNextRide(
  rides: readonly Ride[],
  driverId: number,
): Ride | null {
  return (
    rides.find(
      (ride) =>
        isQueuedNextRide(ride) &&
        ride.accepted_driver_id === driverId &&
        ride.status === RideStatus.ACCEPTED,
    ) ?? null
  )
}


