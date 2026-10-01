import { useEffect, useRef, useState } from 'react'

import { toUserMessage } from '../api/client'
import {
  consentToSharedRide,
  getSharedRideCandidates,
  proposeSharedRide,
} from '../api/rides'
import { RideStatus, type Ride } from '../types/ride'
import { formatCurrency, formatPlace } from '../utils/format'
import { Button } from './Button'
import { Card } from './Card'

const CANDIDATE_POLL_MS = 5000

function isAwaitingSharedConsent(ride: Ride): boolean {
  return ride.shared_ride_with_id != null && ride.shared_ride_consent === false
}

function isSharedRideConfirmed(ride: Ride): boolean {
  return ride.shared_ride_with_id != null && ride.shared_ride_consent === true
}

function candidateFare(candidate: Ride): { label: string; amount: number } | null {
  if (candidate.agreed_fare != null && Number.isFinite(Number(candidate.agreed_fare))) {
    return { label: 'Agreed fare', amount: Number(candidate.agreed_fare) }
  }
  const proposed = candidate.passenger_current_offer ?? candidate.proposed_fare
  if (proposed != null && Number.isFinite(Number(proposed))) {
    return { label: 'Proposed fare', amount: Number(proposed) }
  }
  return null
}

export function DriverSharedRideSection({
  ride,
  disabled,
  onProposed,
  onError,
}: {
  ride: Ride
  disabled: boolean
  onProposed: (updated: Ride) => Promise<Ride>
  onError: (message: string) => void
}) {
  const [candidate, setCandidate] = useState<Ride | null>(null)
  const [asking, setAsking] = useState(false)
  const [pendingCandidateId, setPendingCandidateId] = useState<number | null>(
    null,
  )
  const askingRef = useRef(false)
  const inProgress = ride.status === RideStatus.IN_PROGRESS
  const awaiting =
    isAwaitingSharedConsent(ride) ||
    (pendingCandidateId != null && ride.shared_ride_consent !== true)

  useEffect(() => {
    if (pendingCandidateId == null) return
    if (
      ride.shared_ride_consent === true ||
      ride.shared_ride_with_id === pendingCandidateId
    ) {
      setPendingCandidateId(null)
      return
    }
    const timer = window.setTimeout(() => {
      setPendingCandidateId((current) =>
        current === pendingCandidateId ? null : current,
      )
    }, 8000)
    return () => window.clearTimeout(timer)
  }, [pendingCandidateId, ride.shared_ride_consent, ride.shared_ride_with_id])

  useEffect(() => {
    if (!inProgress || awaiting) {
      setCandidate(null)
      return
    }

    let cancelled = false

    async function load() {
      try {
        const rows = await getSharedRideCandidates(ride.id)
        if (!cancelled) setCandidate(rows[0] ?? null)
      } catch {
        if (!cancelled) setCandidate(null)
      }
    }

    void load()
    const timer = window.setInterval(() => {
      void load()
    }, CANDIDATE_POLL_MS)

    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [awaiting, inProgress, ride.id])

  async function askPassenger() {
    if (!candidate || askingRef.current || disabled) return
    const candidateId = candidate.id
    askingRef.current = true
    setAsking(true)
    try {
      const updated = await proposeSharedRide(ride.id, candidateId)
      setCandidate(null)
      if (isAwaitingSharedConsent(updated)) {
        setPendingCandidateId(candidateId)
      }
      try {
        const refreshed = await onProposed(updated)
        if (
          refreshed.shared_ride_consent === true ||
          (!isAwaitingSharedConsent(updated) && !isAwaitingSharedConsent(refreshed))
        ) {
          setPendingCandidateId(null)
        }
      } catch (err) {
        onError(toUserMessage(err))
      }
    } catch (err) {
      setPendingCandidateId(null)
      onError(toUserMessage(err))
    } finally {
      askingRef.current = false
      setAsking(false)
    }
  }

  if (!inProgress) return null

  if (awaiting) {
    return (
      <Card className="shared-ride is-waiting">
        <p className="eyebrow">Shared Ride</p>
        <h2>Waiting for passenger consent</h2>
      </Card>
    )
  }

  if (!candidate) return null

  const fare = candidateFare(candidate)

  return (
    <Card className="shared-ride">
      <p className="eyebrow">Shared Ride</p>
      <h2>Potential Shared Ride</h2>
      <dl className="kv-grid">
        <div>
          <dt>Pickup</dt>
          <dd>
            {formatPlace(
              candidate.pickup_location,
              candidate.pickup_latitude,
              candidate.pickup_longitude,
            )}
          </dd>
        </div>
        <div>
          <dt>Destination</dt>
          <dd>
            {formatPlace(
              candidate.destination,
              candidate.destination_latitude,
              candidate.destination_longitude,
            )}
          </dd>
        </div>
        {fare ? (
          <div>
            <dt>{fare.label}</dt>
            <dd>{formatCurrency(fare.amount)}</dd>
          </div>
        ) : null}
      </dl>
      <div className="btn-row wrap">
        <Button busy={asking} disabled={disabled} onClick={() => void askPassenger()}>
          Ask Passenger
        </Button>
      </div>
    </Card>
  )
}

export function PassengerSharedRideConsent({
  ride,
  disabled,
  onRefresh,
  onError,
}: {
  ride: Ride
  disabled: boolean
  onRefresh: () => Promise<Ride>
  onError: (message: string) => void
}) {
  const [decision, setDecision] = useState<boolean | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const submittingRef = useRef(false)

  useEffect(() => {
    setDecision(null)
  }, [ride.id])

  useEffect(() => {
    if (decision == null) return
    if (decision && isSharedRideConfirmed(ride)) setDecision(null)
    if (!decision && ride.shared_ride_with_id == null) setDecision(null)
  }, [decision, ride])

  async function respond(consent: boolean) {
    if (submittingRef.current || disabled) return
    submittingRef.current = true
    setSubmitting(true)
    try {
      await consentToSharedRide(ride.id, consent)
      try {
        await onRefresh()
      } catch (err) {
        onError(toUserMessage(err))
      }
      setDecision(consent)
    } catch (err) {
      onError(toUserMessage(err))
    } finally {
      submittingRef.current = false
      setSubmitting(false)
    }
  }

  if (decision === false) return null

  if (decision === true || isSharedRideConfirmed(ride)) {
    return (
      <Card className="shared-ride is-confirmed">
        <p className="eyebrow">Shared Ride</p>
        <h2>Shared Ride confirmed</h2>
      </Card>
    )
  }

  if (!isAwaitingSharedConsent(ride)) return null

  return (
    <Card className="shared-ride">
      <p className="eyebrow">Shared Ride</p>
      <h2>Shared Ride Request</h2>
      <p>
        The driver has another NEXO passenger going to a similar destination.
        Would you be comfortable sharing the ride?
      </p>
      <div className="btn-row wrap">
        <Button
          busy={submitting}
          disabled={disabled}
          onClick={() => void respond(true)}
        >
          Yes, Share Ride
        </Button>
        <Button
          variant="ghost"
          busy={submitting}
          disabled={disabled}
          onClick={() => void respond(false)}
        >
          No
        </Button>
      </div>
    </Card>
  )
}
