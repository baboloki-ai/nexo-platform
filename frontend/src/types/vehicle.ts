export type Vehicle = {
  id: number
  driver_id: number
  make: string
  model: string
  year: number
  color: string
  registration_number: string
  vehicle_type: string
  verification_status?: string
  created_at?: string | null
  updated_at?: string | null
}

export type VehicleCreate = {
  make: string
  model: string
  year: number
  color: string
  registration_number: string
  vehicle_type: string
}
