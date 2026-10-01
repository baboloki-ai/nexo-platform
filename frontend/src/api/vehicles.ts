import type { Vehicle, VehicleCreate } from '../types/vehicle'
import { apiRequest } from './client'

export function getMyVehicles(): Promise<Vehicle[]> {
  return apiRequest<Vehicle[]>('/vehicles/my')
}

export function createVehicle(payload: VehicleCreate): Promise<Vehicle> {
  return apiRequest<Vehicle>('/vehicles/', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
