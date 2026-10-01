export const PaymentStatus = {
  PENDING: 'pending',
  PROCESSING: 'processing',
  PAID: 'paid',
  FAILED: 'failed',
  CANCELLED: 'cancelled',
  REFUNDED: 'refunded',
} as const

export type PaymentStatusValue =
  (typeof PaymentStatus)[keyof typeof PaymentStatus]

export const PaymentMethod = {
  CASH: 'cash',
} as const

export type PaymentMethodValue = (typeof PaymentMethod)[keyof typeof PaymentMethod]

export type Payment = {
  id: number
  ride_id: number
  amount: number
  currency: string
  method: string
  status: string
  paid_at: string | null
  settlement_status: string
}

export function formatPaymentAmount(amount: number): string {
  const quantized = Math.round(Number(amount) * 100) / 100
  if (!Number.isFinite(quantized)) return 'P0'
  if (Math.abs(quantized - Math.round(quantized)) < 0.001) {
    return `P${Math.round(quantized)}`
  }
  return `P${quantized.toFixed(2)}`
}

export function isCashPending(payment: Payment | null | undefined): boolean {
  return (
    payment != null &&
    payment.method === PaymentMethod.CASH &&
    payment.status === PaymentStatus.PENDING
  )
}

export function isPaymentPaid(payment: Payment | null | undefined): boolean {
  return payment != null && payment.status === PaymentStatus.PAID
}

export function paymentHistoryLabel(
  payment: Payment | null | undefined,
): string | null {
  if (payment == null) return null
  if (payment.status === PaymentStatus.PAID) return 'Payment received'
  if (payment.status === PaymentStatus.PENDING) return 'Payment pending'
  return null
}
