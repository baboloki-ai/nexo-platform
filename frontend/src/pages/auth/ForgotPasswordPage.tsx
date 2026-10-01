import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { forgotPassword } from '../../api/users'
import { toUserMessage } from '../../api/client'
import { Button } from '../../components/Button'
import { ErrorMessage } from '../../components/ErrorMessage'
import { Input } from '../../components/Input'

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setMessage(null)
    setBusy(true)

    try {
      const response = await forgotPassword(email.trim())
      setMessage(response.message)
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
              Get back on the road with secure access to your NEXO account.
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
          <p className="eyebrow">Account recovery</p>
          <h1 className="auth-title">Forgot password?</h1>
          <p className="muted">
            Enter the email address linked to your NEXO account and we&apos;ll
            send you a password reset link.
          </p>
        </div>

        <ErrorMessage message={error} onDismiss={() => setError(null)} />

        {message ? (
          <div className="stack">
            <p className="muted">{message}</p>
            <Link to="/login">Return to sign in</Link>
          </div>
        ) : (
          <form className="stack" onSubmit={onSubmit}>
            <Input
              label="Email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />

            <Button type="submit" busy={busy} block>
              {busy ? 'Sending…' : 'Send reset link'}
            </Button>
          </form>
        )}

        {!message && (
          <p className="auth-footer">
            Remember your password? <Link to="/login">Sign in</Link>
          </p>
        )}
      </div>
    </div>
  )
}
