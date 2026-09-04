import { useState } from 'react'
import { Check, ChevronDown, CircleCheck, CircleHelp, TriangleAlert } from 'lucide-react'
import type { CheckOutcome, Evidence } from '@/lib/backend'
import type { Workspace } from '@/lib/workspace'
import { percent } from '@/lib/format'
import { cn } from '@/lib/cn'
import { Button } from '@/components/ui/Button'
import { CriterionRow } from './CriterionRow'

interface Props {
  workspace: Workspace
  approved: boolean
  scoreStep: number
  onScore: (criterionId: string, score: number) => void
  onEvidence: (evidence: Evidence) => void
  onApprove: () => void
  activeQuote: string | null
}

function outcomeIcon(outcome: CheckOutcome) {
  if (outcome.inconclusive) return <CircleHelp size={13} strokeWidth={1.7} className="text-faint" />
  if (outcome.passed) return <CircleCheck size={13} strokeWidth={1.7} className="text-good" />
  return (
    <TriangleAlert
      size={13}
      strokeWidth={1.7}
      className={outcome.level === 'blocking' ? 'text-critical' : 'text-warn'}
    />
  )
}

/** Format Gate — детерминированная часть проверки. Свёрнут, пока всё сошлось:
 *  куратору важны не пройденные проверки, а те, что не прошли. */
function Gate({ workspace }: { workspace: Workspace }) {
  const [open, setOpen] = useState(false)
  const outcomes = workspace.gate?.outcomes ?? []

  if (!outcomes.length) return null

  const failed = outcomes.filter((item) => !item.passed && !item.inconclusive)
  const unclear = outcomes.filter((item) => item.inconclusive)
  const blocked = workspace.gate?.status === 'blocked'

  return (
    <div className={cn('border-b border-line px-5 py-2.5', blocked ? 'bg-critical-wash' : 'bg-[#f8f9f6]')}>
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 text-left">
        <ChevronDown
          size={13}
          strokeWidth={1.8}
          className={cn('shrink-0 text-faint transition-transform', open && 'rotate-180')}
        />
        <span className="text-[12.5px] text-muted">
          Формальные проверки: {outcomes.length - failed.length - unclear.length} из {outcomes.length}
        </span>
        {failed.length ? (
          <span className={cn('text-[12.5px] font-medium', blocked ? 'text-critical-ink' : 'text-warn-ink')}>
            не прошли {failed.length}
          </span>
        ) : null}
        {unclear.length ? (
          <span className="text-[12.5px] text-faint">без ответа {unclear.length}</span>
        ) : null}
      </button>

      {blocked ? (
        <p className="mt-1.5 pl-5 text-[12.5px] leading-snug text-critical-ink">
          Работа не принимается по формату, поэтому модель не запускалась — прогон не стоил ни рубля.
        </p>
      ) : null}

      {open ? (
        <ul className="mt-2 space-y-1.5 pl-5">
          {outcomes.map((item, index) => (
            <li key={`${item.check}-${index}`} className="flex items-start gap-2 text-[12.5px]">
              <span className="mt-0.5 shrink-0">{outcomeIcon(item)}</span>
              <span className="min-w-0">
                <span className="text-ink-soft">{item.label}</span>
                {item.detail ? <span className="text-faint"> — {item.detail}</span> : null}
                {item.locations?.length ? (
                  <span className="ml-1.5 font-mono text-[11.5px] text-faint">
                    {item.locations.join(', ')}
                  </span>
                ) : null}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

export function DraftPanel({
  workspace,
  approved,
  scoreStep,
  onScore,
  onEvidence,
  onApprove,
  activeQuote,
}: Props) {
  const verdictTexts = new Set(workspace.verdicts.map((verdict) => verdict.verdict))
  const attentionReasons = workspace.attentionReasons.filter((reason) => !verdictTexts.has(reason))

  return (
    <section className="flex max-h-[78vh] min-h-0 flex-col border-b border-line bg-surface lg:max-h-none lg:border-b-0 lg:border-r">
      <header className="flex h-11 shrink-0 items-center justify-between gap-3 border-b border-line px-5">
        <h2 className="text-[13px] font-semibold text-ink">Черновик оценки</h2>
        <span className="text-[12px] text-faint">
          цитаты подтверждены у {percent(workspace.evidenceCoverage)} вердиктов
        </span>
      </header>

      <Gate workspace={workspace} />

      {attentionReasons.length ? (
        <div className="border-b border-line bg-warn-wash px-5 py-2.5">
          <div className="flex items-start gap-2">
            <TriangleAlert size={13} strokeWidth={1.8} className="mt-0.5 shrink-0 text-warn" />
            <ul className="space-y-0.5 text-[12.5px] leading-snug text-warn-ink">
              {attentionReasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}

      <div className="min-h-0 flex-1 overflow-y-auto">
        {workspace.verdicts.map((verdict) => (
          <CriterionRow
            key={verdict.criterionId}
            verdict={verdict}
            activeQuote={activeQuote}
            scoreStep={scoreStep}
            onScore={(score) => onScore(verdict.criterionId, score)}
            onEvidence={onEvidence}
          />
        ))}
      </div>

      {/* Одно громкое место — итог; действие стоит рядом с числом, которое утверждает. */}
      <footer className="shrink-0 border-t border-line bg-raised px-5 py-4">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="flex items-baseline gap-2">
              <span className="text-[12.5px] text-muted">
                {workspace.edited ? 'Сумма по критериям' : 'Итог'}
              </span>
              {workspace.edited ? (
                <span className="text-[12.5px] font-medium text-muted">пересчитает сервер</span>
              ) : (
                <span
                  className={cn(
                    'text-[12.5px] font-medium',
                    workspace.passed ? 'text-good-ink' : 'text-critical-ink',
                  )}
                >
                  {workspace.passed ? 'зачёт' : 'ниже порога'}
                </span>
              )}
            </div>
            <div className="mt-0.5 flex items-baseline gap-1.5">
              <span className="text-[38px] font-semibold leading-none tracking-[-0.02em] text-ink">
                {workspace.edited ? workspace.rawScore : workspace.score}
              </span>
              <span className="num text-[16px] leading-none text-faint">/ {workspace.maxScore}</span>
            </div>
          </div>

          <Button
            variant="primary"
            onClick={onApprove}
            disabled={approved}
            icon={approved ? <Check size={15} strokeWidth={2} /> : undefined}
          >
            {approved ? 'Оценка утверждена' : 'Утвердить оценку'}
          </Button>
        </div>

        <div className="mt-3 flex items-baseline justify-between gap-4 border-t border-line-soft pt-2.5">
          <p className="max-w-[46ch] text-[12px] leading-snug text-faint">
            {workspace.edited
              ? 'Штраф за просрочку и обязательные минимумы считает агрегатор — итог станет точным после сохранения правок.'
              : `${workspace.passExplanation} ${workspace.lateExplanation}`}
          </p>
          <span className="num shrink-0 text-[11.5px] text-faint" title="стоимость прогона модели">
            {workspace.costRub.toFixed(2)} ₽
          </span>
        </div>
      </footer>
    </section>
  )
}
