import { Button } from './Button'

export function ConfirmAction({
  open,
  title,
  body,
  confirmLabel = 'Confirm',
  cancelLabel = 'Back',
  danger = false,
  busy = false,
  onConfirm,
  onCancel,
}: {
  open: boolean
  title: string
  body: string
  confirmLabel?: string
  cancelLabel?: string
  danger?: boolean
  busy?: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  if (!open) return null

  return (
    <div className="confirm-backdrop" role="presentation" onClick={onCancel}>
      <div
        className="confirm-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 id="confirm-title">{title}</h2>
        <p className="muted">{body}</p>
        <div className="btn-row wrap">
          <Button
            variant={danger ? 'danger' : 'primary'}
            busy={busy}
            onClick={onConfirm}
          >
            {busy ? 'Working…' : confirmLabel}
          </Button>
          <Button variant="ghost" disabled={busy} onClick={onCancel}>
            {cancelLabel}
          </Button>
        </div>
      </div>
    </div>
  )
}
