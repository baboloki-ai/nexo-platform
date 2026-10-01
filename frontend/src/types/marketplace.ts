import type { DriverResponse } from './ride'

export type DriverWalletLedgerEntry = {
  id: number
  driver_id: number
  ride_id: number | null
  entry_type: string
  amount: number
  balance_after: number
  created_at: string
}

export type DriverWallet = {
  driver_id: number
  available_balance: number
  minimum_balance: number
  meets_minimum: boolean
  updated_at: string | null
  ledger?: DriverWalletLedgerEntry[]
}

export type DriverPerformance = {
  completed_rides: number
  today_gross: number
  today_commission: number
  today_net: number
  wallet_balance: number
  wallet_minimum: number
  meets_wallet_minimum: boolean
  commission_rate: number
}

export type DemandCell = {
  latitude: number
  longitude: number
  count: number
}

export type DemandDriverPoint = {
  driver_id: number
  latitude: number
  longitude: number
  last_seen: string | null
  self: boolean
}

export type DriverDemand = {
  window_minutes: number
  cells: DemandCell[]
  online_drivers: DemandDriverPoint[]
}

export type DriverOpenRequest = {
  ride_id: number
  pickup_location: string
  pickup_latitude: number | null
  pickup_longitude: number | null
  destination: string
  destination_latitude: number | null
  destination_longitude: number | null
  passenger_current_offer: number | null
  passenger_offer_version: number
  trip_distance_km: number | null
  pickup_distance_km: number | null
  pickup_eta_seconds: number | null
  requested_at: string
  my_response: DriverResponse | null
  cash?: boolean
}
