import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { getMe, login } from '../../api/users'
import { toUserMessage } from '../../api/client'
import { useAuth } from '../../auth/AuthContext'
import { setToken } from '../../auth/session'
import { Button } from '../../components/Button'
import { ErrorMessage } from '../../components/ErrorMessage'
import { Input } from '../../components/Input'

export function LoginPage() {
  const { loginWithToken } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const tokens = await login(email.trim(), password)
      setToken(tokens.access_token)
      const user = await getMe()
      loginWithToken(tokens.access_token, user)
    } catch (err) {
      setError(toUserMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-shell">
      <div className="auth-brand-panel" aria-hidden="true">
        <div className="auth-brand-panel-inner">
          <span className="auth-hero-mark">N</span>
          <div className="auth-brand-copyblock">
            <p className="auth-hero-name">NEXO</p>
            <p className="auth-hero-place">Rides in Gaborone</p>
            <p className="auth-hero-copy">
              Direct city travel â€” considered from the moment you request to the moment you arrive.
            </p>
          </div>
        </div>
      </div>
      <div className="auth-card">
        <div className="brand-lockup">
          <span className="brand-mark">N</span>
          <div>
            <p className="brand-name">NEXO</p>
            <p className="brand-sub">Rides in Gaborone</p>
          </div>
        </div>
        <div className="auth-intro">
          <p className="eyebrow">Welcome back</p>
          <h1 className="auth-title">Sign in</h1>
          <p className="muted">Enter your email and password to continue.</p>
        </div>
        <ErrorMessage message={error} onDismiss={() => setError(null)} />
        <form className="stack" onSubmit={onSubmit}>
          <Input
            label="Email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
          <Input
            label="Password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
          <div className="auth-forgot-link">
            <Link to="/forgot-password">Forgot password?</Link>
          </div>
          <Button type="submit" busy={busy} block>
            {busy ? 'Signing inâ€¦' : 'Sign in'}
          </Button>
        </form>
        <p className="auth-footer">
          New to NEXO? <Link to="/register">Create an account</Link>
        </p>
      </div>
    </div>
  )
}

