import type {
  CounterOfferOptions,
  DriverResponse,
  FareQuote,
  NegotiationEvent,
  PassengerOfferAction,
  Ride,
  RideCreate,
} from '../types/ride'
import { apiRequest } from './client'

export function quoteFare(payload: {
  pickup_latitude: number
  pickup_longitude: number
  destination_latitude: number
  destination_longitude: number
}): Promise<FareQuote> {
  return apiRequest<FareQuote>('/rides/quote', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function createRide(payload: RideCreate): Promise<Ride> {
  return apiRequest<Ride>('/rides/', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function getMyRides(): Promise<Ride[]> {
  return apiRequest<Ride[]>('/rides/my')
}

export function updatePassengerOffer(
  rideId: number,
  payload: {
    action: PassengerOfferAction
    amount?: number
    passenger_offer_version?: number
  },
): Promise<Ride> {
  return apiRequest<Ride>(`/rides/${rideId}/offer`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function getCounterOptions(rideId: number): Promise<CounterOfferOptions> {
  return apiRequest<CounterOfferOptions>(`/rides/${rideId}/counter-options`)
}

export function respondToRide(
  rideId: number,
  payload: {
    response_type: 'accept_passenger_offer' | 'counter_offer'
    amount?: number
  },
): Promise<Ride> {
  return apiRequest<Ride>(`/rides/${rideId}/respond`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function getRideResponses(rideId: number): Promise<DriverResponse[]> {
  return apiRequest<DriverResponse[]>(`/rides/${rideId}/responses`)
}

export function getNegotiationHistory(
  rideId: number,
): Promise<NegotiationEvent[]> {
  return apiRequest<NegotiationEvent[]>(`/rides/${rideId}/negotiation`)
}

export function selectDriver(
  rideId: number,
  responseId: number,
): Promise<Ride> {
  return apiRequest<Ride>(`/rides/${rideId}/select`, {
    method: 'PUT',
    body: JSON.stringify({ response_id: responseId }),
  })
}

export function ignoreDriverResponse(
  rideId: number,
  responseId: number,
): Promise<Ride> {
  return apiRequest<Ride>(`/rides/${rideId}/responses/${responseId}/ignore`, {
    method: 'PUT',
  })
}

export function acceptRide(rideId: number): Promise<Ride> {
  return apiRequest<Ride>(`/rides/${rideId}/accept`, {
    method: 'PUT',
  })
}

export function acceptNextRide(rideId: number): Promise<Ride> {
  return apiRequest<Ride>(`/rides/${rideId}/accept-next`, {
    method: 'PUT',
  })
}

export function rejectRide(rideId: number): Promise<{ message: string }> {
  return apiRequest<{ message: string }>(`/rides/${rideId}/reject`, {
    method: 'PUT',
  })
}

export function arriveAtPickup(rideId: number): Promise<Ride> {
  return apiRequest<Ride>(`/rides/${rideId}/arrive`, {
    method: 'PUT',
  })
}

export function markDriverArrived(rideId: number): Promise<Ride> {
  return apiRequest<Ride>(`/rides/${rideId}/driver-arrived`, {
    method: 'PUT',
  })
}

export function startRide(rideId: number): Promise<Ride> {
  return apiRequest<Ride>(`/rides/${rideId}/start`, {
    method: 'PUT',
  })
}

export function completeRide(rideId: number): Promise<Ride> {
  return apiRequest<Ride>(`/rides/${rideId}/complete`, {
    method: 'PUT',
  })
}

export function cancelRide(rideId: number): Promise<Ride> {
  return apiRequest<Ride>(`/rides/${rideId}/cancel`, {
    method: 'PUT',
  })
}

export function getSharedRideCandidates(rideId: number): Promise<Ride[]> {
  return apiRequest<Ride[]>(`/rides/${rideId}/shared-candidates`)
}

export function proposeSharedRide(
  rideId: number,
  candidateId: number,
): Promise<Ride> {
  return apiRequest<Ride>(
    `/rides/${rideId}/shared-candidates/${candidateId}/propose`,
    { method: 'POST' },
  )
}

export function consentToSharedRide(
  rideId: number,
  consent: boolean,
): Promise<Ride> {
  return apiRequest<Ride>(`/rides/${rideId}/shared-consent`, {
    method: 'POST',
    body: JSON.stringify({ consent }),
  })
}
