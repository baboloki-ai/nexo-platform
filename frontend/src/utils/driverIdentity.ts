import type { Ride } from '../types/ride'
import type { DriverPublicIdentity } from '../types/driver'

export function driverVerificationLabel(
  status: string | null | undefined,
): string {
  switch (status) {
    case 'approved':
      return 'Driver verified'
    case 'pending':
      return 'Driver awaiting verification'
    case 'rejected':
      return 'Driver not approved'
    case 'suspended':
      return 'Driver suspended'
    default:
      return 'Driver unverified'
  }
}

export function vehicleVerificationLabel(
  status: string | null | undefined,
): string {
  switch (status) {
    case 'approved':
      return 'Vehicle approved'
    case 'pending':
      return 'Vehicle pending review'
    case 'rejected':
      return 'Vehicle not approved'
    case 'suspended':
      return 'Vehicle suspended'
    default:
      return 'Vehicle not reviewed'
  }
}

export function assignedDriverIdentity(ride: Ride): DriverPublicIdentity | null {
  return ride.assigned_driver ?? null
}

export function assignedDriverName(ride: Ride): string | null {
  return ride.assigned_driver?.display_name ?? null
}

export function formatVehicleLine(
  vehicle: {
    make: string
    model: string
    color: string
    registration_number: string
  } | null | undefined,
): string | null {
  if (!vehicle) return null
  return `${vehicle.color} ${vehicle.make} ${vehicle.model} · ${vehicle.registration_number}`
}
