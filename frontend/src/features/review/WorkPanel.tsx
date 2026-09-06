import { Fragment, useLayoutEffect, useMemo, useRef } from 'react'
import { FileCode2, FileText, Scissors } from 'lucide-react'
import type { WorkspaceFile } from '@/lib/workspace'
import { cn } from '@/lib/cn'

export interface Highlight {
  path: string
  startLine: number | null
  endLine: number | null
  origin: 'evidence' | 'detection'
}

interface Props {
  files: WorkspaceFile[]
  activePath: string
  onSelect: (path: string) => void
  highlight: Highlight | null
  link: string
  prLabel: string
}

function groupByDirectory(files: WorkspaceFile[]): { dir: string; files: WorkspaceFile[] }[] {
  const groups = new Map<string, WorkspaceFile[]>()
  for (const file of files) {
    const slash = file.path.lastIndexOf('/')
    const dir = slash === -1 ? '' : file.path.slice(0, slash + 1)
    groups.set(dir, [...(groups.get(dir) ?? []), file])
  }
  return [...groups.entries()]
    .sort((a, b) => (a[0] === '' ? 1 : b[0] === '' ? -1 : a[0].localeCompare(b[0])))
    .map(([dir, group]) => ({ dir, files: group }))
}

export function WorkPanel({ files, activePath, onSelect, highlight, link, prLabel }: Props) {
  const file = files.find((item) => item.path === activePath) ?? files[0]
  const lines = useMemo(() => file?.text.split('\n') ?? [], [file])
  const codeRef = useRef<HTMLDivElement>(null)

  const marked = highlight?.path === file?.path ? highlight : null

  /* Прокрутка к процитированной строке.
   *
   *  `useLayoutEffect`, а не `useEffect`: на узком экране панель работы в момент
   *  перехода по цитате только что показалась вместо черновика, и мерить её
   *  нужно уже с новыми стилями. Слой раскладки React выполняет после правки
   *  DOM и до отрисовки, а `getBoundingClientRect` заставляет браузер посчитать
   *  раскладку синхронно — то есть замер честный, и ждать кадра не нужно. Через
   *  `requestAnimationFrame` это делать нельзя: в фоновом окне кадры не идут, и
   *  прокрутка не случилась бы вовсе.
   *
   *  Смещение считается вручную, а не через `scrollIntoView`: тот прокручивает
   *  всю цепочку контейнеров вверх, а нужен ровно один — вьювер кода. */
  useLayoutEffect(() => {
    const line = marked?.startLine
    if (!line) return

    const container = codeRef.current
    const row = container?.querySelector(`[data-line="${line}"]`)
    if (!container || !row || container.clientHeight === 0) return

    const offset = row.getBoundingClientRect().top - container.getBoundingClientRect().top
    container.scrollTo({
      top: container.scrollTop + offset - container.clientHeight / 2,
      /* `scrollTo` не смотрит на CSS, поэтому системную настройку «меньше
         движения» приходится спрашивать самим — иначе переход по цитате
         останется единственной анимацией, которую она не выключает. */
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
    })
  }, [marked])

  if (!file) {
    return (
      <section className="grid place-items-center border-b border-line bg-surface p-6 lg:border-b-0 lg:border-r">
        <p className="max-w-[36ch] text-center text-[13px] text-muted">
          В сдаче нет файлов, которые можно показать.
        </p>
      </section>
    )
  }

  return (
    <section className="flex min-h-0 w-full flex-1 flex-col border-b border-line bg-surface lg:border-b-0">
      <header className="flex h-11 shrink-0 items-center justify-between gap-3 border-b border-line px-4">
        <h2 className="text-[13px] font-semibold text-ink">Работа</h2>
        <a
          href={link}
          target="_blank"
          rel="noreferrer"
          className="font-mono text-[12px] text-accent hover:text-accent-ink hover:underline"
        >
          {prLabel}
        </a>
      </header>

      <div
        className="max-h-[288px] shrink-0 overflow-y-auto border-b border-line px-2 py-2.5"
        style={{ maskImage: 'linear-gradient(to bottom, #000 calc(100% - 14px), transparent)' }}
      >
        {groupByDirectory(files).map((group) => (
          <div key={group.dir} className="mb-1.5 last:mb-0">
            {group.dir ? (
              <div className="px-2 py-0.5 font-mono text-[11.5px] text-faint">{group.dir}</div>
            ) : null}
            {group.files.map((item) => {
              const active = item.path === file.path
              const Icon = item.lang === 'markdown' ? FileText : FileCode2
              return (
                <button
                  key={item.path}
                  onClick={() => onSelect(item.path)}
                  className={cn(
                    'flex w-full items-center gap-2 rounded-md px-2 py-1 text-left transition-colors',
                    group.dir ? 'pl-4' : '',
                    active ? 'bg-sunken' : 'hover:bg-[#f4f5f2]',
                  )}
                >
                  <Icon size={13} strokeWidth={1.6} className="shrink-0 text-faint" />
                  <span
                    className={cn(
                      'flex-1 truncate font-mono text-[12.5px]',
                      active ? 'font-medium text-ink' : 'text-ink-soft',
                    )}
                  >
                    {item.path.slice(group.dir.length)}
                  </span>
                  {item.partial ? (
                    <Scissors size={11} strokeWidth={1.7} className="shrink-0 text-warn" aria-label="файл показан фрагментом" />
                  ) : null}
                  {item.hasFindings ? (
                    <span className="size-1.5 shrink-0 rounded-full bg-mark-rule" title="есть цитаты или сигналы" />
                  ) : null}
                </button>
              )
            })}
          </div>
        ))}
      </div>

      {file.partial ? (
        <p className="shrink-0 border-b border-line bg-warn-wash px-4 py-2 text-[12px] leading-snug text-warn-ink">
          Файл показан фрагментом — {file.changedLines || 'доступны не все строки'}. Вывод «этого в
          работе нет» здесь ненадёжен: модель видела не весь текст.
        </p>
      ) : null}

      <div ref={codeRef} className="min-h-0 flex-1 overflow-auto py-3">
        <table className="w-full border-separate border-spacing-0 font-mono text-[12.5px] leading-[1.65]">
          <tbody>
            {lines.map((line, index) => {
              /* Номер берётся из line_numbers, а не из позиции: у фрагмента из
                 диффа строки идут с пропусками, и цитата ссылается на номер в
                 полной версии файла. */
              const number = file.lineNumbers[index] ?? index + 1
              const gap = index > 0 && number !== (file.lineNumbers[index - 1] ?? 0) + 1
              const inMark =
                marked?.startLine != null &&
                number >= marked.startLine &&
                number <= (marked.endLine ?? marked.startLine)
              return (
                <Fragment key={number}>
                  {gap ? (
                    <tr aria-hidden>
                      <td colSpan={2} className="py-1">
                        <div className="border-t border-dashed border-line" />
                      </td>
                    </tr>
                  ) : null}
                  <tr data-line={number} className={cn(inMark && 'mark')}>
                    <td className="num w-12 select-none pr-3 text-right align-top text-faint">{number}</td>
                    <td className="whitespace-pre-wrap break-words pr-4 text-ink-soft">{line || ' '}</td>
                  </tr>
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="flex shrink-0 items-center justify-between gap-3 border-t border-line px-4 py-2 text-[12px] text-faint">
        <span>строки этой сдачи: {file.changedLines || '—'}</span>
        {marked ? (
          <span className="text-muted">
            подсвечено {marked.origin === 'evidence' ? 'по цитате' : 'по сигналу ГенИИ'}
          </span>
        ) : null}
      </div>
    </section>
  )
}
