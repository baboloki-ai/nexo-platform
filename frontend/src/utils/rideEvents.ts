import type { SocketStatus } from '../types/websocket'

export function extractRideId(payload: Record<string, unknown>): number | null {
  const direct = payload.ride_id
  if (typeof direct === 'number' && Number.isInteger(direct) && direct > 0) {
    return direct
  }
  if (typeof direct === 'string' && /^\d+$/.test(direct)) {
    const parsed = Number(direct)
    return parsed > 0 ? parsed : null
  }

  const message = payload.message
  if (typeof message === 'string') {
    const match = message.match(/(?:ride|trip)\s*#?\s*(\d+)/i)
    if (match) {
      const parsed = Number(match[1])
      return parsed > 0 ? parsed : null
    }
  }

  return null
}

export function socketStatusLabel(status: SocketStatus): string {
  switch (status) {
    case 'connected':
      return 'Live'
    case 'connecting':
      return 'Connecting'
    case 'unauthorized':
      return 'Not connected'
    case 'disconnected':
      return 'Reconnecting'
    default:
      return 'Offline'
  }
}
