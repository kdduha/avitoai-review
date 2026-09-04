import { useSession } from '@/app/session'
import { cn } from '@/lib/cn'
import type { Role } from '@/lib/types'

const OPTIONS: { id: Role; label: string }[] = [
  { id: 'curator', label: 'Куратор' },
  { id: 'head', label: 'Руководитель' },
]

/** Пока нет входа по-настоящему, роль переключается руками — так на демо видно
 *  обе картины прав, не заводя двух учёток. */
export function RoleSwitch() {
  const { role, setRole } = useSession()

  return (
    <div className="flex items-center rounded-lg border border-line bg-surface p-0.5">
      {OPTIONS.map((option) => (
        <button
          key={option.id}
          onClick={() => setRole(option.id)}
          aria-pressed={role === option.id}
          className={cn(
            'rounded-[6px] px-2.5 py-1 text-[12.5px] font-medium transition-colors',
            role === option.id ? 'bg-raised text-ink shadow-soft' : 'text-muted hover:text-ink',
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}
