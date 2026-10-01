export type SocketStatus =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'disconnected'
  | 'unauthorized'

export type ConnectedEvent = {
  event: 'connected'
  message?: string
}

export type MarketplaceRequestCreatedEvent = {
  event: 'marketplace_request_created'
  event_id: string
  ride_id: number
  passenger_offer_version: number
  passenger_current_offer: number
  pickup: string
  destination: string
  trip_distance_km: number | null
  pickup_distance_km: number | null
  pickup_eta_seconds: number | null
}

export type PassengerOfferUpdatedEvent = {
  event: 'passenger_offer_updated'
  event_id: string
  ride_id: number
  passenger_offer_version: number
  passenger_current_offer: number
  action: string
}

export type DriverResponseReceivedEvent = {
  event: 'driver_response_received'
  event_id: string
  ride_id: number
  passenger_offer_version: number
  response_id: number
  driver_id: number
  response_type: string
  amount: number
  pickup_distance_km: number | null
  pickup_eta_seconds: number | null
  driver?: unknown
}

export type DriverResponseWithdrawnEvent = {
  event: 'driver_response_withdrawn'
  event_id: string
  ride_id: number
  passenger_offer_version: number
  response_id: number | null
  driver_id: number
}

export type DriverResponseExpiredEvent = {
  event: 'driver_response_expired'
  event_id: string
  ride_id: number
  passenger_offer_version: number
  response_id: number
  driver_id: number
}

export type RideAgreedEvent = {
  event: 'ride_agreed'
  event_id: string
  ride_id: number
  passenger_offer_version: number
  driver_id: number
  agreed_fare: number
  response_id: number
}

export type MarketplaceRequestClosedEvent = {
  event: 'marketplace_request_closed'
  event_id: string
  ride_id: number
  reason: string
  won: boolean
  agreed_fare: number | null
  selected_driver_id: number | null
}

export type RideOfferEvent = {
  event: 'ride_offer'
  ride_id: number
  pickup: string
  destination: string
  fare: number
}

export type RideAcceptedEvent = {
  event: 'ride_accepted'
  ride_id: number
  driver_id: number
  message?: string
}

export type NoDriverAvailableEvent = {
  event: 'no_driver_available'
  ride_id: number
  message?: string
}

export type DriverLocationEvent = {
  event: 'driver_location'
  driver_id: number
  latitude: number
  longitude: number
}

export type NotificationEvent = {
  event: 'notification'
  message: string
  ride_id?: number
}

export type PaymentUpdatedEvent = {
  event: 'payment_updated'
  ride_id: number
  payment_id: number
  status: string
}

export type UnknownSocketEvent = {
  event: string
  [key: string]: unknown
}

export type PassengerSocketEvent =
  | ConnectedEvent
  | RideAcceptedEvent
  | RideAgreedEvent
  | NoDriverAvailableEvent
  | DriverLocationEvent
  | DriverResponseReceivedEvent
  | DriverResponseWithdrawnEvent
  | DriverResponseExpiredEvent
  | PaymentUpdatedEvent
  | NotificationEvent
  | UnknownSocketEvent

export type DriverSocketEvent =
  | ConnectedEvent
  | RideOfferEvent
  | MarketplaceRequestCreatedEvent
  | PassengerOfferUpdatedEvent
  | DriverResponseWithdrawnEvent
  | DriverResponseExpiredEvent
  | MarketplaceRequestClosedEvent
  | PaymentUpdatedEvent
  | NotificationEvent
  | UnknownSocketEvent
