import { Database } from 'lucide-react'

/** Где данные ещё не настоящие — это должно быть написано, а не подразумеваться:
 *  иначе на демо невозможно отличить работающую часть от нарисованной. */
export function MockNotice({ children }: { children: string }) {
  return (
    <div className="mb-4 flex items-start gap-2 rounded-lg border border-line bg-surface px-3 py-2">
      <Database size={13} strokeWidth={1.7} className="mt-0.5 shrink-0 text-faint" />
      <p className="max-w-[86ch] text-[12.5px] leading-[1.5] text-muted">{children}</p>
    </div>
  )
}
