import { useEffect, useState } from 'react'

import { getDriverPerformance, getDriverWallet } from '../../api/drivers'
import { toUserMessage } from '../../api/client'
import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { LoadingState } from '../../components/LoadingState'
import { MIN_DRIVER_WALLET } from '../../constants/fare'
import { useDriver } from '../../driver/DriverContext'
import type { DriverPerformance, DriverWallet } from '../../types/marketplace'
import { formatCurrency, formatWhen } from '../../utils/format'

function ledgerLabel(entryType: string): string {
  switch (entryType) {
    case 'launch_seed':
      return 'Launch seed'
    case 'credit':
      return 'Credit / top-up'
    case 'commission':
      return 'NEXO commission (8%)'
    default:
      return entryType
  }
}

export function DriverPerformancePage() {
  const { setError } = useDriver()
  const [performance, setPerformance] = useState<DriverPerformance | null>(null)
  const [wallet, setWallet] = useState<DriverWallet | null>(null)
  const [loading, setLoading] = useState(true)
  const [showTopUp, setShowTopUp] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    void Promise.all([getDriverPerformance(), getDriverWallet()])
      .then(([nextPerformance, nextWallet]) => {
        if (cancelled) return
        setPerformance(nextPerformance)
        setWallet(nextWallet)
      })
      .catch((err) => {
        if (!cancelled) setError(toUserMessage(err))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [setError])

  if (loading) return <LoadingState message="Loading performance…" />

  const ledger = wallet?.ledger ?? []

  return (
    <>
      <Card className="hero-card">
        <p className="eyebrow">Performance</p>
        <h2>Today and wallet</h2>
        <p className="muted">
          Gross is the agreed cash fare. NEXO commission (8%) is deducted from
          the wallet after a completed trip. Net is gross minus that commission.
        </p>
      </Card>
      <Card>
        <p className="eyebrow">Wallet</p>
        <h2>{formatCurrency(wallet?.available_balance ?? 0)}</h2>
        <p className="muted">
          Minimum operating balance: {formatCurrency(wallet?.minimum_balance ?? MIN_DRIVER_WALLET)}.
        </p>
        {wallet && !wallet.meets_minimum ? (
          <div className="verify-banner">
            <p>
              Your wallet balance is zero or negative. Contact
              NEXO support to top up before going online.
            </p>
          </div>
        ) : (
          <p className="muted">Ready for marketplace requests.</p>
        )}
        <Button variant="secondary" onClick={() => setShowTopUp((open) => !open)}>
          Contact NEXO Support
        </Button>
        {showTopUp ? (
          <div className="top-up-note">
            <p className="eyebrow">Contact NEXO Support</p>
            <p>
              Contact NEXO support to top up this wallet. There is no in-app
              payment or card checkout in this pilot.
            </p>
            <p className="muted">
              After support credits the wallet, refresh this page to see the
              new balance and ledger entry.
            </p>
          </div>
        ) : null}
      </Card>
      <Card>
        <dl className="kv-grid">
          <div>
            <dt>Completed rides</dt>
            <dd>{performance?.completed_rides ?? 0}</dd>
          </div>
          <div>
            <dt>Today gross (agreed fares)</dt>
            <dd>{formatCurrency(performance?.today_gross ?? 0)}</dd>
          </div>
          <div>
            <dt>NEXO commission (8%)</dt>
            <dd>{formatCurrency(performance?.today_commission ?? 0)}</dd>
          </div>
          <div>
            <dt>Today net</dt>
            <dd>{formatCurrency(performance?.today_net ?? 0)}</dd>
          </div>
        </dl>
      </Card>
      <Card>
        <p className="eyebrow">Ledger</p>
        <h2>Transaction history</h2>
        {ledger.length === 0 ? (
          <p className="muted">No wallet movements yet.</p>
        ) : (
          <ul className="ledger-list">
            {ledger.map((entry) => (
              <li key={entry.id}>
                <div>
                  <strong>{ledgerLabel(entry.entry_type)}</strong>
                  <p className="meta">
                    {formatWhen(entry.created_at)}
                    {entry.ride_id != null ? ` · ride ${entry.ride_id}` : ''}
                  </p>
                </div>
                <div>
                  <strong>{formatCurrency(entry.amount)}</strong>
                  <p className="meta">
                    Balance {formatCurrency(entry.balance_after)}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  )
}
