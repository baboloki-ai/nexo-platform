export function ErrorBanner({
  message,
  onDismiss,
}: {
  message: string | null
  onDismiss?: () => void
}) {
  if (!message) return null

  return (
    <div className="banner banner-danger" role="alert">
      <span>{message}</span>
      {onDismiss ? (
        <button type="button" className="banner-dismiss" onClick={onDismiss}>
          Dismiss
        </button>
      ) : null}
    </div>
  )
}

export { ErrorMessage, InfoBanner } from './ErrorMessage'
