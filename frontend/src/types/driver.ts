import type { Vehicle } from './vehicle'

export type DriverPublicVehicle = {
  make: string
  model: string
  color: string
  registration_number: string
  verification_status?: string
}

export type DriverPublicIdentity = {
  display_name: string
  verification_status: string
  vehicle: DriverPublicVehicle | null
}

export type DriverProfile = {
  id: number
  display_name: string
  phone_number: string
  profile_photo_url: string | null
  verification_status: string | null
  availability_status: string | null
  current_latitude: number | null
  current_longitude: number | null
  last_seen: string | null
  created_at: string | null
  updated_at: string | null
  vehicle: Vehicle | null
}

export type DriverProfileUpdate = {
  display_name?: string
  phone_number?: string
  profile_photo_url?: string | null
}
