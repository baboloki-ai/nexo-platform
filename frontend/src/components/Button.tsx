import type { ButtonHTMLAttributes, ReactNode } from 'react'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant
  busy?: boolean
  block?: boolean
  children: ReactNode
}

export function Button({
  variant = 'primary',
  busy = false,
  block = false,
  className = '',
  disabled,
  type = 'button',
  children,
  ...rest
}: ButtonProps) {
  const classes = [
    'btn',
    `btn-${variant}`,
    block ? 'btn-block' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <button type={type} className={classes} disabled={disabled || busy} {...rest}>
      {children}
    </button>
  )
}
