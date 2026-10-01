import { useEffect, useState } from 'react'

import { toUserMessage } from '../api/client'
import { getCounterOptions, rejectRide, respondToRide } from '../api/rides'
import type { DriverOpenRequest } from '../types/marketplace'
import { formatCurrency, formatEta, formatKm, formatWhen } from '../utils/format'
import { Button } from './Button'
import { Card } from './Card'
import { CashPaymentNotice } from './CashPaymentNotice'

export function DriverRequestCard({
  request,
  busy,
  canRespond = true,
  canAcceptNext = false,
  onResponded,
  onAcceptNext,
  onError,
}: {
  request: DriverOpenRequest
  busy: boolean
  canRespond?: boolean
  canAcceptNext?: boolean
  onResponded: () => Promise<void> | void
  onAcceptNext?: () => Promise<void> | void
  onError: (message: string) => void
}) {
  const [amounts, setAmounts] = useState<number[]>([])
  const [loadingOptions, setLoadingOptions] = useState(false)
  const offer = request.passenger_current_offer ?? 0
  const mine = request.my_response

  useEffect(() => {
    if (!canRespond) {
      setAmounts([])
      setLoadingOptions(false)
      return
    }
    let cancelled = false
    setLoadingOptions(true)
    void getCounterOptions(request.ride_id)
      .then((options) => {
        if (!cancelled) setAmounts(options.amounts)
      })
      .catch(() => {
        if (!cancelled) setAmounts([])
      })
      .finally(() => {
        if (!cancelled) setLoadingOptions(false)
      })
    return () => {
      cancelled = true
    }
  }, [canRespond, request.ride_id, request.passenger_offer_version, offer])

  async function acceptOffer() {
    try {
      await respondToRide(request.ride_id, {
        response_type: 'accept_passenger_offer',
      })
      await onResponded()
    } catch (err) {
      onError(toUserMessage(err))
    }
  }

  async function acceptAsNextRide() {
    try {
      await onAcceptNext?.()
    } catch (err) {
      onError(toUserMessage(err))
    }
  }

  async function counter(amount: number) {
    try {
      await respondToRide(request.ride_id, {
        response_type: 'counter_offer',
        amount,
      })
      await onResponded()
    } catch (err) {
      onError(toUserMessage(err))
    }
  }

  async function withdraw() {
    try {
      await rejectRide(request.ride_id)
      await onResponded()
    } catch (err) {
      onError(toUserMessage(err))
    }
  }

  return (
    <Card className="request-card">
      <p className="eyebrow">Ride request</p>
      <h2>Passenger offer {formatCurrency(offer)}</h2>
      <p className="muted">
        {canAcceptNext
          ? 'Accept this request as your Next Ride. Your current trip stays active and this ride stays accepted until you finish.'
          : 'Accepting means you are willing to take this passenger at their current offer. The passenger still chooses the driver.'}
      </p>
      <dl className="kv-grid">
        <div>
          <dt>Pickup</dt>
          <dd>{request.pickup_location}</dd>
        </div>
        <div>
          <dt>Destination</dt>
          <dd>{request.destination}</dd>
        </div>
        <div>
          <dt>Estimated trip distance</dt>
          <dd>{formatKm(request.trip_distance_km)}</dd>
        </div>
        <div>
          <dt>Pickup distance</dt>
          <dd>{formatKm(request.pickup_distance_km)}</dd>
        </div>
        <div>
          <dt>Pickup ETA</dt>
          <dd>{formatEta(request.pickup_eta_seconds)}</dd>
        </div>
        <div>
          <dt>Requested</dt>
          <dd>{formatWhen(request.requested_at)}</dd>
        </div>
      </dl>
      <CashPaymentNotice compact />
      {mine ? (
        <p className="meta">
          Your response: {mine.response_type === 'counter_offer' ? 'counter' : 'accept'}{' '}
          {formatCurrency(mine.amount)} ({mine.status})
        </p>
      ) : null}
      {canAcceptNext ? (
        <div className="btn-row wrap">
          <Button busy={busy} onClick={() => void acceptAsNextRide()}>
            Accept as Next Ride {formatCurrency(offer)}
          </Button>
        </div>
      ) : null}
      {canRespond ? (
        <>
          <div className="btn-row wrap">
            <Button busy={busy} onClick={() => void acceptOffer()}>
              ACCEPT {formatCurrency(offer)}
            </Button>
            {mine?.status === 'open' ? (
              <Button variant="ghost" busy={busy} onClick={() => void withdraw()}>
                Withdraw response
              </Button>
            ) : null}
          </div>
          <p className="eyebrow" style={{ marginTop: '0.85rem' }}>
            OFFER YOUR FARE
          </p>
          <p className="muted">Generated amounts only. Drivers cannot type a fare.</p>
          <div className="chip-row">
            {loadingOptions ? <p className="muted">Loading amounts…</p> : null}
            {amounts.map((amount) => (
              <Button
                key={amount}
                variant="ghost"
                disabled={busy}
                onClick={() => void counter(amount)}
              >
                {formatCurrency(amount)}
              </Button>
            ))}
          </div>
        </>
      ) : null}
    </Card>
  )
}
