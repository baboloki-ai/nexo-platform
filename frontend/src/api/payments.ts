import type { Payment } from '../types/payment'
import { apiRequest } from './client'

export function confirmCashPayment(paymentId: number): Promise<Payment> {
  return apiRequest<Payment>(`/payments/${paymentId}/confirm-cash`, {
    method: 'POST',
  })
}
