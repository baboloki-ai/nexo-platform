import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { createPassenger } from '../../api/passengers'
import { createUser, getMe, login } from '../../api/users'
import { toUserMessage } from '../../api/client'
import { useAuth } from '../../auth/AuthContext'
import { setToken } from '../../auth/session'
import { Button } from '../../components/Button'
import { ErrorMessage } from '../../components/ErrorMessage'
import { Input } from '../../components/Input'
import type { UserRole } from '../../types/user'
import { isBotswanaPhone } from '../../utils/format'

export function RegisterPage() {
  const { loginWithToken } = useAuth()
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [phone, setPhone] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<UserRole>('passenger')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    if (!isBotswanaPhone(phone)) {
      setError('Enter a Botswana phone number, for example +267 71 123 456.')
      return
    }
    setBusy(true)
    try {
      await createUser({
        full_name: `${firstName.trim()} ${lastName.trim()}`.trim(),
        phone_number: phone.trim(),
        email: email.trim(),
        password,
        role,
      })

      const tokens = await login(email.trim(), password)
      setToken(tokens.access_token)
      const provisional = await getMe()

      if (role === 'passenger') {
        await createPassenger({
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          phone: phone.trim(),
          email: email.trim(),
        })
      }

      loginWithToken(tokens.access_token, provisional)
    } catch (err) {
      setError(toUserMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-shell auth-shell--register">
      <div className="auth-brand-panel" aria-hidden="true">
        <div className="auth-brand-panel-inner">
          <span className="auth-hero-mark">N</span>
          <div className="auth-brand-copyblock">
            <p className="auth-hero-name">NEXO</p>
            <p className="auth-hero-place">Rides in Gaborone</p>
            <p className="auth-hero-copy">
              Direct city travel — considered from the moment you request to the moment you arrive.
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
          <p className="eyebrow">Join NEXO</p>
          <h1 className="auth-title">Create an account</h1>
          <p className="muted">Passenger or driver — start riding in Gaborone.</p>
        </div>
        <ErrorMessage message={error} onDismiss={() => setError(null)} />
        <form className="stack" onSubmit={onSubmit}>
          <div className="field-row">
            <Input
              label="First name"
              value={firstName}
              onChange={(event) => setFirstName(event.target.value)}
              required
            />
            <Input
              label="Last name"
              value={lastName}
              onChange={(event) => setLastName(event.target.value)}
              required
            />
          </div>
          <Input
            label="Phone"
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            hint="Botswana number, for example +267 71 123 456"
            autoComplete="tel"
            required
          />
          <Input
            label="Email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            hint="Use a valid email address."
            required
          />
          <Input
            label="Password"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
          <fieldset className="role-fieldset">
            <legend>Account type</legend>
            <label className="choice">
              <input
                type="radio"
                name="role"
                checked={role === 'passenger'}
                onChange={() => setRole('passenger')}
              />
              Passenger
            </label>
            <label className="choice">
              <input
                type="radio"
                name="role"
                checked={role === 'driver'}
                onChange={() => setRole('driver')}
              />
              Driver
            </label>
          </fieldset>
          <Button type="submit" busy={busy} block>
            {busy ? 'Creating account…' : 'Create account'}
          </Button>
        </form>
        <p className="auth-footer">
          Already registered? <Link to="/login">Sign in</Link>
        </p>
      </div>
    </div>
  )
}
