const BW_LOCALE = 'en-BW'

export function formatCurrency(value: number): string {
  const amount = Number.isFinite(value) ? value : 0
  return `P${amount.toFixed(2)}`
}

export function formatEta(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return '—'
  const minutes = Math.max(1, Math.round(seconds / 60))
  return `${minutes} min`
}

export function formatKm(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${value.toFixed(1)} km`
}

/** @deprecated Use formatCurrency. Kept so existing imports keep working. */
export function formatFare(value: number): string {
  return formatCurrency(value)
}

export function formatCoord(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return value.toFixed(5)
}

export function formatPlace(
  label: string | null | undefined,
  latitude?: number | null,
  longitude?: number | null,
): string {
  const text = label?.trim()
  if (text) return text
  if (
    latitude != null &&
    longitude != null &&
    Number.isFinite(latitude) &&
    Number.isFinite(longitude)
  ) {
    return `${formatCoord(latitude)}, ${formatCoord(longitude)}`
  }
  return 'Location not set'
}

export function formatWhen(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString(BW_LOCALE, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

export function isBotswanaPhone(value: string): boolean {
  const compact = value.replace(/[\s()-]/g, '')
  if (/^\+267\d{7,8}$/.test(compact)) return true
  if (/^267\d{7,8}$/.test(compact)) return true
  if (/^0?7\d{7}$/.test(compact)) return true
  return false
}

export function formatPhone(value: string | null | undefined): string {
  if (!value) return '—'
  const compact = value.replace(/[\s()-]/g, '')
  const match = compact.match(/^\+?267(\d{7,8})$/)
  if (!match) return value
  const national = match[1]
  if (national.length === 8) {
    return `+267 ${national.slice(0, 2)} ${national.slice(2, 5)} ${national.slice(5)}`
  }
  if (national.length === 7) {
    return `+267 ${national.slice(0, 3)} ${national.slice(3)}`
  }
  return `+267 ${national}`
}
