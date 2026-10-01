import type { InputHTMLAttributes } from 'react'

type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string
  error?: string
  hint?: string
}

export function Input({
  label,
  error,
  hint,
  id,
  className = '',
  ...rest
}: InputProps) {
  const inputId = id ?? rest.name ?? label.replaceAll(' ', '-').toLowerCase()

  return (
    <label htmlFor={inputId} className={error ? 'field has-error' : 'field'}>
      {label}
      <input id={inputId} className={className} aria-invalid={Boolean(error)} {...rest} />
      {hint ? <span className="field-hint">{hint}</span> : null}
      {error ? <span className="field-error">{error}</span> : null}
    </label>
  )
}
