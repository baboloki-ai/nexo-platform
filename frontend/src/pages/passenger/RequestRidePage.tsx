import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'

import { toUserMessage } from '../../api/client'
import { quoteFare } from '../../api/rides'
import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { CashPaymentNotice } from '../../components/CashPaymentNotice'
import { FareOfferPicker } from '../../components/FareOfferPicker'
import { Input } from '../../components/Input'
import { LoadingState } from '../../components/LoadingState'
import { EXAMPLE_DESTINATION, EXAMPLE_PICKUP } from '../../constants/location'
import { MIN_PASSENGER_OFFER } from '../../constants/fare'
import { MapView } from '../../maps/MapView'
import type { MapPoint, MapSelectMode } from '../../maps/types'
import { isValidLatLng } from '../../maps/types'
import { usePassenger } from '../../passenger/PassengerContext'
import type { FareQuote, RideCreate } from '../../types/ride'
import { formatCurrency, formatKm } from '../../utils/format'

type RideForm = {
  pickup_location: string
  pickup_latitude: string
  pickup_longitude: string
  destination: string
  destination_latitude: string
  destination_longitude: string
}

type FieldErrors = Partial<Record<keyof RideForm | 'proposed_fare', string>>

function exampleForm(): RideForm {
  return {
    pickup_location: EXAMPLE_PICKUP.label,
    pickup_latitude: String(EXAMPLE_PICKUP.latitude),
    pickup_longitude: String(EXAMPLE_PICKUP.longitude),
    destination: EXAMPLE_DESTINATION.label,
    destination_latitude: String(EXAMPLE_DESTINATION.latitude),
    destination_longitude: String(EXAMPLE_DESTINATION.longitude),
  }
}

function parseNumber(value: string, label: string): number {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) {
    throw new Error(`${label} must be a valid number.`)
  }
  return parsed
}

function validate(
  form: RideForm,
  offer: number | null,
): { errors: FieldErrors; payload?: RideCreate } {
  const errors: FieldErrors = {}
  if (!form.pickup_location.trim()) errors.pickup_location = 'Pickup is required.'
  if (!form.destination.trim()) errors.destination = 'Destination is required.'

  let pickupLat = 0
  let pickupLon = 0
  let destLat = 0
  let destLon = 0

  try {
    pickupLat = parseNumber(form.pickup_latitude, 'Pickup latitude')
    if (pickupLat < -90 || pickupLat > 90) {
      errors.pickup_latitude = 'Latitude must be between -90 and 90.'
    }
  } catch (err) {
    errors.pickup_latitude = err instanceof Error ? err.message : 'Invalid latitude.'
  }

  try {
    pickupLon = parseNumber(form.pickup_longitude, 'Pickup longitude')
    if (pickupLon < -180 || pickupLon > 180) {
      errors.pickup_longitude = 'Longitude must be between -180 and 180.'
    }
  } catch (err) {
    errors.pickup_longitude =
      err instanceof Error ? err.message : 'Invalid longitude.'
  }

  try {
    destLat = parseNumber(form.destination_latitude, 'Destination latitude')
    if (destLat < -90 || destLat > 90) {
      errors.destination_latitude = 'Latitude must be between -90 and 90.'
    }
  } catch (err) {
    errors.destination_latitude =
      err instanceof Error ? err.message : 'Invalid latitude.'
  }

  try {
    destLon = parseNumber(form.destination_longitude, 'Destination longitude')
    if (destLon < -180 || destLon > 180) {
      errors.destination_longitude = 'Longitude must be between -180 and 180.'
    }
  } catch (err) {
    errors.destination_longitude =
      err instanceof Error ? err.message : 'Invalid longitude.'
  }

  if (offer == null || !Number.isFinite(offer) || offer < MIN_PASSENGER_OFFER) {
    errors.proposed_fare = `Choose an offer of at least P${MIN_PASSENGER_OFFER}.`
  }

  if (Object.keys(errors).length > 0) {
    return { errors }
  }

  return {
    errors,
    payload: {
      pickup_location: form.pickup_location.trim(),
      pickup_latitude: pickupLat,
      pickup_longitude: pickupLon,
      destination: form.destination.trim(),
      destination_latitude: destLat,
      destination_longitude: destLon,
      proposed_fare: offer as number,
    },
  }
}

