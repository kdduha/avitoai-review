import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { CircleAlert, Coins, Pencil, Plus, ShieldCheck } from 'lucide-react'
import { backend, type Criterion, type RubricSummary } from '@/lib/backend'
import { checkLabel, lateInWords } from '@/lib/rubric'
import { cn } from '@/lib/cn'
import { plural } from '@/lib/format'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'

const LEVEL_TONE = { blocking: 'critical', warning: 'warn', info: 'neutral' } as const

/** Откуда взялась рубрика.
 *
 *  Компилятор и методист пишут сюда разбор: что взято из условия дословно, что
 *  решено самостоятельно и почему. Читать это нужно не каждый раз, а в споре о
 *  балле, поэтому целиком заметка разворачивается по требованию — иначе абзац
 *  на десяток строк уводит саму рубрику под сгиб. */
function SourceNote({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  const long = text.length > 220

  return (
    <div className="mt-1.5">
      <p
        className={cn(
          'max-w-[70ch] text-[12.5px] leading-[1.5] text-faint',
          long && !open && 'line-clamp-2',
        )}
      >
        {text}
      </p>
      {long ? (
        <button
          onClick={() => setOpen(!open)}
          className="mt-0.5 text-[12px] text-muted transition-colors hover:text-ink"
        >
          {open ? 'свернуть' : 'откуда рубрика'}
        </button>
      ) : null}
    </div>
  )
}

function CriterionCard({ criterion }: { criterion: Criterion }) {
  return (
    <article className="border-b border-line-soft px-5 py-4 last:border-b-0">
      <div className="flex items-start justify-between gap-4">
        <h3 className="text-[14px] font-medium text-ink">{criterion.title}</h3>
        <span className="num shrink-0 text-[13.5px] text-muted">
          до {criterion.max_score}
          {criterion.weight && criterion.weight !== 1 ? ` × ${criterion.weight}` : ''}
        </span>
      </div>

      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
        <span className="font-mono text-[11.5px] text-faint">{criterion.id}</span>
        {criterion.min_score_for_pass ? (
          <Badge tone="critical">обязательный минимум {criterion.min_score_for_pass}</Badge>
        ) : null}
        {criterion.auto_verifiable ? <Badge tone="neutral">проверяется кодом</Badge> : null}
        {criterion.ai_sensitive ? <Badge tone="mark">важна самостоятельность</Badge> : null}
      </div>

      {criterion.description ? (
        <p className="mt-2 max-w-[68ch] text-[13px] leading-[1.55] text-ink-soft">{criterion.description}</p>
      ) : null}

      {criterion.checks?.length ? (
        <ul className="mt-2.5 space-y-1 border-l border-line pl-3">
          {criterion.checks.map((check) => (
            <li key={check} className="max-w-[66ch] text-[12.5px] leading-[1.5] text-ink-soft">
              {check}
            </li>
          ))}
        </ul>
      ) : null}
    </article>
  )
}

export function RubricsPage() {
  /* Выбранная рубрика живёт в адресе: на неё возвращается редактор после
     подтверждения, и ссылку на конкретную рубрику можно передать. */
  const [params, setParams] = useSearchParams()

  const list = useQuery({ queryKey: ['rubrics'], queryFn: backend.rubrics, retry: false })

  /* Каталог рос вместе с курсами, и плоский список перестал читаться: тринадцать
     заданий подряд, и по названию не видно, чьё оно. Отсюда два уровня — курс,
     потом задание. Второй уровень показывается только там, где есть из чего
     выбирать: у девяти курсов из одиннадцати задание одно, и ряд из
     единственной кнопки был бы лишним кликом, а не выбором. */
  const courses = useMemo(() => {
    const byCourse = new Map<string, RubricSummary[]>()
    for (const item of list.data ?? []) {
      byCourse.set(item.course, [...(byCourse.get(item.course) ?? []), item])
    }
    return [...byCourse.entries()]
      .sort((left, right) => left[0].localeCompare(right[0], 'ru'))
      .map(([course, items]) => ({ course, items }))
  }, [list.data])

  const current = params.get('id') ?? courses[0]?.items[0]?.assignment_id ?? null
  const currentCourse =
    list.data?.find((item) => item.assignment_id === current)?.course ?? courses[0]?.course ?? null
  const siblings = courses.find((item) => item.course === currentCourse)?.items ?? []

  const rubric = useQuery({
    queryKey: ['rubric', current],
    queryFn: () => backend.rubric(current!),
    enabled: Boolean(current),
    retry: false,
  })

  if (list.isError) {
    return (
      <div className="mx-auto max-w-[720px] px-6 py-7">
        <div className="flex items-start gap-2.5 rounded-card border border-[#f0d3d3] bg-critical-wash px-4 py-3">
          <CircleAlert size={15} strokeWidth={1.8} className="mt-0.5 shrink-0 text-critical" />
          <p className="text-[13px] leading-[1.55] text-ink-soft">
            Каталог рубрик не загрузился — бэкенд не отвечает. Рубрики лежат в{' '}
            <code className="font-mono text-[12px]">backend/rubrics/</code>: добавить курс значит
            положить туда ещё один JSON.
          </p>
        </div>
      </div>
    )
  }

  const data = rubric.data

  return (
    <div className="mx-auto max-w-[920px] px-6 py-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-[20px] font-semibold tracking-[-0.01em] text-ink">Рубрики</h1>
          <p className="mt-1 max-w-[68ch] text-[13.5px] leading-[1.6] text-muted">
            То, против чего ставится каждый вердикт. Промпт собирается из этой структуры, а не
            пишется руками под каждое задание.
          </p>
        </div>
        <Link to="/rubrics/new">
          <Button variant="primary" icon={<Plus size={14} strokeWidth={1.9} />}>
            Новая рубрика
          </Button>
        </Link>
      </div>

      {courses.length > 1 ? (
        <div className="mt-5">
          <div className="label">Курс</div>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {courses.map(({ course, items }) => (
              <button
                key={course}
                onClick={() => setParams({ id: items[0].assignment_id })}
                className={cn(
                  'rounded-lg border px-3 py-1.5 text-[13px] transition-colors',
                  course === currentCourse
                    ? 'border-accent-line bg-accent-wash font-medium text-accent-ink'
                    : 'border-line bg-surface text-muted hover:text-ink',
                )}
              >
                {course}
                {items.length > 1 ? (
                  <span className="num ml-1.5 text-[11.5px] text-faint">{items.length}</span>
                ) : null}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {siblings.length > 1 ? (
        <div className="mt-3.5">
          <div className="label">Задание</div>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {siblings.map((item) => (
              <button
                key={item.assignment_id}
                onClick={() => setParams({ id: item.assignment_id })}
                className={cn(
                  'rounded-lg border px-3 py-1.5 text-[13px] transition-colors',
                  item.assignment_id === current
                    ? 'border-accent-line bg-accent-wash font-medium text-accent-ink'
                    : 'border-line bg-surface text-muted hover:text-ink',
                )}
              >
                {item.title}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {data ? (
        <>
          <header className="mt-5 flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <h2 className="text-[16px] font-semibold text-ink">{data.title}</h2>
              <p className="mt-0.5 text-[13px] text-muted">
                {data.course}
                {data.stage ? `, этап ${data.stage}` : ''}
              </p>
              {data.source_note ? <SourceNote text={data.source_note} /> : null}
            </div>
            <Link to={`/rubrics/${encodeURIComponent(data.assignment_id)}/edit`} className="shrink-0">
              <Button size="sm" icon={<Pencil size={13} strokeWidth={1.8} />}>
                Редактировать
              </Button>
            </Link>
          </header>

          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <div className="card px-4 py-3">
              <div className="text-[12.5px] text-muted">Шкала</div>
              <div className="num mt-1 text-[17px] font-semibold text-ink">{data.scale?.total_max} баллов</div>
              <div className="num mt-1 text-[11.5px] text-faint">
                шаг {data.scale?.step}
                {data.scale?.pass_threshold ? `, зачёт от ${data.scale.pass_threshold}` : ''}
              </div>
            </div>
            <div className="card px-4 py-3">
              <div className="text-[12.5px] text-muted">Просрочка</div>
              <div className="mt-1 max-w-[34ch] text-[12.5px] leading-[1.45] text-ink-soft">
                {lateInWords(data.late_policy)}
              </div>
            </div>
            <div className="card px-4 py-3">
              <div className="text-[12.5px] text-muted">Политика по ИИ</div>
              <div className="mt-1 text-[12.5px] leading-[1.45] text-ink-soft">
                {data.ai_policy === 'declare_required'
                  ? 'использование разрешено, но должно быть заявлено'
                  : data.ai_policy}
              </div>
            </div>
          </div>

          {data.format_gate?.length ? (
            <section className="card mt-4 overflow-hidden">
              <div className="flex items-start gap-2.5 border-b border-line px-5 py-3.5">
                <Coins size={15} strokeWidth={1.7} className="mt-0.5 shrink-0 text-faint" />
                <div>
                  <h3 className="text-[13.5px] font-semibold text-ink">
                    Format Gate: {data.format_gate.length}{' '}
                    {plural(data.format_gate.length, 'проверка', 'проверки', 'проверок')}
                  </h3>
                  <p className="mt-0.5 max-w-[68ch] text-[12px] leading-[1.5] text-faint">
                    Проходят до модели и не стоят ни одного токена: работа, не принимаемая по формату,
                    не должна стоить ни рубля.
                  </p>
                </div>
              </div>
              <ul>
                {data.format_gate.map((check, index) => (
                  <li
                    key={`${check.check}-${index}`}
                    className="flex items-start gap-3 border-b border-line-soft px-5 py-2.5 last:border-b-0"
                  >
                    <Badge tone={LEVEL_TONE[check.level as keyof typeof LEVEL_TONE] ?? 'neutral'}>
                      {check.level === 'blocking'
                        ? 'блокирует'
                        : check.level === 'warning'
                          ? 'предупреждает'
                          : 'справочно'}
                    </Badge>
                    <div className="min-w-0">
                      <div className="text-[13px] text-ink-soft">{checkLabel(check)}</div>
                      {check.note ? (
                        <div className="mt-0.5 max-w-[66ch] text-[12px] leading-[1.45] text-faint">
                          {check.note}
                        </div>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <section className="card mt-4 overflow-hidden">
            <div className="flex items-start gap-2.5 border-b border-line px-5 py-3.5">
              <ShieldCheck size={15} strokeWidth={1.7} className="mt-0.5 shrink-0 text-faint" />
              <div>
                <h3 className="text-[13.5px] font-semibold text-ink">
                  {data.criteria?.length}{' '}
                  {plural(data.criteria?.length ?? 0, 'критерий', 'критерия', 'критериев')}
                </h3>
                <p className="mt-0.5 max-w-[68ch] text-[12px] leading-[1.5] text-faint">
                  Модель отвечает по каждому пункту отдельно — от этого разброс между прогонами резко
                  падает. Сумму считает агрегатор.
                </p>
              </div>
            </div>
            {data.criteria?.map((criterion) => (
              <CriterionCard key={criterion.id} criterion={criterion} />
            ))}
          </section>
        </>
      ) : null}
    </div>
  )
}
