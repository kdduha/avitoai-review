import { useState } from 'react'
import { Check, ChevronDown, CircleCheck, CircleHelp, TriangleAlert } from 'lucide-react'
import type { CheckOutcome, Evidence } from '@/lib/backend'
import type { Workspace } from '@/lib/workspace'
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
  /** Правка или утверждение не долетели до сервера — 409 "уже утверждена",
   *  сеть, что угодно. `null`, пока всё в порядке. */
  actionError?: string | null
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
 *  ревьюеру важны не пройденные проверки, а те, что не прошли. */
/** Список «требуют внимания» — свёрнутой строкой, как формальные проверки.

 *  Развёрнутым он занимал по строке на критерий: шесть пунктов вида «модель не
 *  привела ни одной проверяемой цитаты» закрывали разбор целиком. Само
 *  предупреждение важно — важно и то, что оно не должно вытеснять работу. */
function Attention({ reasons }: { reasons: string[] }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="border-b border-line bg-warn-wash px-5 py-2.5">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 text-left">
        <ChevronDown
          size={13}
          strokeWidth={1.8}
          className={cn('shrink-0 text-warn transition-transform', open && 'rotate-180')}
        />
        <TriangleAlert size={13} strokeWidth={1.8} className="shrink-0 text-warn" />
        <span className="text-[12.5px] text-warn-ink">
          Требуют внимания: {reasons.length}
        </span>
        <span className="ml-auto text-[12px] text-warn-ink/70">{open ? 'свернуть' : 'посмотреть'}</span>
      </button>

      {open ? (
        <ul className="mt-2 space-y-0.5 pl-5 text-[12.5px] leading-snug text-warn-ink">
          {reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}


function Gate({ workspace }: { workspace: Workspace }) {
  const [open, setOpen] = useState(false)
  const outcomes = workspace.gate?.outcomes ?? []

  if (!outcomes.length) return null

  const failed = outcomes.filter((item) => !item.passed && !item.inconclusive)
  const unclear = outcomes.filter((item) => item.inconclusive)
  /* Непройденное дословное требование условия. Раньше оно останавливало разбор
     целиком; теперь это просто самая заметная строка в списке — гейт сообщает,
     а не запрещает. */
  const required = failed.filter((item) => item.level === 'blocking')

  return (
    <div className="border-b border-line bg-[#f8f9f6] px-5 py-2.5">
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
          <span className="text-[12.5px] font-medium text-warn-ink">
            не прошли {failed.length}
          </span>
        ) : null}
        {unclear.length ? (
          <span className="text-[12.5px] text-faint">без ответа {unclear.length}</span>
        ) : null}
      </button>

      {required.length ? (
        <p className="mt-1.5 pl-5 text-[12.5px] leading-snug text-warn-ink">
          Не выполнено требование условия: {required.map((item) => item.label).join('; ')}. Разбор
          сделан, балл по критериям это учитывает.
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
  actionError,
}: Props) {
  const verdictTexts = new Set(workspace.verdicts.map((verdict) => verdict.verdict))
  const attentionReasons = workspace.attentionReasons.filter((reason) => !verdictTexts.has(reason))

  return (
    <section className="flex min-h-0 w-full flex-1 flex-col border-b border-line bg-surface lg:border-b-0">
      <Gate workspace={workspace} />

      {/* Всё, что не критерии, живёт внутри прокрутки. Над списком остаётся
          только заголовок и одна строка формальных проверок: три блока подряд
          — отзыв, список «требуют внимания» и объяснение итога — вместе
          съедали экран, и разбор, ради которого его открывают, оказывался
          за краем. */}
      <div className="min-h-0 flex-1 overflow-y-auto">
      {workspace.summary ? (
        <div className="border-b border-line px-5 py-4">
          <h3 className="text-[12.5px] font-semibold text-ink">Отзыв о работе</h3>
          {workspace.summary.strengths?.length ? (
            <ul className="mt-1.5 space-y-1">
              {workspace.summary.strengths.map((item) => (
                <li key={item} className="text-[13px] leading-[1.55] text-muted">
                  + {item}
                </li>
              ))}
            </ul>
          ) : null}
          {workspace.summary.improvements?.length ? (
            <ul className="mt-1.5 space-y-1">
              {workspace.summary.improvements.map((item) => (
                <li key={item} className="text-[13px] leading-[1.55] text-muted">
                  − {item}
                </li>
              ))}
            </ul>
          ) : null}
          {workspace.summary.encouragement ? (
            <p className="mt-2 text-[12.5px] leading-[1.5] text-faint">
              {workspace.summary.encouragement}
            </p>
          ) : null}
        </div>
      ) : null}

      {attentionReasons.length ? <Attention reasons={attentionReasons} /> : null}

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

        {/* Объяснение итога — в конце разбора, а не в футере. В футере оно
            росло вместе с числом обязательных минимумов и закрывало собой
            последние критерии: закреплённая полоса отъедала высоту у того
            самого списка, ради которого экран и открывают. Здесь оно читается
            последним — после того, как ревьюер прошёл критерии. */}
        {!workspace.edited && (workspace.passExplanation || workspace.lateExplanation) ? (
          <div className="border-t border-line px-5 py-3.5">
            <h3 className="text-[12.5px] font-semibold text-ink">Как сложился итог</h3>
            <p className="mt-1 max-w-[70ch] text-[12.5px] leading-[1.55] text-muted">
              {[workspace.passExplanation, workspace.lateExplanation]
                .filter(Boolean)
                .join(' ')}
            </p>
          </div>
        ) : null}
      </div>

      {/* Одно громкое место — итог; действие стоит рядом с числом, которое утверждает. */}
      <footer className="shrink-0 border-t border-line bg-raised px-5 py-4">
        {actionError ? (
          <p className="mb-3 rounded-lg border border-[#f0d3d3] bg-critical-wash px-3 py-2 text-[12.5px] text-critical-ink">
            {actionError}
          </p>
        ) : null}
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="flex items-baseline gap-2">
              <span className="text-[12.5px] text-muted">
                {workspace.edited ? 'Сумма по критериям' : 'Итог'}
              </span>
              {workspace.edited ? (
                <span className="text-[12.5px] font-medium text-muted">пересчитает сервер</span>
              ) : workspace.passed === null ? (
                /* Порога нет в рубрике: ни «зачёт», ни «ниже порога» —
                   объявлять то, чего условие не задаёт, нельзя. */
                <span className="text-[12.5px] font-medium text-muted">решает ревьюер</span>
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
            {/* Обнулённый за просрочку балл выглядел как разбор, который ничего
                не нашёл. Набранное по критериям обязано стоять рядом с нулём:
                иначе хорошая работа читается как проваленная. */}
            {!workspace.edited && workspace.score !== workspace.rawScore ? (
              <p className="mt-1 text-[12px] text-muted">
                по критериям {workspace.rawScore} из {workspace.maxScore} ·{' '}
                {workspace.lateExplanation}
              </p>
            ) : null}
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
              : 'Как сложился итог — в конце разбора.'}
          </p>
          <span className="num shrink-0 text-[11.5px] text-faint" title="стоимость прогона модели">
            {workspace.costRub.toFixed(2)} ₽
          </span>
        </div>
      </footer>
    </section>
  )
}
