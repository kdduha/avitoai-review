import { useState } from 'react'
import { ChevronDown, Minus, Plus, Quote, TriangleAlert } from 'lucide-react'
import type { Evidence } from '@/lib/backend'
import type { WorkspaceVerdict } from '@/lib/workspace'
import { cn } from '@/lib/cn'
import { Badge } from '@/components/ui/Badge'

interface Props {
  verdict: WorkspaceVerdict
  onScore: (score: number) => void
  onEvidence: (evidence: Evidence) => void
  activeQuote: string | null
  scoreStep: number
}

function evidenceLabel(evidence: Evidence): string {
  const start = evidence.start_line
  const end = evidence.end_line
  if (start && end && end !== start) return `${evidence.artifact} ${start}–${end}`
  if (start) return `${evidence.artifact} ${start}`
  return evidence.artifact
}

export function CriterionRow({ verdict, onScore, onEvidence, activeQuote, scoreStep }: Props) {
  const [editing, setEditing] = useState(false)
  const [open, setOpen] = useState(false)

  const step = (delta: number) => {
    const raw = verdict.score + delta * scoreStep
    const next = Math.max(0, Math.min(verdict.maxScore, Math.round(raw / scoreStep) * scoreStep))
    if (next !== verdict.score) onScore(Number(next.toFixed(2)))
  }

  return (
    <article className="border-b border-line-soft px-5 py-4 last:border-b-0">
      <div className="flex items-start justify-between gap-4">
        <h3 className="pt-0.5 text-[14px] font-semibold text-ink">{verdict.title}</h3>

        <div className="flex shrink-0 items-center gap-1">
          {editing ? (
            <div className="flex items-center gap-1 rounded-lg border border-accent-line bg-accent-wash px-1 py-0.5">
              <button
                onClick={() => step(-1)}
                className="grid size-6 place-items-center rounded-md text-accent-ink hover:bg-white/70"
                aria-label="Уменьшить балл"
              >
                <Minus size={13} strokeWidth={2} />
              </button>
              <span className="num w-12 text-center text-[15px] font-semibold text-ink">
                {verdict.score}
              </span>
              <button
                onClick={() => step(1)}
                className="grid size-6 place-items-center rounded-md text-accent-ink hover:bg-white/70"
                aria-label="Увеличить балл"
              >
                <Plus size={13} strokeWidth={2} />
              </button>
              <button
                onClick={() => setEditing(false)}
                className="ml-0.5 rounded-md px-1.5 py-0.5 text-[12px] font-medium text-accent-ink hover:bg-white/70"
              >
                Готово
              </button>
            </div>
          ) : (
            <button
              onClick={() => setEditing(true)}
              title="Поправить балл"
              className="num rounded-lg px-2 py-0.5 text-[15px] tracking-tight transition-colors hover:bg-sunken"
            >
              <span className="font-semibold text-ink">{verdict.score}</span>
              <span className="text-faint"> / {verdict.maxScore}</span>
            </button>
          )}
        </div>
      </div>

      {verdict.edited ? (
        <div className="mt-1.5">
          <Badge tone="accent">Балл поправлен куратором</Badge>
        </div>
      ) : null}

      <p className="mt-2 max-w-[62ch] text-[13.5px] leading-[1.6] text-ink-soft">{verdict.verdict}</p>

      {verdict.needsHumanAttention && verdict.attentionReason !== verdict.verdict ? (
        <div className="mt-2.5 flex items-start gap-1.5 text-[12.5px] text-warn-ink">
          <TriangleAlert size={13} strokeWidth={1.8} className="mt-0.5 shrink-0" />
          <span>{verdict.attentionReason}</span>
        </div>
      ) : null}

      {verdict.evidence.length ? (
        <div className="mt-3 space-y-1">
          {verdict.evidence.map((item, index) => {
            const active = activeQuote === item.quote
            const broken = item.status !== 'valid'
            return (
              <button
                key={index}
                onClick={() => onEvidence(item)}
                disabled={broken}
                className={cn(
                  'group flex w-full items-center gap-2 rounded-md py-1 pl-2 pr-2 text-left transition-colors',
                  broken
                    ? 'cursor-not-allowed opacity-60'
                    : active
                      ? 'mark'
                      : 'hover:bg-[#f4f5f2]',
                )}
              >
                <Quote size={12} strokeWidth={1.7} className="shrink-0 text-mark-rule" />
                <span className="truncate font-mono text-[12px] text-accent group-hover:text-accent-ink">
                  {evidenceLabel(item)}
                </span>
                {broken ? (
                  <span className="text-[11.5px] text-critical-ink">
                    {item.note || 'цитата не сошлась'}
                  </span>
                ) : null}
              </button>
            )
          })}
        </div>
      ) : null}

      {verdict.studentFeedback || verdict.improvementHint ? (
        <>
      <button
        onClick={() => setOpen(!open)}
        className="mt-2.5 inline-flex items-center gap-1 text-[12.5px] font-medium text-muted hover:text-ink"
      >
        <ChevronDown size={13} strokeWidth={1.8} className={cn('transition-transform', open && 'rotate-180')} />
        Что увидит студент
      </button>

      {open ? (
        <div className="mt-2 space-y-2 rounded-lg bg-[#f6f7f4] px-3 py-2.5">
          {verdict.studentFeedback ? (
            <p className="max-w-[62ch] text-[13px] leading-[1.55] text-ink-soft">{verdict.studentFeedback}</p>
          ) : null}
          {verdict.improvementHint ? (
            <p className="max-w-[62ch] text-[13px] leading-[1.55] text-muted">
              Что докрутить: {verdict.improvementHint}
            </p>
          ) : null}
        </div>
      ) : null}
        </>
      ) : null}
    </article>
  )
}
