import type { ReactNode } from 'react'
import type { TooltipProps } from 'recharts'
import { cn } from '@/lib/cn'

/** Хром графиков держим в одном месте: сетка — сплошная волосяная линия на шаг
 *  от фона, подписи — текстовыми чернилами, цвет несут только сами марки. */
export const AXIS = {
  tick: { fill: '#93918a', fontSize: 11 },
  axisLine: { stroke: '#dcdcd6' },
  tickLine: false,
} as const

export const GRID = { stroke: '#e6e7e2', vertical: false } as const

export const SERIES = {
  primary: '#2a78d6',
  second: '#eb6834',
  /** Порядковая шкала для воронки: шаги не светлее 250 на светлом фоне. */
  ordinal: ['#86b6ef', '#5598e7', '#2a78d6', '#1c5cab'],
} as const

export function ChartTooltip({ active, payload, label, unit }: TooltipProps<number, string> & { unit?: string }) {
  if (!active || !payload?.length) return null

  return (
    <div className="rounded-lg border border-line bg-raised px-2.5 py-2 shadow-lift">
      <div className="text-[12px] font-medium text-ink">{label}</div>
      <div className="mt-1 space-y-0.5">
        {payload.map((item) => (
          <div key={String(item.dataKey)} className="flex items-center gap-2 text-[12px]">
            <span className="size-2 shrink-0 rounded-[2px]" style={{ background: item.color }} />
            <span className="text-muted">{item.name}</span>
            <span className="num ml-auto font-medium text-ink">
              {item.value}
              {unit ?? ''}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function Legend({ items }: { items: { name: string; color: string }[] }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
      {items.map((item) => (
        <span key={item.name} className="flex items-center gap-1.5 text-[12px] text-muted">
          <span className="size-2 rounded-[2px]" style={{ background: item.color }} />
          {item.name}
        </span>
      ))}
    </div>
  )
}

export function Panel({
  title,
  hint,
  legend,
  className,
  children,
}: {
  title: string
  hint?: string
  legend?: ReactNode
  className?: string
  children: ReactNode
}) {
  return (
    <section className={cn('card px-4 pb-4 pt-3.5', className)}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-[13.5px] font-semibold text-ink">{title}</h3>
          {hint ? <p className="mt-0.5 text-[12px] text-faint">{hint}</p> : null}
        </div>
        {legend}
      </div>
      <div className="mt-3">{children}</div>
    </section>
  )
}

export function StatTile({
  label,
  value,
  hint,
  tone = 'neutral',
}: {
  label: string
  value: string
  hint?: string
  tone?: 'neutral' | 'warn' | 'good'
}) {
  return (
    <div className="card px-4 py-3">
      <div className="text-[12.5px] text-muted">{label}</div>
      <div
        className={cn(
          'mt-1 text-[24px] font-semibold leading-none tracking-[-0.015em]',
          tone === 'warn' ? 'text-warn-ink' : tone === 'good' ? 'text-good-ink' : 'text-ink',
        )}
      >
        {value}
      </div>
      {hint ? <div className="mt-1.5 text-[11.5px] text-faint">{hint}</div> : null}
    </div>
  )
}
