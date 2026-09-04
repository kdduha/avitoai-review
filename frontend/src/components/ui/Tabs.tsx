import { cn } from '@/lib/cn'

export interface TabItem {
  id: string
  label: string
  count?: number
}

export function Tabs({
  items,
  value,
  onChange,
  className,
}: {
  items: TabItem[]
  value: string
  onChange: (id: string) => void
  className?: string
}) {
  return (
    <div className={cn('flex items-end gap-1 border-b border-line', className)} role="tablist">
      {items.map((item) => {
        const active = item.id === value
        return (
          <button
            key={item.id}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(item.id)}
            className={cn(
              'relative -mb-px flex items-center gap-1.5 px-3 pb-2.5 pt-1 text-[13.5px] transition-colors',
              active
                ? 'font-semibold text-ink after:absolute after:inset-x-2 after:bottom-[-1px] after:h-0.5 after:rounded-full after:bg-accent'
                : 'font-medium text-muted hover:text-ink',
            )}
          >
            {item.label}
            {item.count !== undefined ? (
              <span className={cn('num text-[12px]', active ? 'text-muted' : 'text-faint')}>{item.count}</span>
            ) : null}
          </button>
        )
      })}
    </div>
  )
}
