export function ErrorMessage({
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

export function InfoBanner({ message }: { message: string | null }) {
  if (!message) return null
  return (
    <div className="banner banner-info" role="status">
      {message}
    </div>
  )
}

/** @deprecated Use ErrorMessage. Kept so existing C0 imports keep working. */
export const ErrorBanner = ErrorMessage
