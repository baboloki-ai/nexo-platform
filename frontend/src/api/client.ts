import { getToken, notifyUnauthorized } from '../auth/session'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

const STATUS_FALLBACK: Record<number, string> = {
  400: 'The request could not be completed.',
  401: 'Your session has expired. Please sign in again.',
  403: 'You are not allowed to do that.',
  404: 'The requested resource was not found.',
  422: 'Some fields are invalid. Check your input and try again.',
  500: 'Something went wrong. Please try again.',
}

const UNSAFE_DETAIL =
  /traceback|sqlalchemy|psycopg|operationalerror|internal server error|jwt|bearer\s+[a-z0-9._-]|stack trace|\/app\/|\.py:|axioserror/i

function looksUnsafe(message: string): boolean {
  return UNSAFE_DETAIL.test(message)
}

function readDetail(data: unknown): string | null {
  if (data == null || typeof data !== 'object' || !('detail' in data)) {
    return null
  }

  const detail = (data as { detail: unknown }).detail
  if (typeof detail === 'string' && detail.trim()) {
    return detail
  }

  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (typeof item === 'string') return item
        if (item && typeof item === 'object' && 'msg' in item) {
          return String((item as { msg: unknown }).msg)
        }
        return null
      })
      .filter((part): part is string => Boolean(part))
    return parts.length > 0 ? parts.join(' ') : null
  }

  return null
}

export function toUserMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status >= 500 || looksUnsafe(error.message)) {
      return STATUS_FALLBACK[error.status] ?? 'Something went wrong. Please try again.'
    }
    return error.message
  }
  if (error instanceof Error && error.message) {
    if (looksUnsafe(error.message) || /failed with status code|network error/i.test(error.message)) {
      return 'Something went wrong. Please try again.'
    }
    return error.message
  }
  return 'Something went wrong. Please try again.'
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers)
  const token = getToken()
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const isFormBody = options.body instanceof URLSearchParams
  if (options.body && !isFormBody && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers })
  } catch {
    throw new ApiError(
      'Unable to reach NEXO. Check your connection and try again.',
      0,
    )
  }

  const isLogin = path === '/users/login'
  if (response.status === 401 && !isLogin) {
    notifyUnauthorized()
  }

  if (!response.ok) {
    let message =
      STATUS_FALLBACK[response.status] ??
      'Something went wrong. Please try again.'
    try {
      const data: unknown = await response.json()
      message = readDetail(data) ?? message
    } catch {
      // Keep the status fallback when the body is not JSON.
    }
    throw new ApiError(message, response.status)
  }

  if (response.status === 204) {
    return undefined as T
  }

  const text = await response.text()
  if (!text) {
    return undefined as T
  }

  return JSON.parse(text) as T
}

