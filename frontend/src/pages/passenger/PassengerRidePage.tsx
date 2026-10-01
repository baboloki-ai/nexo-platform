import { useEffect, useRef, useState, type PointerEvent, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { ApiError, toUserMessage } from '../../api/client'
import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { ConfirmAction } from '../../components/ConfirmAction'
import { DriverIdentityCard } from '../../components/DriverIdentityCard'
import { FareOfferPicker } from '../../components/FareOfferPicker'
import { LoadingState } from '../../components/LoadingState'
import { RideSummary } from '../../components/RideSummary'
import { PassengerSharedRideConsent } from '../../components/SharedRideSection'
import { StatusBadge } from '../../components/StatusBadge'
import { SystemRideMessage } from '../../components/SystemRideMessage'
import { MIN_PASSENGER_OFFER } from '../../constants/fare'
import { rideStatusLabel } from '../../constants/rideStatus'
import { MapView } from '../../maps/MapView'
import { useLiveDriverLocation } from '../../maps/useLiveDriverLocation'
import { useRideMapPoints } from '../../maps/useRideMapPoints'
import { usePassenger } from '../../passenger/PassengerContext'
import {
  RideStatus,
  canPassengerCancel,
  isAssignedStatus,
  isCompletedStatus,
  isEnRouteStatus,
  isSearchingStatus,
} from '../../types/ride'
import { formatCoord, formatCurrency, formatEta, formatKm } from '../../utils/format'
import { assignedDriverIdentity } from '../../utils/driverIdentity'
import {
  formatPaymentAmount,
  isCashPending,
  isPaymentPaid,
} from '../../types/payment'

const SWIPE_AXIS_LOCK_PX = 12
const SWIPE_HINT_PX = 20
const SWIPE_THRESHOLD_PX = 64
const SWIPE_MAX_PX = 88
const INTERACTIVE_SELECTOR = [
  'button',
  'a',
  'input',
  'select',
  'textarea',
  'label',
  'iframe',
  '[role="button"]',
  '[role="link"]',
  '[role="dialog"]',
  '[role="slider"]',
  '[role="option"]',
  '[role="checkbox"]',
  '[role="radio"]',
  '[role="switch"]',
  '[role="tab"]',
  '[role="menuitem"]',
  '[contenteditable="true"]',
  '.btn',
  '.chip-row',
  '.fare-picker',
  '.nexo-map',
  '.leaflet-container',
  '.confirm-backdrop',
  '.confirm-card',
].join(',')

function isInteractiveTarget(target: EventTarget | null): boolean {
  return target instanceof Element && target.closest(INTERACTIVE_SELECTOR) != null
}

function SwipeableResponseCard({
  disabled,
  onSwipeLeft,
  onSwipeRight,
  children,
}: {
  disabled: boolean
  onSwipeLeft: () => void
  onSwipeRight: () => void
  children: ReactNode
}) {
  const rootRef = useRef<HTMLDivElement>(null)
  const onSwipeLeftRef = useRef(onSwipeLeft)
  const onSwipeRightRef = useRef(onSwipeRight)
  onSwipeLeftRef.current = onSwipeLeft
  onSwipeRightRef.current = onSwipeRight

  const [offset, setOffset] = useState(0)
  const [dragging, setDragging] = useState(false)
  const [direction, setDirection] = useState<'none' | 'select' | 'ignore'>('none')
  const [reducedMotion, setReducedMotion] = useState(false)
  const gesture = useRef({
    pointerId: null as number | null,
    startX: 0,
    startY: 0,
    axis: 'undecided' as 'undecided' | 'horizontal' | 'vertical',
    offset: 0,
    acted: false,
  })

  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const sync = () => setReducedMotion(media.matches)
    sync()
    media.addEventListener('change', sync)
    return () => media.removeEventListener('change', sync)
  }, [])

  function settle() {
    gesture.current.offset = 0
    setOffset(0)
    setDragging(false)
    setDirection('none')
  }

  useEffect(() => {
    if (!disabled) return
    const node = rootRef.current
    const pointerId = gesture.current.pointerId
    gesture.current.pointerId = null
    gesture.current.axis = 'undecided'
    gesture.current.acted = true
    gesture.current.offset = 0
    if (node && pointerId != null && node.hasPointerCapture(pointerId)) {
      node.releasePointerCapture(pointerId)
    }
    setOffset(0)
    setDragging(false)
    setDirection('none')
  }, [disabled])

  useEffect(() => {
    const node = rootRef.current
    return () => {
      const pointerId = gesture.current.pointerId
      gesture.current.pointerId = null
      gesture.current.acted = true
      if (node && pointerId != null && node.hasPointerCapture(pointerId)) {
        node.releasePointerCapture(pointerId)
      }
    }
  }, [])

  function onPointerDown(event: PointerEvent<HTMLDivElement>) {
    if (disabled || !event.isPrimary) return
    if (event.pointerType === 'mouse' && event.button !== 0) return
    if (gesture.current.pointerId != null) return
    if (isInteractiveTarget(event.target)) return
    gesture.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      axis: 'undecided',
      offset: 0,
      acted: false,
    }
    setDragging(false)
    setDirection('none')
  }

  function onPointerMove(event: PointerEvent<HTMLDivElement>) {
    const current = gesture.current
    if (current.pointerId !== event.pointerId || current.acted || disabled) return
    const dx = event.clientX - current.startX
    const dy = event.clientY - current.startY

    if (current.axis === 'undecided') {
      if (Math.abs(dx) < SWIPE_AXIS_LOCK_PX && Math.abs(dy) < SWIPE_AXIS_LOCK_PX) {
        return
      }
      if (Math.abs(dy) >= Math.abs(dx)) {
        current.axis = 'vertical'
        current.pointerId = null
        return
      }
      current.axis = 'horizontal'
      setDragging(true)
      rootRef.current?.setPointerCapture(event.pointerId)
    }

    if (current.axis !== 'horizontal') return
    if (event.cancelable) event.preventDefault()
    const next = Math.max(-SWIPE_MAX_PX, Math.min(SWIPE_MAX_PX, dx))
    current.offset = next
    if (!reducedMotion) setOffset(next)
    setDirection(next >= SWIPE_HINT_PX ? 'select' : next <= -SWIPE_HINT_PX ? 'ignore' : 'none')
  }

  function onPointerEnd(event: PointerEvent<HTMLDivElement>) {
    const current = gesture.current
    if (current.pointerId !== event.pointerId) return
    current.pointerId = null
    const node = rootRef.current
    if (node?.hasPointerCapture(event.pointerId)) {
      node.releasePointerCapture(event.pointerId)
    }

    const dx = current.offset
    const axis = current.axis
    const acted = current.acted
    current.axis = 'undecided'
    current.offset = 0

    if (axis !== 'horizontal' || acted || disabled) {
      settle()
      return
    }

    if (dx >= SWIPE_THRESHOLD_PX) {
      current.acted = true
      settle()
      onSwipeRightRef.current()
      return
    }
    if (dx <= -SWIPE_THRESHOLD_PX) {
      current.acted = true
      settle()
      onSwipeLeftRef.current()
      return
    }
    settle()
  }

  const classes = [
    'response-card-swipe',
    dragging ? 'is-dragging' : '',
    direction === 'select' ? 'is-select' : '',
    direction === 'ignore' ? 'is-ignore' : '',
    reducedMotion ? 'is-reduced-motion' : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div
      ref={rootRef}
      className={classes}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerEnd}
      onPointerCancel={onPointerEnd}
      onLostPointerCapture={onPointerEnd}
      onDragStart={(event) => event.preventDefault()}
    >
      <p className="response-card-swipe-hint" aria-hidden="true">
        <span className="is-select-label">Select</span>
        <span className="is-ignore-label">Ignore</span>
      </p>
      <article
        className="response-card"
        style={reducedMotion ? undefined : { transform: `translate3d(${offset}px, 0, 0)` }}
      >
        {children}
      </article>
    </div>
  )
}

