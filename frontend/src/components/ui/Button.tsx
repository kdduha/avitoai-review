import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { cn } from '@/lib/cn'

type Variant = 'primary' | 'secondary' | 'ghost' | 'quiet' | 'danger'
type Size = 'sm' | 'md'

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  icon?: ReactNode
}

const VARIANTS: Record<Variant, string> = {
  primary:
    'bg-accent text-white border border-accent hover:bg-accent-ink hover:border-accent-ink shadow-[0_1px_2px_rgba(23,22,20,0.08)]',
  secondary:
    'bg-raised text-ink border border-line hover:border-[#d6d4cb] hover:bg-[#fbfbf9] shadow-[0_1px_1px_rgba(23,22,20,0.03)]',
  ghost: 'bg-transparent text-muted border border-transparent hover:bg-sunken hover:text-ink',
  quiet: 'bg-sunken text-ink-soft border border-transparent hover:bg-[#e9e8e2]',
  danger: 'bg-raised text-critical-ink border border-[#f0d3d3] hover:bg-critical-wash',
}

const SIZES: Record<Size, string> = {
  sm: 'h-7 px-2.5 text-[12.5px] gap-1.5 rounded-lg',
  md: 'h-9 px-3.5 text-[13.5px] gap-2 rounded-[10px]',
}

export function Button({ variant = 'secondary', size = 'md', icon, className, children, ...rest }: Props) {
  return (
    <button
      type="button"
      className={cn(
        'inline-flex items-center justify-center font-medium transition-colors duration-150',
        'disabled:opacity-45 disabled:pointer-events-none whitespace-nowrap',
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...rest}
    >
      {icon}
      {children}
    </button>
  )
}
