import type { Ride } from '../types/ride'
import { apiRequest } from './client'

export function getTrip(rideId: number): Promise<Ride> {
  return apiRequest<Ride>(`/trips/${rideId}`)
}
