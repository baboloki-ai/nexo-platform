import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { resetPassword } from '../../api/users'
import { toUserMessage } from '../../api/client'
import { Button } from '../../components/Button'
import { ErrorMessage } from '../../components/ErrorMessage'
import { Input } from '../../components/Input'

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') ?? ''

  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setMessage(null)

    if (!token) {
      setError('This password reset link is invalid or missing.')
      return
    }

    if (password.length < 8) {
      setError('Password must be at least 8 characters long.')
      return
    }

    if (password !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }

    setBusy(true)

    try {
      const response = await resetPassword(token, password)
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
              Create a new password and get back to your NEXO account.
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
          <h1 className="auth-title">Reset password</h1>
          <p className="muted">
            Choose a new password for your NEXO account.
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
              label="New password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              minLength={8}
            />

            <Input
              label="Confirm new password"
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              required
              minLength={8}
            />

            <Button type="submit" busy={busy} block>
              {busy ? 'Resetting…' : 'Reset password'}
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
