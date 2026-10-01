export function LoadingState({
  message = 'Loading…',
}: {
  message?: string
}) {
  return (
    <div className="loading-state" role="status">
      <span className="spinner" aria-hidden="true" />
      <p>{message}</p>
    </div>
  )
}
