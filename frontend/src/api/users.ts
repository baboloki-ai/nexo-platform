import type { LoginResponse, User, UserCreate } from '../types/user'
import { apiRequest } from './client'

export function createUser(payload: UserCreate): Promise<User> {
  return apiRequest<User>('/users/', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function login(email: string, password: string): Promise<LoginResponse> {
  const body = new URLSearchParams()
  body.set('username', email)
  body.set('password', password)

  return apiRequest<LoginResponse>('/users/login', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body,
  })
}

export function getMe(): Promise<User> {
  return apiRequest<User>('/users/me')
}

export function forgotPassword(email: string): Promise<{ message: string }> {
  return apiRequest<{ message: string }>('/users/forgot-password', {
    method: 'POST',
    body: JSON.stringify({ email }),
  })
}

export function resetPassword(
  token: string,
  newPassword: string,
): Promise<{ message: string }> {
  return apiRequest<{ message: string }>('/users/reset-password', {
    method: 'POST',
    body: JSON.stringify({
      token,
      new_password: newPassword,
    }),
  })
}
