import { AuthProvider, useAuth } from './auth/AuthContext'
import { Button } from './components/Button'
import { AppRouter } from './router'

function BootScreen() {
  const { ready, restoreError, retryRestore } = useAuth()

  if (!ready) {
    return (
      <div className="boot-screen">
        <span className="brand-mark">N</span>
        <p className="brand-name">NEXO</p>
        <p>Restoring your NEXO session…</p>
      </div>
    )
  }

  if (restoreError) {
    return (
      <div className="boot-screen">
        <span className="brand-mark">N</span>
        <p className="brand-name">NEXO</p>
        <p>{restoreError}</p>
        <Button onClick={retryRestore}>Retry</Button>
      </div>
    )
  }

  return <AppRouter />
}

export default function App() {
  return (
    <AuthProvider>
      <BootScreen />
    </AuthProvider>
  )
}
