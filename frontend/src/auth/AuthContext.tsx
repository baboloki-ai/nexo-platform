import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'
import type { ReactNode } from 'react'

import { getMe } from '../api/users'
import { ApiError, toUserMessage } from '../api/client'
import type { User } from '../types/user'
import { closeAllSockets } from '../realtime/socket'
import {
  clearClientSession,
  getToken,
  setToken,
  setUnauthorizedHandler,
} from './session'

type AuthContextValue = {
  user: User | null
  ready: boolean
  restoreError: string | null
  loginWithToken: (token: string, user: User) => void
  logout: () => void
  retryRestore: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [ready, setReady] = useState(false)
  const [restoreError, setRestoreError] = useState<string | null>(null)
  const [restoreNonce, setRestoreNonce] = useState(0)

  const logout = useCallback(() => {
    closeAllSockets()
    clearClientSession()
    setUser(null)
    setRestoreError(null)
  }, [])

  const loginWithToken = useCallback((token: string, nextUser: User) => {
    setToken(token)
    setUser(nextUser)
    setRestoreError(null)
  }, [])

  const retryRestore = useCallback(() => {
    setReady(false)
    setRestoreError(null)
    setRestoreNonce((value) => value + 1)
  }, [])

  useEffect(() => {
    setUnauthorizedHandler(() => {
      closeAllSockets()
      setUser(null)
      setRestoreError(null)
    })
    return () => setUnauthorizedHandler(null)
  }, [])

  useEffect(() => {
    const token = getToken()
    if (!token) {
      setUser(null)
      setReady(true)
      return
    }

    let cancelled = false
    setReady(false)

    getMe()
      .then((me) => {
        if (cancelled) return
        setUser(me)
        setRestoreError(null)
        setReady(true)
      })
      .catch((error: unknown) => {
        if (cancelled) return
        if (error instanceof ApiError && error.status === 401) {
          clearClientSession()
          setUser(null)
          setRestoreError(null)
          setReady(true)
          return
        }
        setRestoreError(toUserMessage(error))
        setReady(true)
      })

    return () => {
      cancelled = true
    }
  }, [restoreNonce])

  const value = useMemo(
    () => ({
      user,
      ready,
      restoreError,
      loginWithToken,
      logout,
      retryRestore,
    }),
    [user, ready, restoreError, loginWithToken, logout, retryRestore],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}
