import type { DriverSocketEvent, SocketStatus } from '../types/websocket'
import { connectNexoSocket, type SocketHandle } from './socket'

type DriverHandlers = {
  onEvent: (event: DriverSocketEvent) => void
  onStatus: (status: SocketStatus) => void
}

export function connectDriverSocket(
  userId: number,
  token: string,
  handlers: DriverHandlers,
): SocketHandle {
  return connectNexoSocket(`/ws/driver/${userId}`, token, {
    onStatus: handlers.onStatus,
    onEvent: (payload) => {
      const event = String(payload.event ?? '')
      handlers.onEvent({ ...payload, event } as DriverSocketEvent)
    },
  })
}
