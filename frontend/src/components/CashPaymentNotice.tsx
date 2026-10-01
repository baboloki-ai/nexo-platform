export function CashPaymentNotice({
  compact = false,
}: {
  compact?: boolean
}) {
  return (
    <div className="cash-notice">
      <p className="eyebrow">Payment method</p>
      <p className="cash-notice-title">Cash</p>
      {compact ? (
        <p className="muted">Pay the driver in cash.</p>
      ) : (
        <p className="muted">Pay the driver directly after the trip.</p>
      )}
    </div>
  )
}
