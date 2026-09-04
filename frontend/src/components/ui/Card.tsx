import type { HTMLAttributes, ReactNode } from 'react'
import { cn } from '@/lib/cn'

export function Card({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('card', className)} {...rest} />
}

interface HeaderProps {
  title: ReactNode
  hint?: ReactNode
  action?: ReactNode
  className?: string
}

export function CardHeader({ title, hint, action, className }: HeaderProps) {
  return (
    <div className={cn('flex items-baseline justify-between gap-4 px-5 pt-4 pb-3', className)}>
      <div className="min-w-0">
        <div className="text-[13.5px] font-semibold text-ink">{title}</div>
        {hint ? <div className="mt-0.5 text-[12.5px] text-faint">{hint}</div> : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  )
}
