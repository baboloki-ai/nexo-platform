export type UserRole = 'passenger' | 'driver'

export type VerificationStatus =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'suspended'

export type User = {
  id: number
  full_name: string
  phone_number: string
  email: string
  role: UserRole | string
  verification_status?: string | null
  profile_photo_url?: string | null
  created_at?: string | null
}

export type UserCreate = {
  full_name: string
  phone_number: string
  email: string
  password: string
  role: UserRole
}

export type LoginResponse = {
  access_token: string
  token_type: string
}

export function isApprovedDriver(status: string | null | undefined): boolean {
  return status === 'approved'
}
