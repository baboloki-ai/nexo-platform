import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import { GuestOnly, RequireAuth } from '../auth/RequireAuth'
import { DriverLayout } from '../driver/DriverLayout'
import { ForgotPasswordPage } from '../pages/auth/ForgotPasswordPage'
import { LoginPage } from '../pages/auth/LoginPage'
import { RegisterPage } from '../pages/auth/RegisterPage'
import { ResetPasswordPage } from '../pages/auth/ResetPasswordPage'
import { DriverDashboard } from '../pages/driver/DriverDashboard'
import { DriverDemandPage } from '../pages/driver/DriverDemandPage'
import { DriverHistoryPage } from '../pages/driver/DriverHistoryPage'
import { DriverPerformancePage } from '../pages/driver/DriverPerformancePage'
import { DriverRidePage } from '../pages/driver/DriverRidePage'
import { PassengerDashboard } from '../pages/passenger/PassengerDashboard'
import { PassengerHistoryPage } from '../pages/passenger/PassengerHistoryPage'
import { PassengerRidePage } from '../pages/passenger/PassengerRidePage'
import { RequestRidePage } from '../pages/passenger/RequestRidePage'
import { PassengerLayout } from '../passenger/PassengerLayout'

function HomeRedirect() {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  return (
    <Navigate to={user.role === 'driver' ? '/driver' : '/passenger'} replace />
  )
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomeRedirect />} />
        <Route
          path="/login"
          element={
            <GuestOnly>
              <LoginPage />
            </GuestOnly>
          }
        />
        <Route
          path="/register"
          element={
            <GuestOnly>
              <RegisterPage />
            </GuestOnly>
          }
        />
        <Route
          path="/forgot-password"
          element={
            <GuestOnly>
              <ForgotPasswordPage />
            </GuestOnly>
          }
        />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route
          path="/passenger"
          element={
            <RequireAuth role="passenger">
              <PassengerLayout />
            </RequireAuth>
          }
        >
          <Route index element={<PassengerDashboard />} />
          <Route path="request" element={<RequestRidePage />} />
          <Route path="ride/:id" element={<PassengerRidePage />} />
          <Route path="history" element={<PassengerHistoryPage />} />
        </Route>
        <Route
          path="/driver"
          element={
            <RequireAuth role="driver">
              <DriverLayout />
            </RequireAuth>
          }
        >
          <Route index element={<DriverDashboard />} />
          <Route path="demand" element={<DriverDemandPage />} />
          <Route path="performance" element={<DriverPerformancePage />} />
          <Route path="ride/:id" element={<DriverRidePage />} />
          <Route path="history" element={<DriverHistoryPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
