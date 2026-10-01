import type { PassengerSocketEvent, SocketStatus } from '../types/websocket'
import { connectNexoSocket, type SocketHandle } from './socket'

type PassengerHandlers = {
  onEvent: (event: PassengerSocketEvent) => void
  onStatus: (status: SocketStatus) => void
}

export function connectPassengerSocket(
  passengerId: number,
  token: string,
  handlers: PassengerHandlers,
): SocketHandle {
  return connectNexoSocket(`/ws/passenger/${passengerId}`, token, {
    onStatus: handlers.onStatus,
    onEvent: (payload) => {
      const event = String(payload.event ?? '')
      handlers.onEvent({ ...payload, event } as PassengerSocketEvent)
    },
  })
}