function pointFromFields(
  latitude: string,
  longitude: string,
  label: string,
): MapPoint | null {
  const lat = Number(latitude)
  const lng = Number(longitude)
  if (!isValidLatLng(lat, lng)) return null
  return { latitude: lat, longitude: lng, label }
}

export function RequestRidePage() {
  const navigate = useNavigate()
  const { profile, activeRide, loading, busy, requestRide, setError } =
    usePassenger()
  const [form, setForm] = useState<RideForm>(exampleForm)
  const [errors, setErrors] = useState<FieldErrors>({})
  const [selectMode, setSelectMode] = useState<MapSelectMode>('pickup')
  const [fitNonce, setFitNonce] = useState(0)
  const [quote, setQuote] = useState<FareQuote | null>(null)
  const [quoteBusy, setQuoteBusy] = useState(false)
  const [selectedOffer, setSelectedOffer] = useState<number | null>(null)

  const canSubmit = useMemo(
    () => !busy && !activeRide && selectedOffer != null && quote != null,
    [busy, activeRide, selectedOffer, quote],
  )
  const pickupPoint = pointFromFields(
    form.pickup_latitude,
    form.pickup_longitude,
    'Pickup',
  )
  const destinationPoint = pointFromFields(
    form.destination_latitude,
    form.destination_longitude,
    'Destination',
  )

  useEffect(() => {
    if (!pickupPoint || !destinationPoint) {
      setQuote(null)
      setSelectedOffer(null)
      return
    }
    let cancelled = false
    setQuoteBusy(true)
    void quoteFare({
      pickup_latitude: pickupPoint.latitude,
      pickup_longitude: pickupPoint.longitude,
      destination_latitude: destinationPoint.latitude,
      destination_longitude: destinationPoint.longitude,
    })
      .then((next) => {
        if (cancelled) return
        setQuote(next)
        setSelectedOffer(next.recommended_fare)
        setErrors((current) => {
          const { proposed_fare: _ignored, ...rest } = current
          return rest
        })
      })
      .catch((err) => {
        if (cancelled) return
        setQuote(null)
        setSelectedOffer(null)
        setError(toUserMessage(err))
      })
      .finally(() => {
        if (!cancelled) setQuoteBusy(false)
      })
    return () => {
      cancelled = true
    }
  }, [
    pickupPoint?.latitude,
    pickupPoint?.longitude,
    destinationPoint?.latitude,
    destinationPoint?.longitude,
    setError,
  ])

  function update<K extends keyof RideForm>(key: K, value: string) {
    setForm((current) => ({ ...current, [key]: value }))
  }

  function onMapClick(point: { latitude: number; longitude: number }) {
    const lat = point.latitude.toFixed(6)
    const lng = point.longitude.toFixed(6)
    if (selectMode === 'pickup') {
      setForm((current) => ({
        ...current,
        pickup_latitude: lat,
        pickup_longitude: lng,
      }))
      return
    }
    setForm((current) => ({
      ...current,
      destination_latitude: lat,
      destination_longitude: lng,
    }))
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    const result = validate(form, selectedOffer)
    setErrors(result.errors)
    if (!result.payload) return
    try {
      const ride = await requestRide(result.payload)
      navigate(`/passenger/ride/${ride.id}`)
    } catch {
      // Layout shows the API error.
    }
  }

  if (loading) {
    return <LoadingState message="Loading…" />
  }

  if (!profile) {
    return <Navigate to="/passenger" replace />
  }

  if (activeRide) {
    return <Navigate to={`/passenger/ride/${activeRide.id}`} replace />
  }

  return (
    <Card>
      <p className="eyebrow">NEXO · Gaborone</p>
      <h2>Request a ride</h2>
      <p className="muted">
        Set pickup and destination. NEXO estimates trip distance and recommends
        a cash fare. You can offer the recommended amount or more.
      </p>
      <div className="map-toolbar">
        <Button
          type="button"
          variant={selectMode === 'pickup' ? 'primary' : 'ghost'}
          onClick={() => setSelectMode('pickup')}
        >
          Select pickup
        </Button>
        <Button
          type="button"
          variant={selectMode === 'destination' ? 'primary' : 'ghost'}
          onClick={() => setSelectMode('destination')}
        >
          Select destination
        </Button>
      </div>
      <MapView
        pickup={pickupPoint}
        destination={destinationPoint}
        onMapClick={onMapClick}
        fitNonce={fitNonce}
      />
      <p className="map-legend">
        <span>Pickup</span>
        <span>Destination</span>
        <span>
          {selectMode === 'pickup' ? 'Selecting pickup' : 'Selecting destination'}
        </span>
      </p>
      <form className="stack map-follow-form" onSubmit={onSubmit}>
        <Input
          label="Pickup"
          value={form.pickup_location}
          onChange={(event) => update('pickup_location', event.target.value)}
          error={errors.pickup_location}
          required
        />
        <div className="field-row">
          <Input
            label="Pickup latitude"
            inputMode="decimal"
            value={form.pickup_latitude}
            onChange={(event) => update('pickup_latitude', event.target.value)}
            error={errors.pickup_latitude}
            required
          />
          <Input
            label="Pickup longitude"
            inputMode="decimal"
            value={form.pickup_longitude}
            onChange={(event) => update('pickup_longitude', event.target.value)}
            error={errors.pickup_longitude}
            required
          />
        </div>
        <Input
          label="Destination"
          value={form.destination}
          onChange={(event) => update('destination', event.target.value)}
          error={errors.destination}
          required
        />
        <div className="field-row">
          <Input
            label="Destination latitude"
            inputMode="decimal"
            value={form.destination_latitude}
            onChange={(event) => update('destination_latitude', event.target.value)}
            error={errors.destination_latitude}
            required
          />
          <Input
            label="Destination longitude"
            inputMode="decimal"
            value={form.destination_longitude}
            onChange={(event) => update('destination_longitude', event.target.value)}
            error={errors.destination_longitude}
            required
          />
        </div>
        <div>
          <p className="eyebrow">Estimated trip distance</p>
          <h2>
            {quoteBusy
              ? 'Calculating…'
              : quote?.estimated_trip_distance_km != null
                ? formatKm(quote.estimated_trip_distance_km)
                : '—'}
          </h2>
          <p className="muted">
            Straight-line estimate, not road distance. Used only to recommend a
            fare.
          </p>
        </div>
        <div>
          <p className="eyebrow">Recommended fare</p>
          <h2>
            {quote ? formatCurrency(quote.recommended_fare) : '—'}
          </h2>
          <p className="muted">
            {quote
              ? `P${quote.base_fare.toFixed(2)} base + P${quote.fare_per_km.toFixed(2)} per km. You can offer more.`
              : 'Set pickup and destination to see a recommended fare.'}
          </p>
        </div>
        {quote && selectedOffer != null ? (
          <FareOfferPicker
            recommended={quote.recommended_fare}
            options={quote.offer_options}
            selected={selectedOffer}
            onChange={setSelectedOffer}
            disabled={busy || quoteBusy}
          />
        ) : null}
        {errors.proposed_fare ? (
          <p className="field-error">{errors.proposed_fare}</p>
        ) : null}
        <CashPaymentNotice />
        <div className="btn-row wrap">
          <Button type="submit" busy={busy} disabled={!canSubmit}>
            {busy ? 'Requesting…' : 'Request ride'}
          </Button>
          <Button
            variant="ghost"
            type="button"
            disabled={busy}
            onClick={() => {
              setForm(exampleForm())
              setErrors({})
              setFitNonce((value) => value + 1)
            }}
          >
            Use Gaborone example
          </Button>
        </div>
      </form>
    </Card>
  )
}
