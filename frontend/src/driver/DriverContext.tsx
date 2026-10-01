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

import {
  getDriverProfile,
  getDriverRides,
  getMarketplaceRequests,
  goOffline,
  goOnline,
  updateDriverLocation,
} from '../api/drivers'
import {
  acceptNextRide,
  acceptRide,
  arriveAtPickup,
  cancelRide,
  completeRide,
  markDriverArrived,
  rejectRide,
  startRide,
} from '../api/rides'
import { getTrip } from '../api/trips'
import { createVehicle, getMyVehicles } from '../api/vehicles'
import { ApiError, toUserMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import {
  addDriverHistoryId,
  getDriverGps,
  getDriverHistoryIds,
  getDriverOnlineHint,
  getDriverRideId,
  getToken,
  setDriverGps,
  setDriverOnlineHint,
  setDriverRideId,
} from '../auth/session'
import { FALLBACK_DRIVER_GPS } from '../constants/location'
import { useDriverGpsWatch } from '../maps/useDriverGpsWatch'
import type { GpsWatchStatus, MapPoint } from '../maps/types'
import { isValidLatLng } from '../maps/types'
import { registerDriverPush } from '../realtime/driverPush'
import { connectDriverSocket } from '../realtime/driverSocket'
import { RideStatus, isActiveRide, isHistoricalRide, type Ride } from '../types/ride'
import type { Vehicle, VehicleCreate } from '../types/vehicle'
import type { DriverProfile } from '../types/driver'
import type { DriverOpenRequest } from '../types/marketplace'
import { isApprovedDriver } from '../types/user'
import type {
  MarketplaceRequestClosedEvent,
  RideOfferEvent,
  SocketStatus,
} from '../types/websocket'
import {
  getBrowserLocation,
  queryGpsPermission,
  type GpsPermission,
} from '../utils/geolocation'
import {
  isQueuedNextRide,
  selectActiveAssignedRide,
  selectNextRide,
} from '../utils/activeAssignedRide'
import { extractRideId } from '../utils/rideEvents'

export type GpsSource = 'browser' | 'test' | 'none'
export type GpsMode = 'live' | 'demo'
export type LocationUpdateStatus = 'idle' | 'sending' | 'ok' | 'error'

type DriverContextValue = {
  online: boolean
  latitude: string
  longitude: string
  setLatitude: (value: string) => void
  setLongitude: (value: string) => void
  gpsPermission: GpsPermission
  gpsSource: GpsSource
  gpsMode: GpsMode
  gpsConfirmed: boolean
  gpsWatchStatus: GpsWatchStatus
  gpsWatchError: string | null
  lastWatchPosition: MapPoint | null
  locationStatus: LocationUpdateStatus
  offer: RideOfferEvent | null
  requests: DriverOpenRequest[]
  ride: Ride | null
  nextRide: Ride | null
  vehicles: Vehicle[]
  profile: DriverProfile | null
  approved: boolean
  socketStatus: SocketStatus
  error: string | null
  info: string | null
  busy: boolean
  historyIds: number[]
  historyRides: Ride[]
  setError: (message: string | null) => void
  setInfo: (message: string | null) => void
  goOnlineNow: () => Promise<void>
  goOfflineNow: () => Promise<void>
  sendLocationNow: () => Promise<void>
  useLiveGps: () => void
  useDemoGps: () => Promise<void>
  acceptOffer: () => Promise<Ride | null>
  acceptNextRequest: (rideId: number) => Promise<Ride | null>
  rejectOffer: () => Promise<void>
  runLifecycle: (
    action: (rideId: number) => Promise<Ride>,
    success: string,
  ) => Promise<Ride | null>
  arrive: () => Promise<Ride | null>
  markArrived: () => Promise<Ride | null>
  start: () => Promise<Ride | null>
  complete: () => Promise<Ride | null>
  cancelAssigned: () => Promise<Ride | null>
  addVehicle: (payload: VehicleCreate) => Promise<void>
  refreshTrip: (rideId: number) => Promise<Ride>
  loadHistoryTrip: (rideId: number) => Promise<Ride>
  refreshProfile: () => Promise<DriverProfile | null>
  loadHistory: () => Promise<Ride[]>
  refreshRequests: () => Promise<DriverOpenRequest[]>
}

const DriverContext = createContext<DriverContextValue | null>(null)

export function DriverProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const storedGps = getDriverGps()
  const [online, setOnline] = useState(getDriverOnlineHint())
  const [latitude, setLatitude] = useState(
    storedGps ? String(storedGps.latitude) : String(FALLBACK_DRIVER_GPS.latitude),
  )
  const [longitude, setLongitude] = useState(
    storedGps ? String(storedGps.longitude) : String(FALLBACK_DRIVER_GPS.longitude),
  )
  const [gpsPermission, setGpsPermission] = useState<GpsPermission>('unknown')
  const [gpsSource, setGpsSource] = useState<GpsSource>(
    storedGps ? 'test' : 'none',
  )
  const [gpsMode, setGpsMode] = useState<GpsMode>('live')
  const [gpsConfirmed, setGpsConfirmed] = useState(storedGps != null)
  const [locationStatus, setLocationStatus] =
    useState<LocationUpdateStatus>('idle')
  const [offer, setOffer] = useState<RideOfferEvent | null>(null)
  const [requests, setRequests] = useState<DriverOpenRequest[]>([])
  const [ride, setRide] = useState<Ride | null>(null)
  const [nextRide, setNextRide] = useState<Ride | null>(null)
  const [vehicles, setVehicles] = useState<Vehicle[]>([])
  const [profile, setProfile] = useState<DriverProfile | null>(null)
  const [socketStatus, setSocketStatus] = useState<SocketStatus>('idle')
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [historyIds, setHistoryIds] = useState<number[]>(getDriverHistoryIds)
  const [historyRides, setHistoryRides] = useState<Ride[]>([])

  const rideRef = useRef<Ride | null>(null)
  rideRef.current = ride
  const sendingRef = useRef(false)
  const hasActiveRide = ride != null && isActiveRide(ride.status)

  const rememberHistory = useCallback((rideId: number) => {
    addDriverHistoryId(rideId)
    setHistoryIds(getDriverHistoryIds())
  }, [])

  const applyRide = useCallback(
    (next: Ride | null) => {
      if (next && isQueuedNextRide(next)) {
        setNextRide(next)
        return
      }
      setRide(next)
      if (next && isActiveRide(next.status) && next.accepted_driver_id != null) {
        setDriverRideId(next.id)
        if (next.status !== RideStatus.PENDING_DRIVER_ACCEPTANCE) {
          setOffer(null)
        }
        return
      }
      setDriverRideId(null)
      if (next && !isActiveRide(next.status)) {
        rememberHistory(next.id)
      }
    },
    [rememberHistory],
  )

  const restoreAssignedFromServer = useCallback(async () => {
    if (!user) return
    const rows = await getDriverRides()
    const currentAssigned = selectActiveAssignedRide(
      rows,
      user.id,
      getDriverRideId(),
    )
    // Keep a just-completed ride unless a Next Ride was promoted over it.
    if (currentAssigned) {
      applyRide(currentAssigned)
    } else if (!rideRef.current || isActiveRide(rideRef.current.status)) {
      applyRide(null)
    }
    setNextRide(selectNextRide(rows, user.id))
    setHistoryRides(rows.filter((item) => isHistoricalRide(item.status)))
  }, [applyRide, user])

  const refreshTrip = useCallback(
    async (rideId: number) => {
      const trip = await getTrip(rideId)
      applyRide(trip)
      return trip
    },
    [applyRide],
  )

  const loadHistoryTrip = useCallback(async (rideId: number) => {
    return getTrip(rideId)
  }, [])

  const refreshProfile = useCallback(async () => {
    const next = await getDriverProfile()
    setProfile(next)
    if (next.availability_status === 'available') {
      setOnline(true)
      setDriverOnlineHint(true)
    } else if (next.availability_status === 'offline') {
      setOnline(false)
      setDriverOnlineHint(false)
    }
    return next
  }, [])

  const loadHistory = useCallback(async () => {
    const rows = await getDriverRides()
    const historical = rows.filter((item) => isHistoricalRide(item.status))
    setHistoryRides(historical)
    return historical
  }, [])

  const refreshRequests = useCallback(async () => {
    const rows = await getMarketplaceRequests()
    setRequests(rows)
    return rows
  }, [])

  useEffect(() => {
    if (!user) return
    const driverId = user.id
    let cancelled = false
    async function restore() {
      try {
        const permission = await queryGpsPermission()
        if (!cancelled) setGpsPermission(permission)
      } catch {
        // Permissions API is optional.
      }

      try {
        const mine = await getMyVehicles()
        if (!cancelled) setVehicles(mine)
      } catch (err) {
        if (!cancelled) setError(toUserMessage(err))
      }

      try {
        const nextProfile = await getDriverProfile()
        if (!cancelled) {
          setProfile(nextProfile)
          if (nextProfile.availability_status === 'available') {
            setOnline(true)
            setDriverOnlineHint(true)
          }
        }
      } catch (err) {
        if (!cancelled) setError(toUserMessage(err))
      }

      let driverRides: Ride[] = []
      try {
        driverRides = await getDriverRides()
        if (!cancelled) {
          setHistoryRides(
            driverRides.filter((item) => isHistoricalRide(item.status)),
          )
        }
      } catch (err) {
        if (!cancelled) setError(toUserMessage(err))
      }

      try {
        const openRequests = await getMarketplaceRequests()
        if (!cancelled) setRequests(openRequests)
      } catch (err) {
        if (!cancelled) setError(toUserMessage(err))
      }

      // L4.1.1: GET /drivers/rides is the source of truth for the assigned
      // active ride. sessionStorage is only a cache written by applyRide.
      const activeAssigned = selectActiveAssignedRide(
        driverRides,
        driverId,
        getDriverRideId(),
      )
      const queuedNext = selectNextRide(driverRides, driverId)
      if (!cancelled) setNextRide(queuedNext)
      if (activeAssigned) {
        if (!cancelled) applyRide(activeAssigned)
        return
      }

      const storedRideId = getDriverRideId()
      if (!storedRideId) return
      try {
        const trip = await getTrip(storedRideId)
        if (cancelled) return
        if (trip.status === RideStatus.PENDING_DRIVER_ACCEPTANCE) {
          applyRide(trip)
          setOffer({
            event: 'ride_offer',
            ride_id: trip.id,
            pickup: trip.pickup_location,
            destination: trip.destination,
            fare: trip.proposed_fare,
          })
          return
        }
        setDriverRideId(null)
      } catch (err) {
        if (err instanceof ApiError && (err.status === 403 || err.status === 404)) {
          setDriverRideId(null)
          return
        }
        if (!cancelled) setError(toUserMessage(err))
      }
    }
    void restore()
    return () => {
      cancelled = true
    }
  }, [applyRide, user])

  useEffect(() => {
    if (!user) return
    const token = getToken()
    if (!token) return

    const handle = connectDriverSocket(user.id, token, {
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
        if (event.event === 'marketplace_request_created') {
          setInfo('New passenger request.')
          void refreshRequests().catch((err) => setError(toUserMessage(err)))
          return
        }
        if (event.event === 'passenger_offer_updated') {
          setInfo('Passenger updated their offer.')
          void refreshRequests().catch((err) => setError(toUserMessage(err)))
          return
        }
        if (event.event === 'marketplace_request_closed') {
          const closed = event as MarketplaceRequestClosedEvent
          void refreshRequests().catch((err) => setError(toUserMessage(err)))
          if (closed.won) {
            setInfo('Passenger selected you.')
            void getTrip(closed.ride_id)
              .then((trip) => {
                if (isQueuedNextRide(trip)) {
                  setNextRide(trip)
                  setInfo('Next Ride accepted.')
                  return
                }
                applyRide(trip)
              })
              .catch((err) => setError(toUserMessage(err)))
          } else {
            setInfo('That request is no longer open.')
          }
          return
        }
        if (event.event === 'payment_updated' && 'ride_id' in event) {
          const rideId = Number(event.ride_id)
          if (rideRef.current?.id === rideId) {
            void refreshTrip(rideId).catch((err) => {
              if (
                err instanceof ApiError &&
                (err.status === 403 || err.status === 404)
              ) {
                return
              }
              setError(toUserMessage(err))
            })
          } else {
            void loadHistory().catch(() => undefined)
          }
          return
        }
        if (event.event === 'ride_offer') {
          const current = rideRef.current
          if (
            current &&
            isActiveRide(current.status) &&
            current.status !== RideStatus.PENDING_DRIVER_ACCEPTANCE
          ) {
            return
          }
          const next = event as RideOfferEvent
          setOffer(next)
          setDriverRideId(next.ride_id)
          setInfo('Incoming ride request.')
          return
        }
        if (event.event === 'notification') {
          const rideId =
            extractRideId(event as unknown as Record<string, unknown>) ??
            getDriverRideId() ??
            rideRef.current?.id ??
            null
          if (!rideId) return
          void refreshTrip(rideId).catch((err) => {
            if (
              err instanceof ApiError &&
              (err.status === 403 || err.status === 404)
            ) {
              setOffer(null)
              applyRide(null)
              return
            }
            setError(toUserMessage(err))
          })
        }
      },
    })

    return () => handle.close()
  }, [user, refreshTrip, applyRide, refreshRequests, loadHistory])

  useEffect(() => {
    if (!user) return
    void registerDriverPush()
  }, [user])

  useEffect(() => {
    if (!user) return
    const onResume = () => {
      if (document.visibilityState !== 'visible') return
      void refreshRequests().catch(() => undefined)
    }
    document.addEventListener('visibilitychange', onResume)
    window.addEventListener('focus', onResume)
    return () => {
      document.removeEventListener('visibilitychange', onResume)
      window.removeEventListener('focus', onResume)
    }
  }, [user, refreshRequests])

  useEffect(() => {
    if (!online) return
    const timer = window.setInterval(() => {
      void refreshRequests().catch(() => undefined)
    }, 5000)
    return () => window.clearInterval(timer)
  }, [online, refreshRequests])

  useEffect(() => {
    if (!ride || !isActiveRide(ride.status)) return
    const timer = window.setInterval(() => {
      void refreshTrip(ride.id).catch(() => {
        // Keep last known ride if a background poll fails.
      })
    }, 5000)
    return () => window.clearInterval(timer)
  }, [ride, refreshTrip])

  const sendCoordinates = useCallback(
    async (
      lat: number,
      lon: number,
      silent = false,
      accuracy: number | null = null,
      speed: number | null = null,
      heading: number | null = null,
      timestamp: number | null = null,
    ) => {
      if (!isValidLatLng(lat, lon)) {
        throw new Error('Enter a valid latitude and longitude.')
      }
      if (sendingRef.current) return null
      sendingRef.current = true
      if (!silent) setLocationStatus('sending')
      try {
        const result = await updateDriverLocation(
          lat,
          lon,
          accuracy,
          speed,
          heading,
          timestamp,
        )
        setDriverGps({ latitude: result.latitude, longitude: result.longitude })
        setGpsConfirmed(true)
        setLatitude(String(result.latitude))
        setLongitude(String(result.longitude))
        setLocationStatus('ok')
        return result
      } catch (err) {
        setLocationStatus('error')
        throw err
      } finally {
        sendingRef.current = false
      }
    },
    [],
  )

  const onWatchPosition = useCallback(
    (point: {
      latitude: number
      longitude: number
      accuracy: number | null
      speed: number | null
      heading: number | null
      timestamp: number
    }) => {
      void sendCoordinates(
        point.latitude,
        point.longitude,
        true,
        point.accuracy,
        point.speed,
        point.heading,
        point.timestamp,
      )
        .then((result) => {
          if (result) setGpsSource('browser')
        })
        .catch(() => {
          // Keep the watch alive; the GPS panel shows the failed update.
        })
    },
    [sendCoordinates],
  )

  const gpsWatch = useDriverGpsWatch({
    enabled: (online || hasActiveRide) && gpsMode === 'live',
    onPosition: onWatchPosition,
  })

  const goOnlineNow = useCallback(async () => {
    if (!isApprovedDriver(profile?.verification_status)) {
      setError('Your driver account is awaiting verification.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const permission = await queryGpsPermission()
      setGpsPermission(permission)
      let lat = Number(latitude)
      let lon = Number(longitude)
      if (gpsMode === 'demo') {
        setGpsSource('test')
      } else {
        const browser = await getBrowserLocation()
        if (browser) {
          lat = browser.latitude
          lon = browser.longitude
          setGpsSource('browser')
          setGpsPermission('granted')
        } else {
          setGpsSource('test')
        }
      }

      if (!isValidLatLng(lat, lon)) {
        throw new Error('Enter a valid latitude and longitude before going online.')
      }

      const location = await sendCoordinates(lat, lon)
      if (!location) {
        setError('Location update is already in progress. Try going online again.')
        return
      }

      const status = await goOnline()
      setOnline(true)
      setDriverOnlineHint(true)
      setInfo(
        `${status.message} Location ${location.latitude.toFixed(4)}, ${location.longitude.toFixed(4)} sent.`,
      )
      void refreshRequests().catch(() => undefined)
      void registerDriverPush()
    } catch (err) {
      setError(toUserMessage(err))
      throw err
    } finally {
      setBusy(false)
    }
  }, [gpsMode, latitude, longitude, sendCoordinates, profile, refreshRequests])

  const goOfflineNow = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      const status = await goOffline()
      setOnline(false)
      setDriverOnlineHint(false)
      setInfo(status.message)
    } catch (err) {
      setError(toUserMessage(err))
      throw err
    } finally {
      setBusy(false)
    }
  }, [])

  const sendLocationNow = useCallback(async () => {
    const lat = Number(latitude)
    const lon = Number(longitude)
    if (!isValidLatLng(lat, lon)) {
      setError('Enter a valid latitude and longitude.')
      return
    }
    setBusy(true)
    setError(null)
    setGpsMode('demo')
    try {
      const location = await sendCoordinates(lat, lon)
      if (!location) return
      setGpsSource('test')
      setInfo(
        `Location sent: ${location.latitude.toFixed(4)}, ${location.longitude.toFixed(4)}`,
      )
    } catch (err) {
      setError(toUserMessage(err))
      throw err
    } finally {
      setBusy(false)
    }
  }, [latitude, longitude, sendCoordinates])

  const useLiveGps = useCallback(() => {
    setGpsMode('live')
    setInfo('Live location tracking is on.')
  }, [])

  const useDemoGps = useCallback(async () => {
    setGpsMode('demo')
    setLatitude(String(FALLBACK_DRIVER_GPS.latitude))
    setLongitude(String(FALLBACK_DRIVER_GPS.longitude))
    setGpsSource('test')
    if (!online && !(rideRef.current && isActiveRide(rideRef.current.status))) {
      setInfo('Gaborone fallback location loaded. Send it before you go online.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const location = await sendCoordinates(
        FALLBACK_DRIVER_GPS.latitude,
        FALLBACK_DRIVER_GPS.longitude,
      )
      if (!location) return
      setInfo(
        `Location sent: ${location.latitude.toFixed(4)}, ${location.longitude.toFixed(4)}`,
      )
    } catch (err) {
      setError(toUserMessage(err))
      throw err
    } finally {
      setBusy(false)
    }
  }, [online, sendCoordinates])

  const acceptNextRequest = useCallback(async (rideId: number) => {
    setBusy(true)
    setError(null)
    try {
      const accepted = await acceptNextRide(rideId)
      setNextRide(accepted)
      setInfo('Next Ride accepted. Current ride stays active.')
      void refreshRequests().catch(() => undefined)
      return accepted
    } catch (err) {
      setError(toUserMessage(err))
      throw err
    } finally {
      setBusy(false)
    }
  }, [refreshRequests])

  const acceptOffer = useCallback(async () => {
    const rideId = offer?.ride_id ?? ride?.id
    if (!rideId) return null
    setBusy(true)
    setError(null)
    try {
      const accepted = await acceptRide(rideId)
      applyRide(accepted)
      setOffer(null)
      setInfo('Ride accepted.')
      return accepted
    } catch (err) {
      setError(toUserMessage(err))
      throw err
    } finally {
      setBusy(false)
    }
  }, [offer, ride, applyRide])

  const rejectOffer = useCallback(async () => {
    const rideId = offer?.ride_id ?? ride?.id
    if (!rideId) return
    setBusy(true)
    setError(null)
    try {
      await rejectRide(rideId)
      setOffer(null)
      applyRide(null)
      setInfo('Ride rejected.')
    } catch (err) {
      setError(toUserMessage(err))
      throw err
    } finally {
      setBusy(false)
    }
  }, [offer, ride, applyRide])

  const runLifecycle = useCallback(
    async (action: (rideId: number) => Promise<Ride>, success: string) => {
      if (!ride) return null
      setBusy(true)
      setError(null)
      try {
        const next = await action(ride.id)
        applyRide(next)
        setInfo(success)
        return next
      } catch (err) {
        setError(toUserMessage(err))
        throw err
      } finally {
        setBusy(false)
      }
    },
    [ride, applyRide],
  )

  const arrive = useCallback(
    () => runLifecycle(arriveAtPickup, 'Heading to pickup.'),
    [runLifecycle],
  )
  const markArrived = useCallback(
    () => runLifecycle(markDriverArrived, 'Marked as arrived.'),
    [runLifecycle],
  )
  const start = useCallback(
    () => runLifecycle(startRide, 'Ride started.'),
    [runLifecycle],
  )
  const complete = useCallback(
    async () => {
      const next = await runLifecycle(completeRide, 'Trip completed.')
      try {
        await restoreAssignedFromServer()
      } catch {
        void loadHistory().catch(() => undefined)
      }
      return next
    },
    [runLifecycle, loadHistory, restoreAssignedFromServer],
  )
  const cancelAssigned = useCallback(
    async () => {
      const next = await runLifecycle(cancelRide, 'Ride cancelled.')
      void loadHistory().catch(() => undefined)
      return next
    },
    [runLifecycle, loadHistory],
  )

  const addVehicle = useCallback(async (payload: VehicleCreate) => {
    setBusy(true)
    setError(null)
    try {
      const created = await createVehicle(payload)
      setVehicles((current) => [created, ...current])
      setInfo('Vehicle saved.')
      void refreshProfile().catch(() => undefined)
    } catch (err) {
      setError(toUserMessage(err))
      throw err
    } finally {
      setBusy(false)
    }
  }, [refreshProfile])

  const value = useMemo(
    () => ({
      online,
      latitude,
      longitude,
      setLatitude,
      setLongitude,
      gpsPermission,
      gpsSource,
      gpsMode,
      gpsConfirmed,
      gpsWatchStatus: gpsWatch.status,
      gpsWatchError: gpsWatch.errorMessage,
      lastWatchPosition: gpsWatch.lastPosition,
      locationStatus,
      offer,
      requests,
      ride,
      nextRide,
      vehicles,
      profile,
      approved: isApprovedDriver(profile?.verification_status),
      socketStatus,
      error,
      info,
      busy,
      historyIds,
      historyRides,
      setError,
      setInfo,
      goOnlineNow,
      goOfflineNow,
      sendLocationNow,
      useLiveGps,
      useDemoGps,
      acceptOffer,
      acceptNextRequest,
      rejectOffer,
      runLifecycle,
      arrive,
      markArrived,
      start,
      complete,
      cancelAssigned,
      addVehicle,
      refreshTrip,
      loadHistoryTrip,
      refreshProfile,
      loadHistory,
      refreshRequests,
    }),
    [
      online,
      latitude,
      longitude,
      gpsPermission,
      gpsSource,
      gpsMode,
      gpsConfirmed,
      gpsWatch.status,
      gpsWatch.errorMessage,
      gpsWatch.lastPosition,
      locationStatus,
      offer,
      requests,
      ride,
      nextRide,
      vehicles,
      profile,
      socketStatus,
      error,
      info,
      busy,
      historyIds,
      historyRides,
      goOnlineNow,
      goOfflineNow,
      sendLocationNow,
      useLiveGps,
      useDemoGps,
      acceptOffer,
      acceptNextRequest,
      rejectOffer,
      runLifecycle,
      arrive,
      markArrived,
      start,
      complete,
      cancelAssigned,
      addVehicle,
      refreshTrip,
      loadHistoryTrip,
      refreshProfile,
      loadHistory,
      refreshRequests,
    ],
  )

  return <DriverContext.Provider value={value}>{children}</DriverContext.Provider>
}

export function useDriver(): DriverContextValue {
  const context = useContext(DriverContext)
  if (!context) {
    throw new Error('useDriver must be used within DriverProvider')
  }
  return context
}
