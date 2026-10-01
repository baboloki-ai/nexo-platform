import { Button } from './Button'
import { MIN_PASSENGER_OFFER } from '../constants/fare'
import { formatCurrency } from '../utils/format'

const OFFER_STEP = 5

function roundThebe(value: number): number {
  return Math.round(value * 100) / 100
}

export function FareOfferPicker({
  recommended,
  options,
  selected,
  onChange,
  disabled = false,
  caption,
}: {
  recommended: number
  options: number[]
  selected: number
  onChange: (amount: number) => void
  disabled?: boolean
  caption?: string
}) {
  const amounts = Array.from(new Set([...options, selected]))
    .map(roundThebe)
    .filter((amount) => amount >= MIN_PASSENGER_OFFER)
    .sort((a, b) => a - b)

  return (
    <div className="fare-picker">
      <p className="eyebrow">Your offer</p>
      <div className="chip-row">
        {amounts.map((amount) => (
          <Button
            key={amount}
            variant={amount === selected ? 'primary' : 'ghost'}
            disabled={disabled}
            onClick={() => onChange(amount)}
          >
            {formatCurrency(amount)}
            {amount === roundThebe(recommended) ? ' · recommended' : ''}
          </Button>
        ))}
        <Button
          variant="ghost"
          disabled={disabled}
          onClick={() => onChange(roundThebe(selected + OFFER_STEP))}
        >
          Offer {formatCurrency(roundThebe(selected + OFFER_STEP))}
        </Button>
      </div>
      <p className="muted">
        {caption ??
          'Choose the recommended fare, increase it, or keep offering more. Cash only. Minimum is ' +
            formatCurrency(MIN_PASSENGER_OFFER) +
            '. There is no maximum.'}
      </p>
    </div>
  )
}
