import { Check, Info, X } from 'lucide-react'
import type { DetectionReport, DetectionSpan, SignalKind, SignalResult } from '@/lib/backend'
import { cn } from '@/lib/cn'
import { Button } from '@/components/ui/Button'

const SIGNAL_NAMES: Record<SignalKind, string> = {
  forensics: 'история коммитов',
  perplexity: 'перплексия',
  stylometry: 'стилометрия',
  judge: 'модель-судья',
}

type Verdict = 'pending' | 'confirmed' | 'rejected'

interface Props {
  report: DetectionReport | null
  error: string | null
  onSpan: (span: DetectionSpan) => void
  onVerdict: (spanId: string, verdict: Verdict) => void
  activeSpanId: string | null
}

/** Точечная оценка бессмысленна без интервала, поэтому шкала показывает
 *  именно интервал, а само число — только засечкой внутри него. */
function Meter({ report }: { report: DetectionReport }) {
  const low = (report.confidence_low ?? 0) * 100
  const high = (report.confidence_high ?? 0) * 100
  const point = (report.overall_score ?? 0) * 100

  return (
    <div className="px-5 pb-4 pt-3.5">
      <div className="flex items-baseline justify-between">
        <span className="text-[13px] text-ink-soft">{report.label}</span>
        <span className="num text-[19px] font-semibold tracking-tight text-ink">
          {(report.overall_score ?? 0).toFixed(2)}
        </span>
      </div>

      <div className="relative mt-2.5 h-1.5 rounded-full bg-sunken">
        <div
          className="absolute h-full rounded-full bg-warn-wash"
          style={{ left: `${low}%`, width: `${Math.max(0, high - low)}%` }}
        />
        <div
          className="absolute top-[-3px] h-3 w-[2.5px] rounded-full bg-warn"
          style={{ left: `calc(${point}% - 1.25px)` }}
        />
      </div>

      <div className="num mt-1.5 text-[11.5px] text-faint">
        интервал {(report.confidence_low ?? 0).toFixed(2)} — {(report.confidence_high ?? 0).toFixed(2)}
      </div>
    </div>
  )
}

/** Какие сигналы вообще отработали. Недоступный сигнал — не ноль, а «не
 *  смотрели», и это должно быть видно до того, как ревьюер сделает вывод. */
