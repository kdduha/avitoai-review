import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

type Tone = 'neutral' | 'good' | 'warn' | 'critical' | 'accent' | 'mark'

const TONES: Record<Tone, string> = {
  neutral: 'bg-sunken text-ink-soft',
  good: 'bg-good-wash text-good-ink',
  warn: 'bg-warn-wash text-warn-ink',
  critical: 'bg-critical-wash text-critical-ink',
  accent: 'bg-accent-wash text-accent-ink',
  mark: 'bg-mark text-mark-ink',
}

export function Badge({
  tone = 'neutral',
  icon,
  children,
  className,
}: {
  tone?: Tone
  icon?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[12px] font-medium leading-5',
        TONES[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  )
}
