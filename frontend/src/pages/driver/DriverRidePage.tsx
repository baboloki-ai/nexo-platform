import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { ApiError, toUserMessage } from '../../api/client'
import { confirmCashPayment } from '../../api/payments'
import { getTrip } from '../../api/trips'
import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { ConfirmAction } from '../../components/ConfirmAction'
import { LoadingState } from '../../components/LoadingState'
import { RideSummary } from '../../components/RideSummary'
import { DriverSharedRideSection } from '../../components/SharedRideSection'
import { StatusBadge } from '../../components/StatusBadge'
import { SystemRideMessage } from '../../components/SystemRideMessage'
import { rideStatusLabel } from '../../constants/rideStatus'
import { useDriver } from '../../driver/DriverContext'
import { MapView } from '../../maps/MapView'
import { isValidLatLng } from '../../maps/types'
import { gpsWatchStatusLabel } from '../../maps/useDriverGpsWatch'
import { useLiveDriverLocation } from '../../maps/useLiveDriverLocation'
import { useRideMapPoints } from '../../maps/useRideMapPoints'
import {
  RideStatus,
  canDriverCancel,
  isActiveRide,
  isCompletedStatus,
  type Ride,
} from '../../types/ride'
import {
  formatPaymentAmount,
  isCashPending,
  isPaymentPaid,
} from '../../types/payment'