function Signals({ signals }: { signals: SignalResult[] }) {
  if (!signals.length) return null

  return (
    <div className="px-5 pb-3.5">
      <ul className="space-y-1">
        {signals.map((signal) => {
          const off = signal.status !== 'ok'
          return (
            <li key={signal.kind} className="flex items-baseline gap-2 text-[12px]">
              <span className={cn('flex-1', off ? 'text-faint' : 'text-ink-soft')}>
                {SIGNAL_NAMES[signal.kind]}
              </span>
              <span className="num text-faint">вес {(signal.weight ?? 0).toFixed(2)}</span>
              <span className={cn('num w-9 text-right', off ? 'text-faint' : 'text-ink')}>
                {off ? '—' : (signal.score ?? 0).toFixed(2)}
              </span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function SpanCard({
  span,
  active,
  onOpen,
  onVerdict,
}: {
  span: DetectionSpan
  active: boolean
  onOpen: () => void
  onVerdict: (verdict: Verdict) => void
}) {
  const decided = span.reviewer_verdict !== 'pending'

  return (
    <div
      className={cn(
        'rounded-lg border px-3 py-2.5 transition-colors',
        active ? 'border-mark-rule bg-mark' : 'border-line bg-raised',
        decided && 'opacity-70',
      )}
    >
      <button onClick={onOpen} className="w-full text-left">
        <div className="flex items-baseline justify-between gap-2">
          <span className="truncate font-mono text-[12px] text-accent">
            {span.artifact}
            {span.start_line ? ` ${span.start_line}–${span.end_line}` : ''}
          </span>
          <span className="num shrink-0 text-[12px] text-muted">{(span.score ?? 0).toFixed(2)}</span>
        </div>
        <p className="mt-1.5 text-[12.5px] leading-[1.5] text-ink-soft">{span.reason}</p>
        <p className="mt-1.5 text-[11.5px] text-faint">
          {(span.signals ?? []).map((kind) => SIGNAL_NAMES[kind]).join(', ')}
        </p>
      </button>

      <div className="mt-2.5 flex items-center gap-1.5">
        {decided ? (
          <span
            className={cn(
              'text-[12px] font-medium',
              span.reviewer_verdict === 'confirmed' ? 'text-warn-ink' : 'text-muted',
            )}
          >
            {span.reviewer_verdict === 'confirmed' ? 'Сигнал подтверждён' : 'Сигнал отклонён'}
          </span>
        ) : (
          <>
            <Button size="sm" onClick={() => onVerdict('confirmed')} icon={<Check size={12} strokeWidth={2} />}>
              Подтвердить
            </Button>
            <Button size="sm" variant="ghost" onClick={() => onVerdict('rejected')} icon={<X size={12} strokeWidth={2} />}>
              Отклонить
            </Button>
          </>
        )}
      </div>
    </div>
  )
}

export function DetectionPanel({ report, error, onSpan, onVerdict, activeSpanId }: Props) {
  return (
    <section className="flex min-h-0 flex-col bg-surface">
      <header className="flex h-11 shrink-0 items-center justify-between border-b border-line px-5">
        <h2 className="text-[13px] font-semibold text-ink">Признаки ГенИИ</h2>
        <span className="text-[12px] text-faint">рекомендательно</span>
      </header>

      {!report ? (
        <div className="flex flex-1 items-start px-5 py-5">
          <p className="max-w-[38ch] text-[13px] leading-[1.55] text-muted">
            {error ?? 'Детектор для этой работы не запускался.'}
          </p>
        </div>
      ) : (
        <>
          <Meter report={report} />
          <Signals signals={report.signals ?? []} />

          {report.mismatch ? (
            <div className="mx-5 mb-4 rounded-lg border border-[#f0e2c2] bg-warn-wash px-3 py-2.5">
              <div className="text-[12.5px] font-medium text-warn-ink">Использование ИИ не заявлено</div>
              <p className="mt-1 text-[12px] leading-[1.5] text-warn-ink/85">
                По условиям курса нарушение — не сам ИИ, а необъявленный ИИ. {report.declaration_note}
              </p>
            </div>
          ) : null}

          <div className="min-h-0 flex-1 space-y-2 overflow-y-auto px-5 pb-4">
            {(report.spans ?? []).length ? (
              (report.spans ?? []).map((span) => (
                <SpanCard
                  key={span.id}
                  span={span}
                  active={activeSpanId === span.id}
                  onOpen={() => onSpan(span)}
                  onVerdict={(verdict) => onVerdict(span.id, verdict)}
                />
              ))
            ) : (
              <p className="text-[13px] text-muted">Подозрительных фрагментов не нашлось.</p>
            )}
          </div>

          {/* Ограничения приезжают только про этот прогон — недоступный сигнал,
              файл, доступный фрагментом. Постоянной сноски здесь больше нет,
              поэтому список бывает пустым, и тогда футера быть не должно:
              рамка с иконкой и без текста читается как потерянный текст. */}
          {report.limitations?.length ? (
            <footer className="shrink-0 border-t border-line px-5 py-3.5">
              <div className="flex gap-2 text-[11.5px] leading-[1.5] text-faint">
                <Info size={13} strokeWidth={1.7} className="mt-0.5 shrink-0" />
                <ul className="space-y-0.5">
                  {report.limitations.map((limit) => (
                    <li key={limit}>{limit}</li>
                  ))}
                </ul>
              </div>
            </footer>
          ) : null}
        </>
      )}
    </section>
  )
}
