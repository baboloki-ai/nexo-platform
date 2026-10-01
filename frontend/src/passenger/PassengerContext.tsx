import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import type { ReactNode } from 'react'

import { createPassenger, getMyPassengers } from '../api/passengers'
import {
  cancelRide,
  createRide,
  getMyRides,
  getRideResponses,
  ignoreDriverResponse,
  selectDriver,
  updatePassengerOffer,
} from '../api/rides'
import { getTrip } from '../api/trips'
import { ApiError, toUserMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { getToken } from '../auth/session'
import { rideUpdateMessage } from '../constants/rideStatus'
import { connectPassengerSocket } from '../realtime/passengerSocket'
import type { Passenger } from '../types/passenger'
import {
  isActiveRide,
  type DriverResponse,
  type Ride,
  type RideCreate,
} from '../types/ride'
import type { DriverLocationEvent, SocketStatus } from '../types/websocket'
import { extractRideId } from '../utils/rideEvents'

type PassengerContextValue = {
  profile: Passenger | null
  rides: Ride[]
  activeRide: Ride | null
  driverLocation: DriverLocationEvent | null
  socketStatus: SocketStatus
  error: string | null
  info: string | null
  loading: boolean
  busy: boolean
  setError: (message: string | null) => void
  setInfo: (message: string | null) => void
  refreshRides: () => Promise<Ride[]>
  refreshTrip: (rideId: number) => Promise<Ride>
  saveProfile: (firstName: string, lastName: string) => Promise<void>
  requestRide: (payload: RideCreate) => Promise<Ride>
  cancelRideById: (rideId: number) => Promise<Ride>
  responses: DriverResponse[]
  refreshResponses: (rideId: number) => Promise<DriverResponse[]>
  increaseOffer: (rideId: number, amount: number, version?: number) => Promise<Ride>
  maintainOffer: (rideId: number, version?: number) => Promise<Ride>
  selectDriverResponse: (rideId: number, responseId: number) => Promise<Ride>
  ignoreResponse: (rideId: number, responseId: number) => Promise<Ride>
}

const PassengerContext = createContext<PassengerContextValue | null>(null)

export function PassengerProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const [profile, setProfile] = useState<Passenger | null>(null)
  const [rides, setRides] = useState<Ride[]>([])
  const [driverLocation, setDriverLocation] =
    useState<DriverLocationEvent | null>(null)
  const [socketStatus, setSocketStatus] = useState<SocketStatus>('idle')
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [responses, setResponses] = useState<DriverResponse[]>([])

  const activeRide = useMemo(
    () => rides
      .filter((ride) => isActiveRide(ride.status))
      .sort((a, b) => new Date(b.requested_at).getTime() - new Date(a.requested_at).getTime())[0] ?? null,
    [rides],
  )
  const activeRideIdRef = useRef<number | null>(null)
  activeRideIdRef.current = activeRide?.id ?? null

  const applyTrip = useCallback((trip: Ride) => {
    setRides((current) => {
      const others = current.filter((ride) => ride.id !== trip.id)
      return [trip, ...others]
    })
    if (!isActiveRide(trip.status)) {
      setDriverLocation((current) =>
        current && trip.accepted_driver_id === current.driver_id ? current : null,
      )
    }
    return trip
  }, [])

  const refreshRides = useCallback(async () => {
    const history = await getMyRides()
    setRides(history)
    return history
  }, [])

  const refreshTrip = useCallback(
    async (rideId: number) => {
      const trip = await getTrip(rideId)
      return applyTrip(trip)
    },
    [applyTrip],
  )

  const refreshResponses = useCallback(async (rideId: number) => {
    const rows = await getRideResponses(rideId)
    setResponses(rows)
    return rows
  }, [])

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      try {
        const profiles = await getMyPassengers()
        if (cancelled) return
        setProfile(profiles[0] ?? null)
        if (profiles[0]) {
          await refreshRides()
        }
      } catch (err) {
        if (!cancelled) setError(toUserMessage(err))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [refreshRides])

  useEffect(() => {
    if (!profile) return
    const token = getToken()
    if (!token) return

    const handle = connectPassengerSocket(profile.id, token, {
      onStatus: (status) => {
        setSocketStatus(status)
        if (status === 'unauthorized') {
          setError('Live updates could not be authenticated. Please sign in again.')
        }
      },
      onEvent: (event) => {
        if (event.event === 'connected') {
          return
        }
        if (event.event === 'ride_accepted' && 'ride_id' in event) {
          const rideId = Number(event.ride_id)
          setDriverLocation(null)
          void refreshTrip(rideId)
            .then((trip) => setInfo(rideUpdateMessage(trip.status)))
            .catch((err) => setError(toUserMessage(err)))
          return
        }
        if (event.event === 'ride_agreed' && 'ride_id' in event) {
          const rideId = Number(event.ride_id)
          void refreshTrip(rideId)
            .then((trip) => {
              setInfo(
                trip.agreed_fare != null
                  ? `Agreed fare locked at P${Number(trip.agreed_fare).toFixed(2)}.`
                  : rideUpdateMessage(trip.status),
              )
              return refreshResponses(rideId)
            })
            .catch((err) => setError(toUserMessage(err)))
          return
        }
        if (event.event === 'driver_response_received' && 'ride_id' in event) {
          const rideId = Number(event.ride_id)
          setInfo('A driver responded to your offer.')
          void refreshResponses(rideId).catch((err) => setError(toUserMessage(err)))
          void refreshTrip(rideId).catch((err) => setError(toUserMessage(err)))
          return
        }
        if (
          (event.event === 'driver_response_withdrawn' ||
            event.event === 'driver_response_expired') &&
          'ride_id' in event
        ) {
          const rideId = Number(event.ride_id)
          void refreshResponses(rideId).catch((err) => setError(toUserMessage(err)))
          return
        }
        if (event.event === 'no_driver_available' && 'ride_id' in event) {
          const rideId = Number(event.ride_id)
          void refreshTrip(rideId)
            .then((trip) => setInfo(rideUpdateMessage(trip.status)))
            .catch((err) => setError(toUserMessage(err)))
          return
        }
        if (event.event === 'payment_updated' && 'ride_id' in event) {
          const rideId = Number(event.ride_id)
          void refreshTrip(rideId).catch((err) => {
            if (err instanceof ApiError && (err.status === 403 || err.status === 404)) {
              return
            }
            setError(toUserMessage(err))
          })
          return
        }
        if (event.event === 'driver_location') {
          setDriverLocation(event as DriverLocationEvent)
          return
        }
        if (event.event === 'notification') {
          const rideId =
            extractRideId(event as unknown as Record<string, unknown>) ??
            activeRideIdRef.current
          if (!rideId) return
          void refreshTrip(rideId)
            .then((trip) => setInfo(rideUpdateMessage(trip.status)))
            .catch((err) => {
              if (err instanceof ApiError && (err.status === 403 || err.status === 404)) {
                void refreshRides().catch(() => {
                  setError(toUserMessage(err))
                })
                return
              }
              setError(toUserMessage(err))
            })
        }
      },
    })

    return () => handle.close()
  }, [profile, refreshTrip, refreshRides, refreshResponses])

  useEffect(() => {
    if (!activeRide) {
      setResponses([])
      return
    }
    void refreshResponses(activeRide.id).catch(() => undefined)
    const timer = window.setInterval(() => {
      void refreshTrip(activeRide.id).catch(() => {
        // Keep the last known ride if a background poll fails.
      })
      if (
        activeRide.status === 'pending' ||
        activeRide.status === 'pending_driver_acceptance'
      ) {
        void refreshResponses(activeRide.id).catch(() => undefined)
      }
    }, 5000)
    return () => window.clearInterval(timer)
  }, [activeRide, refreshTrip, refreshResponses])

  const saveProfile = useCallback(
    async (firstName: string, lastName: string) => {
      if (!user) return
      setBusy(true)
      setError(null)
      try {
        const created = await createPassenger({
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          phone: user.phone_number,
          email: user.email,
        })
        setProfile(created)
        await refreshRides()
      } catch (err) {
        setError(toUserMessage(err))
        throw err
      } finally {
        setBusy(false)
      }
    },
    [refreshRides, user],
  )

  const requestRide = useCallback(
    async (payload: RideCreate) => {
      setBusy(true)
      setError(null)
      setDriverLocation(null)
      try {
        const ride = await createRide(payload)
        applyTrip(ride)
        setInfo('Looking for a driver.')
        return ride
      } catch (err) {
        if (err instanceof ApiError && err.status === 400) {
          const message = toUserMessage(err)
          if (/already have an active ride/i.test(message)) {
            setError(message)
          } else if (/passenger profile not found/i.test(message)) {
            setError('Create a passenger profile before requesting a ride.')
          } else {
            setError(
              'Unable to request the ride. Please check your pickup and destination.',
            )
          }
        } else {
          setError(toUserMessage(err))
        }
        throw err
      } finally {
        setBusy(false)
      }
    },
    [applyTrip],
  )

  const cancelRideById = useCallback(
    async (rideId: number) => {
      setBusy(true)
      setError(null)
      try {
        const ride = await cancelRide(rideId)
        applyTrip(ride)
        setInfo(rideUpdateMessage(ride.status))
        return ride
      } catch (err) {
        setError(toUserMessage(err))
        throw err
      } finally {
        setBusy(false)
      }
    },
    [applyTrip],
  )

  const increaseOffer = useCallback(
    async (rideId: number, amount: number, version?: number) => {
      setBusy(true)
      setError(null)
      try {
        const ride = await updatePassengerOffer(rideId, {
          action: 'increase',
          amount,
          passenger_offer_version: version,
        })
        applyTrip(ride)
        setInfo('Your offer was increased.')
        return ride
      } catch (err) {
        setError(toUserMessage(err))
        throw err
      } finally {
        setBusy(false)
      }
    },
    [applyTrip],
  )

  const maintainOffer = useCallback(
    async (rideId: number, version?: number) => {
      setBusy(true)
      setError(null)
      try {
        const ride = await updatePassengerOffer(rideId, {
          action: 'maintain',
          passenger_offer_version: version,
        })
        applyTrip(ride)
        setInfo('You kept your current offer.')
        return ride
      } catch (err) {
        setError(toUserMessage(err))
        throw err
      } finally {
        setBusy(false)
      }
    },
    [applyTrip],
  )

  const selectDriverResponse = useCallback(
    async (rideId: number, responseId: number) => {
      setBusy(true)
      setError(null)
      try {
        const ride = await selectDriver(rideId, responseId)
        applyTrip(ride)
        setInfo(
          ride.agreed_fare != null
            ? `Driver selected. Agreed fare ${ride.agreed_fare.toFixed(2)}.`
            : 'Driver selected.',
        )
        await refreshResponses(rideId)
        return ride
      } catch (err) {
        setError(toUserMessage(err))
        throw err
      } finally {
        setBusy(false)
      }
    },
    [applyTrip, refreshResponses],
  )

  const ignoreResponse = useCallback(
    async (rideId: number, responseId: number) => {
      setBusy(true)
      setError(null)
      try {
        const ride = await ignoreDriverResponse(rideId, responseId)
        applyTrip(ride)
        await refreshResponses(rideId)
        setInfo('Driver response ignored.')
        return ride
      } catch (err) {
        setError(toUserMessage(err))
        throw err
      } finally {
        setBusy(false)
      }
    },
    [applyTrip, refreshResponses],
  )

  const value = useMemo(
    () => ({
      profile,
      rides,
      activeRide,
      driverLocation,
      socketStatus,
      error,
      info,
      loading,
      busy,
      setError,
      setInfo,
      refreshRides,
      refreshTrip,
      saveProfile,
      requestRide,
      cancelRideById,
      responses,
      refreshResponses,
      increaseOffer,
      maintainOffer,
      selectDriverResponse,
      ignoreResponse,
    }),
    [
      profile,
      rides,
      activeRide,
      driverLocation,
      socketStatus,
      error,
      info,
      loading,
      busy,
      refreshRides,
      refreshTrip,
      saveProfile,
      requestRide,
      cancelRideById,
      responses,
      refreshResponses,
      increaseOffer,
      maintainOffer,
      selectDriverResponse,
      ignoreResponse,
    ],
  )

  return (
    <PassengerContext.Provider value={value}>{children}</PassengerContext.Provider>
  )
}

export function usePassenger(): PassengerContextValue {
  const context = useContext(PassengerContext)
  if (!context) {
    throw new Error('usePassenger must be used within PassengerProvider')
  }
  return context
}

