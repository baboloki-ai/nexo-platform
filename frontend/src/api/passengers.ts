import type { Passenger, PassengerCreate } from '../types/passenger'
import { apiRequest } from './client'

export function createPassenger(payload: PassengerCreate): Promise<Passenger> {
  return apiRequest<Passenger>('/passengers/', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function getMyPassengers(): Promise<Passenger[]> {
  return apiRequest<Passenger[]>('/passengers/my')
}
