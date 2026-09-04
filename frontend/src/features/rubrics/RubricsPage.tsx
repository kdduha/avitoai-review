import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CircleAlert, Coins, ShieldCheck } from 'lucide-react'
import { backend, type Criterion, type FormatCheck, type LatePolicy } from '@/lib/backend'
import { cn } from '@/lib/cn'
import { plural } from '@/lib/format'
import { Badge } from '@/components/ui/Badge'

const LEVEL_TONE = { blocking: 'critical', warning: 'warn', info: 'neutral' } as const

/** Правило просрочки записано в рубрике числами; куратору нужно предложение. */
function lateInWords(policy: LatePolicy | undefined): string {
  if (!policy) return 'штраф за просрочку не задан'
  const grace = policy.grace_days ?? 0
  const penalty = policy.penalty_per_grace_day ?? 0
  if (!grace && !penalty) return 'штрафа за просрочку нет'

  const head = grace
    ? `досдача в течение ${grace} ${plural(grace, 'дня', 'дней', 'дней')} — минус ${penalty} ${plural(penalty, 'балл', 'балла', 'баллов')} за день`
    : `минус ${penalty} за каждый день просрочки`
  return head + (policy.after_grace === 'zero' ? ', позже — 0 баллов' : ', дальше штраф растёт')
}

/** У части проверок методист пишет `label`, у части — нет; голое число из
 *  `params` в списке нечитаемо, поэтому у каждого вида проверки есть своя
 *  формулировка. */
function checkLabel(check: FormatCheck): string {
  const params = (check.params ?? {}) as Record<string, unknown>
  if (typeof params.label === 'string' && params.label) return params.label

  switch (check.check) {
    case 'token_budget':
      return `Объём работы — не больше ${params.max_tokens} токенов`
    case 'required_paths':
      return `Требуемые пути: ${[params.paths].flat().join(', ')}`
    case 'code_absent':
      return `В работе не должно быть: ${params.pattern}`
    default:
      return typeof params.expected === 'string' ? params.expected : check.check
  }
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
  const [selected, setSelected] = useState<string | null>(null)

  const list = useQuery({ queryKey: ['rubrics'], queryFn: backend.rubrics, retry: false })
  const current = selected ?? list.data?.[0]?.assignment_id ?? null

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
      <h1 className="text-[20px] font-semibold tracking-[-0.01em] text-ink">Рубрики</h1>
      <p className="mt-1 max-w-[68ch] text-[13.5px] leading-[1.6] text-muted">
        То, против чего ставится каждый вердикт. Промпт собирается из этой структуры, а не пишется
        руками под каждое задание.
      </p>

      {list.data && list.data.length > 1 ? (
        <div className="mt-4 flex flex-wrap gap-1.5">
          {list.data.map((item) => (
            <button
              key={item.assignment_id}
              onClick={() => setSelected(item.assignment_id)}
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
      ) : null}

      {data ? (
        <>
          <header className="mt-5">
            <h2 className="text-[16px] font-semibold text-ink">{data.title}</h2>
            <p className="mt-0.5 text-[13px] text-muted">
              {data.course}
              {data.stage ? `, этап ${data.stage}` : ''}
            </p>
            {data.source_note ? (
              <p className="mt-1.5 max-w-[70ch] text-[12.5px] leading-[1.5] text-faint">{data.source_note}</p>
            ) : null}
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
