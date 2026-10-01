import { NavLink } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import { Button } from './Button'
import { LiveBadge } from './StatusBadge'

export type HeaderNavItem = {
  to: string
  label: string
  end?: boolean
}

export function AppHeader({
  title,
  socketConnected,
  socketLabel,
  nav = [],
}: {
  title: string
  socketConnected: boolean
  socketLabel: string
  nav?: HeaderNavItem[]
}) {
  const { user, logout } = useAuth()

  return (
    <header className="app-header">
      <div className="brand-lockup">
        <span className="brand-mark">N</span>
        <div>
          <p className="brand-name">NEXO</p>
          <p className="brand-sub">{title}</p>
        </div>
      </div>
      {nav.length > 0 ? (
        <nav className="app-nav" aria-label="Primary">
          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                isActive ? 'nav-link is-active' : 'nav-link'
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      ) : null}
      <div className="header-meta">
        <LiveBadge connected={socketConnected} label={socketLabel} />
        {user ? (
          <div className="user-chip">
            <strong>{user.full_name}</strong>
            <span>{user.email}</span>
          </div>
        ) : null}
        <Button variant="ghost" onClick={logout}>
          Log out
        </Button>
      </div>
    </header>
  )
}
