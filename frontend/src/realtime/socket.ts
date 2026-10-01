import type { SocketStatus } from '../types/websocket'

type SocketHandlers = {
  onEvent: (payload: Record<string, unknown>) => void
  onStatus: (status: SocketStatus) => void
}

export type SocketHandle = {
  close: () => void
}

const openHandles = new Set<SocketHandle>()

export function closeAllSockets(): void {
  for (const handle of openHandles) {
    handle.close()
  }
  openHandles.clear()
}

export function connectNexoSocket(
  path: string,
  token: string,
  handlers: SocketHandlers,
): SocketHandle {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = `${protocol}//${window.location.host}${path}?token=${encodeURIComponent(token)}`

  let closedByUser = false
  let socket: WebSocket | null = null
  let retryTimer: number | null = null
  let attempts = 0

  const clearRetry = () => {
    if (retryTimer != null) {
      window.clearTimeout(retryTimer)
      retryTimer = null
    }
  }

  const open = () => {
    if (closedByUser) return
    handlers.onStatus('connecting')
    const next = new WebSocket(url)
    socket = next

    next.onopen = () => {
      attempts = 0
      handlers.onStatus('connected')
    }

    next.onmessage = (event) => {
      try {
        const parsed: unknown = JSON.parse(String(event.data))
        if (parsed && typeof parsed === 'object') {
          handlers.onEvent(parsed as Record<string, unknown>)
        }
      } catch {
        // Ignore malformed frames; do not surface stack traces.
      }
    }

    next.onclose = (event) => {
      if (socket === next) {
        socket = null
      }
      if (closedByUser) {
        handlers.onStatus('disconnected')
        return
      }
      if (event.code === 1008) {
        handlers.onStatus('unauthorized')
        return
      }
      handlers.onStatus('disconnected')
      const delay = Math.min(1000 * 2 ** attempts, 15000)
      attempts += 1
      retryTimer = window.setTimeout(open, delay)
    }

    next.onerror = () => {
      // onclose handles reconnect and user-facing status.
    }
  }

  open()

  const handle: SocketHandle = {
    close: () => {
      closedByUser = true
      clearRetry()
      openHandles.delete(handle)
      if (socket && socket.readyState < WebSocket.CLOSING) {
        socket.close()
      }
      socket = null
    },
  }

  openHandles.add(handle)
  return handle
}
