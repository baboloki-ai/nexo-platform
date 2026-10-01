import { apiRequest } from './client'
import type { DriverProfile, DriverProfileUpdate } from '../types/driver'
import type {
  DriverDemand,
  DriverOpenRequest,
  DriverPerformance,
  DriverWallet,
  DriverWalletLedgerEntry,
} from '../types/marketplace'
import type { Ride } from '../types/ride'

export type DriverStatusResponse = {
  message: string
  status: string
}

export type DriverLocationResponse = {
  message: string
  latitude: number
  longitude: number
}

export function getDriverProfile(): Promise<DriverProfile> {
  return apiRequest<DriverProfile>('/drivers/me')
}

export function updateDriverProfile(
  payload: DriverProfileUpdate,
): Promise<DriverProfile> {
  return apiRequest<DriverProfile>('/drivers/me', {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function getDriverRides(): Promise<Ride[]> {
  return apiRequest<Ride[]>('/drivers/rides')
}

export function goOnline(): Promise<DriverStatusResponse> {
  return apiRequest<DriverStatusResponse>('/drivers/go-online', {
    method: 'PUT',
  })
}

export function goOffline(): Promise<DriverStatusResponse> {
  return apiRequest<DriverStatusResponse>('/drivers/go-offline', {
    method: 'PUT',
  })
}

export function updateDriverLocation(
  latitude: number,
  longitude: number,
  accuracy: number | null = null,
  speed: number | null = null,
  heading: number | null = null,
  timestamp: number | null = null,
): Promise<DriverLocationResponse> {
  return apiRequest<DriverLocationResponse>('/drivers/location', {
    method: 'PUT',
    body: JSON.stringify({
      latitude,
      longitude,
      accuracy,
      speed,
      heading,
      timestamp,
    }),
  })
}

export function getMarketplaceRequests(): Promise<DriverOpenRequest[]> {
  return apiRequest<DriverOpenRequest[]>('/drivers/requests')
}

export function getDriverWallet(): Promise<DriverWallet> {
  return apiRequest<DriverWallet>('/drivers/wallet')
}

export function getDriverWalletLedger(): Promise<DriverWalletLedgerEntry[]> {
  return apiRequest<DriverWalletLedgerEntry[]>('/drivers/wallet/ledger')
}

export function getDriverPerformance(): Promise<DriverPerformance> {
  return apiRequest<DriverPerformance>('/drivers/performance')
}

export function getDriverDemand(): Promise<DriverDemand> {
  return apiRequest<DriverDemand>('/drivers/demand')
}