export function DriverRidePage() {
  const { id } = useParams()
  const rideId = Number(id)
  const {
    ride,
    nextRide,
    busy,
    refreshTrip,
    loadHistoryTrip,
    setError,
    arrive,
    markArrived,
    start,
    complete,
    cancelAssigned,
    latitude,
    longitude,
    gpsConfirmed,
    gpsMode,
    gpsWatchStatus,
    lastWatchPosition,
  } = useDriver()
  const [confirmComplete, setConfirmComplete] = useState(false)
  const [confirmCancel, setConfirmCancel] = useState(false)
  const [missing, setMissing] = useState(false)
  const [pending, setPending] = useState(false)
  const [localRide, setLocalRide] = useState<Ride | null>(null)

  // Retain this route's ride if complete() promotes a different assigned ride.
  if (ride?.id === rideId && localRide !== ride) {
    setLocalRide(ride)
  }

  const current =
    ride?.id === rideId ? ride : localRide?.id === rideId ? localRide : null

  useEffect(() => {
    if (!Number.isInteger(rideId) || rideId <= 0) {
      setMissing(true)
      return
    }
    if (ride?.id === rideId) {
      setMissing(false)
      return
    }

    let cancelled = false
    const hasOtherActive = ride != null && isActiveRide(ride.status) && ride.id !== rideId
    const loader = hasOtherActive ? loadHistoryTrip : refreshTrip

    void loader(rideId)
      .then((trip) => {
        if (cancelled) return
        if (hasOtherActive) setLocalRide(trip)
        setMissing(false)
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
  }, [rideId, ride, refreshTrip, loadHistoryTrip, setError])

  const { pickup, destination } = useRideMapPoints(current)
  const sentLat = Number(latitude)
  const sentLng = Number(longitude)
  const confirmedPoint =
    gpsConfirmed && isValidLatLng(sentLat, sentLng)
      ? { latitude: sentLat, longitude: sentLng }
      : null
  const driverPoint = useLiveDriverLocation(
    gpsMode === 'live' ? (lastWatchPosition ?? confirmedPoint) : confirmedPoint,
  )

  async function run(action: () => Promise<unknown>) {
    setPending(true)
    try {
      await action()
    } catch {
      // Layout shows the API error.
    } finally {
      setPending(false)
    }
  }

  if (!Number.isInteger(rideId) || rideId <= 0 || missing) {
    return (
      <Card>
        <h2>Ride not found</h2>
        <p className="muted">You are not assigned to this trip.</p>
        <Link to="/driver" className="btn btn-primary">
          Back to dashboard
        </Link>
      </Card>
    )
  }

  if (!current) {
    return <LoadingState message="Loading ride…" />
  }

  const disabled = busy || pending
  const completed = isCompletedStatus(current.status)
  const isQueuedNext =
    current.is_next_ride === true || nextRide?.id === current.id
  const isCurrentAssigned = ride?.id === current.id && !isQueuedNext
  const active = isActiveRide(current.status)

  return (
    <>
      <Card className="hero-card">
        <p className="eyebrow">{isQueuedNext ? 'Next ride' : 'Current ride'}</p>
        <h2>{rideStatusLabel(current.status)}</h2>
        <StatusBadge status={current.status} />
        {isQueuedNext ? (
          <p className="muted">
            This ride stays accepted until you complete the current trip.
          </p>
        ) : null}
        {isCurrentAssigned && nextRide ? (
          <p className="muted">
            Next Ride {nextRide.id} is accepted.{' '}
            <Link to={`/driver/ride/${nextRide.id}`}>Open next ride</Link>
          </p>
        ) : null}
      </Card>

      <Card>
        <p className="eyebrow">Map</p>
        <h2>Trip</h2>
        <MapView pickup={pickup} destination={destination} driver={driverPoint} />
        <p className="map-legend">
          <span>Pickup</span>
          <span>Destination</span>
          <span>
            Driver{' '}
            {driverPoint
              ? gpsMode === 'demo'
                ? 'fallback position'
                : 'current position'
              : 'no location yet'}
          </span>
          <span>{gpsWatchStatusLabel(gpsWatchStatus)}</span>
        </p>
      </Card>

      {current.system_messages?.length ? (
        <Card>
          <SystemRideMessage messages={current.system_messages} />
        </Card>
      ) : null}

      {current.status === RideStatus.IN_PROGRESS && isCurrentAssigned ? (
        <DriverSharedRideSection
          ride={current}
          disabled={disabled}
          onProposed={async () => {
            const refreshed = await refreshTrip(current.id)
            if (refreshed.id === current.id) setLocalRide(refreshed)
            return refreshed
          }}
          onError={setError}
        />
      ) : null}

      <Card>
        <RideSummary
          ride={current}
          extra={
            active && isCurrentAssigned ? (
              <div className="btn-row wrap action-bar">
                {current.status === RideStatus.ACCEPTED ? (
                  <Button disabled={disabled} onClick={() => void run(arrive)}>
                    Arrive
                  </Button>
                ) : null}
                {current.status === RideStatus.DRIVER_ARRIVING ? (
                  <Button disabled={disabled} onClick={() => void run(markArrived)}>
                    Driver arrived
                  </Button>
                ) : null}
                {current.status === RideStatus.DRIVER_ARRIVING ||
                current.status === RideStatus.DRIVER_ARRIVED ? (
                  <Button
                    variant="secondary"
                    disabled={disabled}
                    onClick={() => void run(start)}
                  >
                    Start
                  </Button>
                ) : null}
                {current.status === RideStatus.IN_PROGRESS ? (
                  <Button disabled={disabled} onClick={() => setConfirmComplete(true)}>
                    Complete
                  </Button>
                ) : null}
                {canDriverCancel(current.status) ? (
                  <Button
                    variant="danger"
                    disabled={disabled}
                    onClick={() => setConfirmCancel(true)}
                  >
                    Cancel ride
                  </Button>
                ) : null}
              </div>
            ) : null
          }
        />

        {completed || !active ? (
          <div className="btn-row wrap action-bar">
            <Link to="/driver" className="btn btn-primary">
              Back to dashboard
            </Link>
            <Link to="/driver/history" className="btn btn-ghost">
              Ride history
            </Link>
          </div>
        ) : null}
      </Card>

      {completed && current.payment && isCashPending(current.payment) ? (
        <Card>
          <div className="cash-notice">
            <p className="eyebrow">Cash payment</p>
            <p className="cash-notice-title">
              {formatPaymentAmount(current.payment.amount)}
            </p>
            <div className="btn-row wrap action-bar">
              <Button
                disabled={disabled}
                busy={pending}
                onClick={() => {
                  const paymentId = current.payment?.id
                  if (paymentId == null) return
                  void run(async () => {
                    try {
                      await confirmCashPayment(paymentId)
                      const trip = await getTrip(current.id)
                      setLocalRide(trip)
                      if (ride?.id === current.id) {
                        await refreshTrip(current.id)
                      }
                    } catch (err) {
                      setError(toUserMessage(err))
                      throw err
                    }
                  })
                }}
              >
                Confirm cash received
              </Button>
            </div>
          </div>
        </Card>
      ) : completed && current.payment && isPaymentPaid(current.payment) ? (
        <Card>
          <div className="cash-notice">
            <p className="eyebrow">Cash payment</p>
            <p className="cash-notice-title">
              Payment received — {formatPaymentAmount(current.payment.amount)}
            </p>
          </div>
        </Card>
      ) : null}

      <ConfirmAction
        open={confirmComplete}
        title="Complete this ride?"
        body="The passenger will be notified that the trip is finished."
        confirmLabel="Complete ride"
        busy={disabled}
        onConfirm={() => {
          void run(async () => {
            const completedRide = await complete()
            if (completedRide) setLocalRide(completedRide)
          }).finally(() => setConfirmComplete(false))
        }}
        onCancel={() => setConfirmComplete(false)}
      />
      <ConfirmAction
        open={confirmCancel}
        title="Cancel this ride?"
        body="You can cancel until the trip starts. There is no cancellation fee in this cash pilot."
        confirmLabel="Cancel ride"
        danger
        busy={disabled}
        onConfirm={() => {
          void run(cancelAssigned).finally(() => setConfirmCancel(false))
        }}
        onCancel={() => setConfirmCancel(false)}
      />
    </>
  )
}
