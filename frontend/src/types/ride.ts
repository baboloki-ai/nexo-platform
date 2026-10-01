import type { DriverPublicIdentity } from './driver'
import type { Payment } from './payment'

export const RideStatus = {
  PENDING: 'pending',
  PENDING_DRIVER_ACCEPTANCE: 'pending_driver_acceptance',
  ACCEPTED: 'accepted',
  DRIVER_ARRIVING: 'driver_arriving',
  DRIVER_ARRIVED: 'driver_arrived',
  IN_PROGRESS: 'in_progress',
  COMPLETED: 'completed',
  CANCELLED_BY_PASSENGER: 'cancelled_by_passenger',
  CANCELLED_BY_DRIVER: 'cancelled_by_driver',
  EXPIRED: 'expired',
  NO_DRIVER_AVAILABLE: 'no_driver_available',
} as const

export type RideStatusValue = (typeof RideStatus)[keyof typeof RideStatus]

export type RideSystemMessage = {
  source: string
  label?: string
  body: string
  created_at: string | null
}

export type Ride = {
  id: number
  passenger_id: number
  pickup_location: string
  pickup_latitude: number | null
  pickup_longitude: number | null
  destination: string
  destination_latitude: number | null
  destination_longitude: number | null
  proposed_fare: number
  recommended_fare?: number | null
  passenger_current_offer?: number | null
  passenger_offer_version?: number
  agreed_fare?: number | null
  trip_distance_km?: number | null
  trip_distance_source?: string | null
  trip_distance_is_road_distance?: boolean
  pickup_distance_km?: number | null
  pickup_eta_seconds?: number | null
  selected_at?: string | null
  completed_at?: string | null
  status: string
  accepted_driver_id: number | null
  is_next_ride?: boolean
  shared_ride_with_id?: number | null
  shared_ride_consent?: boolean
  requested_at: string
  assigned_driver?: DriverPublicIdentity | null
  payment?: Payment | null
  system_messages?: RideSystemMessage[]
}

export type RideCreate = {
  pickup_location: string
  pickup_latitude: number
  pickup_longitude: number
  destination: string
  destination_latitude: number
  destination_longitude: number
  proposed_fare: number
}

export type FareQuote = {
  estimated_trip_distance_km: number | null
  distance_source: string
  is_road_distance: boolean
  recommended_fare: number
  minimum_offer: number
  base_fare: number
  fare_per_km: number
  offer_options: number[]
}

export type PassengerOfferAction = 'increase' | 'maintain'

export type DriverResponseType =
  | 'accept_passenger_offer'
  | 'counter_offer'

export type DriverResponseStatus =
  | 'open'
  | 'selected'
  | 'closed_loser'
  | 'expired'
  | 'withdrawn'

export type DriverResponse = {
  id: number
  ride_id: number
  driver_id: number
  response_type: DriverResponseType | string
  amount: number
  status: DriverResponseStatus | string
  passenger_offer_version_at_submit: number
  passenger_offer_amount_at_submit: number
  pickup_distance_km: number | null
  pickup_eta_seconds: number | null
  created_at: string
  expires_at: string | null
  responded_at: string | null
  driver?: DriverPublicIdentity | null
}

export type NegotiationEvent = {
  id: number
  ride_id: number
  actor_type: string
  actor_user_id: number | null
  driver_id: number | null
  action: string
  amount: number | null
  resulting_ride_status: string | null
  resulting_response_status: string | null
  created_at: string
}

export type CounterOfferOptions = {
  ride_id: number
  passenger_current_offer: number
  passenger_offer_version: number
  amounts: number[]
}

export const ACTIVE_RIDE_STATUSES: readonly string[] = [
  RideStatus.PENDING,
  RideStatus.PENDING_DRIVER_ACCEPTANCE,
  RideStatus.ACCEPTED,
  RideStatus.DRIVER_ARRIVING,
  RideStatus.DRIVER_ARRIVED,
  RideStatus.IN_PROGRESS,
]

export const PASSENGER_CANCELLABLE_STATUSES: readonly string[] = [
  RideStatus.PENDING,
  RideStatus.PENDING_DRIVER_ACCEPTANCE,
  RideStatus.ACCEPTED,
  RideStatus.DRIVER_ARRIVING,
  RideStatus.DRIVER_ARRIVED,
]

export const DRIVER_CANCELLABLE_STATUSES: readonly string[] = [
  RideStatus.ACCEPTED,
  RideStatus.DRIVER_ARRIVING,
  RideStatus.DRIVER_ARRIVED,
]

export function isActiveRide(status: string): boolean {
  return ACTIVE_RIDE_STATUSES.includes(status)
}

export function canPassengerCancel(status: string): boolean {
  return PASSENGER_CANCELLABLE_STATUSES.includes(status)
}

export function canDriverCancel(status: string): boolean {
  return DRIVER_CANCELLABLE_STATUSES.includes(status)
}

export function isSearchingStatus(status: string): boolean {
  return (
    status === RideStatus.PENDING ||
    status === RideStatus.PENDING_DRIVER_ACCEPTANCE
  )
}

export function isAssignedStatus(status: string): boolean {
  return status === RideStatus.ACCEPTED
}

export function isEnRouteStatus(status: string): boolean {
  return (
    status === RideStatus.DRIVER_ARRIVING ||
    status === RideStatus.DRIVER_ARRIVED ||
    status === RideStatus.IN_PROGRESS
  )
}

export function isCompletedStatus(status: string): boolean {
  return status === RideStatus.COMPLETED
}

export function isHistoricalRide(status: string): boolean {
  return !isActiveRide(status)
}
