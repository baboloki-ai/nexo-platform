import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { useAuth } from './AuthContext'

function dashboardPath(role: string): string {
  return role === 'driver' ? '/driver' : '/passenger'
}

export function RequireAuth({
  role,
  children,
}: {
  role: 'passenger' | 'driver'
  children: ReactNode
}) {
  const { user } = useAuth()
  const location = useLocation()

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  if (user.role !== role) {
    return <Navigate to={dashboardPath(user.role)} replace />
  }

  return children
}

export function GuestOnly({ children }: { children: ReactNode }) {
  const { user } = useAuth()

  if (user) {
    return <Navigate to={dashboardPath(user.role)} replace />
  }

  return children
}