function isConfirmedSharedJoiner(ride: { shared_ride_with_id?: number | null; shared_ride_consent?: boolean | null; status: string }): boolean {
  return ride.shared_ride_with_id != null && ride.shared_ride_consent === true && ride.status === RideStatus.ACCEPTED
}

export function PassengerRidePage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const rideId = Number(id)
  const {
    rides,
    driverLocation,
    busy,
    responses,
    refreshTrip,
    cancelRideById,
    increaseOffer,
    maintainOffer,
    selectDriverResponse,
    ignoreResponse,
    setError,
  } = usePassenger()
  const [confirmCancel, setConfirmCancel] = useState(false)
  const [missing, setMissing] = useState(false)
  const [increaseAmount, setIncreaseAmount] = useState<number | null>(null)
  const [pendingSelect, setPendingSelect] = useState<{
    responseId: number
    amount: number
    isCounter: boolean
  } | null>(null)

  const ride = rides.find((item) => item.id === rideId) ?? null
  const activeRide = rides.find((item) => !isCompletedStatus(item.status) && !isConfirmedSharedJoiner(item)) ?? null

  useEffect(() => {
    if (activeRide && activeRide.id !== rideId) {
      navigate("/passenger/ride/" + activeRide.id, { replace: true })
    }
  }, [activeRide, navigate, rideId])
  const openResponses = responses.filter((item) => item.status === 'open')

  useEffect(() => {
    if (pendingSelect == null) return
    const stillOpen = responses.some(
      (item) => item.id === pendingSelect.responseId && item.status === 'open',
    )
    if (!stillOpen) setPendingSelect(null)
  }, [responses, pendingSelect])

  useEffect(() => {
    if (!Number.isInteger(rideId) || rideId <= 0) {
      setMissing(true)
      return
    }
    let cancelled = false
    void refreshTrip(rideId)
      .then(() => {
        if (!cancelled) setMissing(false)
      })
      .catch((err) => {
        if (cancelled) return
        if (err instanceof ApiError && (err.status === 403 || err.status === 404)) {
          setMissing(true)
          return
        }
        setError(toUserMessage(err))
      })
    return () => {
      cancelled = true
    }
  }, [rideId, refreshTrip, setError])

  const { pickup, destination } = useRideMapPoints(ride)
  const driverPoint = useLiveDriverLocation(
    driverLocation
      ? {
          latitude: driverLocation.latitude,
          longitude: driverLocation.longitude,
        }
      : null,
  )

  async function onCancel() {
    try {
      await cancelRideById(rideId)
      setConfirmCancel(false)
    } catch {
      setConfirmCancel(false)
    }
  }

  if (!Number.isInteger(rideId) || rideId <= 0 || missing) {
    return (
      <Card>
        <h2>Ride not found</h2>
        <p className="muted">This ride is not available on your account.</p>
        <Link to="/passenger" className="btn btn-primary">
          Back to dashboard
        </Link>
      </Card>
    )
  }

  if (!ride) {
    return <LoadingState message="Loading ride…" />
  }

  const searching = isSearchingStatus(ride.status)
  const assigned = isAssignedStatus(ride.status)
  const enRoute = isEnRouteStatus(ride.status)
  const completed = isCompletedStatus(ride.status)
  const driverIdentity = assignedDriverIdentity(ride)

  return (
    <>
      <Card className={searching ? 'hero-card searching-card' : 'hero-card'}>
        {searching ? <span className="searching-pulse" aria-hidden="true" /> : null}
        <p className="eyebrow">NEXO</p>
        <h2>
          {searching
            ? 'Waiting for driver responses'
            : completed
              ? 'Trip completed'
              : rideStatusLabel(ride.status)}
        </h2>
        <StatusBadge status={ride.status} />
      </Card>

      <PassengerSharedRideConsent
        ride={ride}
        disabled={busy}
        onRefresh={() => refreshTrip(ride.id)}
        onError={setError}
      />

        {searching ? (
          <Card>
            <p className="eyebrow">Your offer</p>
            <h2>
              {formatCurrency(
                ride.passenger_current_offer ?? ride.proposed_fare,
              )}
            </h2>
            <p className="muted">
              Drivers can accept this amount or send a generated counter-offer.
              You choose the driver. You can increase or keep this offer.
              Minimum is P{MIN_PASSENGER_OFFER}. There is no maximum.
            </p>
            {ride.recommended_fare != null ? (
              <p className="meta">
                NEXO recommended {formatCurrency(ride.recommended_fare)}
                {ride.trip_distance_km != null
                  ? ` for an estimated ${formatKm(ride.trip_distance_km)}`
                  : ''}
                .
              </p>
            ) : null}
            <FareOfferPicker
              recommended={
                ride.recommended_fare ??
                ride.passenger_current_offer ??
                ride.proposed_fare
              }
              options={[
                ride.passenger_current_offer ?? ride.proposed_fare,
                (ride.passenger_current_offer ?? ride.proposed_fare) + 5,
                (ride.passenger_current_offer ?? ride.proposed_fare) + 10,
                (ride.passenger_current_offer ?? ride.proposed_fare) + 20,
              ].filter(
                (amount) =>
                  amount >=
                  (ride.passenger_current_offer ?? ride.proposed_fare),
              )}
              selected={
                increaseAmount ??
                ride.passenger_current_offer ??
                ride.proposed_fare
              }
              onChange={setIncreaseAmount}
              disabled={busy}
              caption={`Increase from ${formatCurrency(ride.passenger_current_offer ?? ride.proposed_fare)} or keep the current offer. Minimum is ${formatCurrency(MIN_PASSENGER_OFFER)}. There is no maximum.`}
            />
            <div className="btn-row wrap">
              <Button
                busy={busy}
                disabled={
                  increaseAmount == null ||
                  increaseAmount <=
                    (ride.passenger_current_offer ?? ride.proposed_fare)
                }
                onClick={() => {
                  if (increaseAmount == null) return
                  void increaseOffer(
                    ride.id,
                    increaseAmount,
                    ride.passenger_offer_version,
                  ).then(() => setIncreaseAmount(null))
                }}
              >
                Increase offer
              </Button>
              <Button
                variant="ghost"
                busy={busy}
                onClick={() =>
                  void maintainOffer(ride.id, ride.passenger_offer_version)
                }
              >
                Keep current offer
              </Button>
            </div>
          </Card>
        ) : null}

        {searching ? (
          <Card>
            <p className="eyebrow">Driver responses</p>
            <h2>
              {openResponses.length} open
            </h2>
            {openResponses.length === 0 ? (
              <p className="muted">No drivers have responded yet.</p>
            ) : (
              <div className="stack">
                <p className="muted">
                  Compare responses and choose a driver. NEXO does not rank or
                  auto-select.
                </p>
                <div className="response-compare" role="table">
                  <div className="response-compare-row head" role="row">
                    <span>Driver</span>
                    <span>Response</span>
                    <span>Fare</span>
                    <span>Pickup ETA</span>
                    <span>Vehicle</span>
                  </div>
                  {openResponses.map((item) => (
                      <div
                        key={`compare-${item.id}`}
                        className="response-compare-row"
                        role="row"
                      >
                        <span>{item.driver?.display_name ?? 'Driver'}</span>
                        <span>
                          {item.response_type === 'counter_offer'
                            ? 'Counter'
                            : 'Accept'}
                        </span>
                        <span>{formatCurrency(item.amount)}</span>
                        <span>{formatEta(item.pickup_eta_seconds)}</span>
                        <span>
                          {item.driver?.vehicle
                            ? `${item.driver.vehicle.make} ${item.driver.vehicle.model}`
                            : '—'}
                        </span>
                      </div>
                    ))}
                </div>
                <p className="muted">
                  Swipe right to select, swipe left to ignore — or use the buttons.
                </p>
                {openResponses.map((item) => (
                    <SwipeableResponseCard
                      key={item.id}
                      disabled={busy || pendingSelect != null || confirmCancel}
                      onSwipeLeft={() => {
                        if (busy) return
                        void ignoreResponse(ride.id, item.id)
                      }}
                      onSwipeRight={() => {
                        if (busy) return
                        setPendingSelect({
                          responseId: item.id,
                          amount: item.amount,
                          isCounter: item.response_type === 'counter_offer',
                        })
                      }}
                    >
                      <div className="section-head">
                        <div>
                          <p className="eyebrow">
                            {item.response_type === 'counter_offer'
                              ? 'Counter-offer'
                              : 'Accepts your offer'}
                          </p>
                          <h3>{formatCurrency(item.amount)}</h3>
                        </div>
                        {item.driver ? (
                          <p className="meta">{item.driver.display_name}</p>
                        ) : null}
                      </div>
                      <dl className="kv-grid">
                        <div>
                          <dt>Pickup ETA</dt>
                          <dd>{formatEta(item.pickup_eta_seconds)}</dd>
                        </div>
                        <div>
                          <dt>Pickup distance</dt>
                          <dd>{formatKm(item.pickup_distance_km)}</dd>
                        </div>
                        {item.driver?.vehicle ? (
                          <div>
                            <dt>Vehicle</dt>
                            <dd>
                              {item.driver.vehicle.make} {item.driver.vehicle.model}{' '}
                              · {item.driver.vehicle.color}
                            </dd>
                          </div>
                        ) : null}
                        {item.driver?.vehicle ? (
                          <div>
                            <dt>Registration</dt>
                            <dd className="mono">
                              {item.driver.vehicle.registration_number}
                            </dd>
                          </div>
                        ) : null}
                      </dl>
                      {item.driver ? (
                        <DriverIdentityCard
                          identity={item.driver}
                          statusLabel={
                            item.response_type === 'counter_offer'
                              ? 'Counter-offer'
                              : 'Ready to accept'
                          }
                        />
                      ) : null}
                      <div className="btn-row wrap">
                        <Button
                          busy={busy}
                          onClick={() => {
                            if (busy || pendingSelect != null) return
                            setPendingSelect({
                              responseId: item.id,
                              amount: item.amount,
                              isCounter: item.response_type === 'counter_offer',
                            })
                          }}
                        >
                          {item.response_type === 'counter_offer'
                            ? `Accept ${formatCurrency(item.amount)}`
                            : 'Select this driver'}
                        </Button>
                        <Button
                          variant="ghost"
                          disabled={busy}
                          onClick={() => void ignoreResponse(ride.id, item.id)}
                        >
                          Ignore
                        </Button>
                      </div>
                    </SwipeableResponseCard>
                  ))}
              </div>
            )}
          </Card>
        ) : null}

        <Card>
        <p className="eyebrow">Map</p>
        <h2>Trip</h2>
        <MapView pickup={pickup} destination={destination} driver={driverPoint} />
        <p className="map-legend">
          <span>Pickup</span>
          <span>Destination</span>
          <span>Driver {driverPoint ? 'live' : 'waiting for location'}</span>
        </p>
      </Card>

      {(assigned || enRoute || completed) && ride.system_messages?.length ? (
        <Card>
          <SystemRideMessage messages={ride.system_messages} />
        </Card>
      ) : null}

      <Card>
        <RideSummary
          ride={ride}
          driverLocation={
            driverLocation && (assigned || enRoute)
              ? {
                  latitude: driverLocation.latitude,
                  longitude: driverLocation.longitude,
                }
              : null
          }
        />

        {(assigned || enRoute) && driverIdentity ? (
          <DriverIdentityCard
            identity={driverIdentity}
            statusLabel={rideStatusLabel(ride.status)}
            liveLocation={
              driverLocation
                ? `${formatCoord(driverLocation.latitude)}, ${formatCoord(driverLocation.longitude)}`
                : null
            }
          />
        ) : (assigned || enRoute) && ride.accepted_driver_id != null ? (
          <div className="location-box">
            <p className="eyebrow">Driver</p>
            <p>Driver assigned</p>
            {driverLocation ? (
              <p className="mono">
                {formatCoord(driverLocation.latitude)},{' '}
                {formatCoord(driverLocation.longitude)}
              </p>
            ) : (
              <p className="muted">
                Driver location appears here after the assigned driver shares
                their position.
              </p>
            )}
          </div>
        ) : null}

        {canPassengerCancel(ride.status) ? (
          <div className="action-bar">
            <Button variant="danger" busy={busy} onClick={() => setConfirmCancel(true)}>
              Cancel ride
            </Button>
          </div>
        ) : ride.status === RideStatus.IN_PROGRESS ? (
          <p className="muted">
            You cannot cancel after the trip has started.
          </p>
        ) : null}

        {completed || (!searching && !assigned && !enRoute) ? (
          <div className="btn-row wrap action-bar">
            <Link to="/passenger" className="btn btn-primary">
              Back to dashboard
            </Link>
            <Link to="/passenger/history" className="btn btn-ghost">
              Ride history
            </Link>
          </div>
        ) : null}
      </Card>

      {completed && ride.payment ? (
        <Card>
          <div className="cash-notice">
            <p className="eyebrow">Payment</p>
            {isCashPending(ride.payment) ? (
              <>
                <p className="cash-notice-title">Payment pending</p>
                <p className="muted">Awaiting driver confirmation.</p>
              </>
            ) : isPaymentPaid(ride.payment) ? (
              <p className="cash-notice-title">
                Payment received — {formatPaymentAmount(ride.payment.amount)}
              </p>
            ) : null}
          </div>
        </Card>
      ) : null}

      <ConfirmAction
        open={pendingSelect != null}
        title={
          pendingSelect?.isCounter
            ? `Accept ${formatCurrency(pendingSelect.amount)}?`
            : 'Select this driver?'
        }
        body="This chooses the driver for this ride at the shown fare. Other open responses will close."
        confirmLabel={
          pendingSelect?.isCounter
            ? `Accept ${formatCurrency(pendingSelect.amount)}`
            : 'Select this driver'
        }
        busy={busy}
        onConfirm={() => {
          if (pendingSelect == null || busy) return
          const responseId = pendingSelect.responseId
          void selectDriverResponse(ride.id, responseId).finally(() => {
            setPendingSelect(null)
          })
        }}
        onCancel={() => setPendingSelect(null)}
      />
      <ConfirmAction
        open={confirmCancel}
        title="Cancel this ride?"
        body="You can cancel until the driver starts the trip. There is no cancellation fee in this cash pilot. You can request another ride afterwards."
        confirmLabel="Cancel ride"
        danger
        busy={busy}
        onConfirm={() => void onCancel()}
        onCancel={() => setConfirmCancel(false)}
      />
    </>
  )
}







