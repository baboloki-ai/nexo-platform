import { apiRequest } from './client'

export type VapidPublicKeyResponse = {
  vapid_public_key: string
}

export type PushSubscriptionPayload = {
  endpoint: string
  keys: {
    p256dh: string
    auth: string
  }
}

export type PushSubscriptionResponse = {
  driver_id: number
  endpoint: string
}

export function getVapidPublicKey(): Promise<VapidPublicKeyResponse> {
  return apiRequest<VapidPublicKeyResponse>('/drivers/push/vapid-public-key')
}

export function registerPushSubscription(
  payload: PushSubscriptionPayload,
): Promise<PushSubscriptionResponse> {
  return apiRequest<PushSubscriptionResponse>('/drivers/push/subscriptions', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
