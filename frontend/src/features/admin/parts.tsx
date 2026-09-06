import { useState, type ReactNode } from 'react'
import { ApiError } from '@/lib/backend'
import { Button } from '@/components/ui/Button'

export function errorText(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback
}

export function ErrorLine({ children }: { children: ReactNode }) {
  if (!children) return null
  return <p className="mt-2 text-[12.5px] text-critical-ink">{children}</p>
}

/** Удаление спрашивает подтверждение на месте: модальное окно ради одной
 *  строки уводит взгляд от того, что удаляют. */
export function ConfirmDelete({
  label = 'Удалить',
  what,
  onConfirm,
  pending,
}: {
  label?: string
  what: string
  onConfirm: () => void
  pending?: boolean
}) {
  const [asked, setAsked] = useState(false)

  if (!asked) {
    return (
      <Button size="sm" variant="ghost" onClick={() => setAsked(true)} aria-label={`${label}: ${what}`}>
        {label}
      </Button>
    )
  }
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="text-[12px] text-muted">{what}?</span>
      <Button
        size="sm"
        variant="danger"
        disabled={pending}
        onClick={() => {
          setAsked(false)
          onConfirm()
        }}
      >
        {label}
      </Button>
      <Button size="sm" variant="ghost" onClick={() => setAsked(false)}>
        Отмена
      </Button>
    </span>
  )
}

export function Section({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <div className="mt-4 border-t border-line-soft pt-3">
      <div className="flex items-center gap-2">
        <h4 className="text-[12.5px] font-semibold text-ink">{title}</h4>
        {action ? <span className="ml-auto">{action}</span> : null}
      </div>
      {children}
    </div>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="mt-2 text-[12.5px] text-muted">{children}</p>
}

export function plural(count: number, one: string, few: string, many: string): string {
  const mod100 = count % 100
  const mod10 = count % 10
  const word =
    mod100 >= 11 && mod100 <= 14 ? many : mod10 === 1 ? one : mod10 >= 2 && mod10 <= 4 ? few : many
  return `${count} ${word}`
}
