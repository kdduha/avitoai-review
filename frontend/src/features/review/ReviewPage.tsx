import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, FlaskConical } from 'lucide-react'
import type { DetectionSpan, Evidence } from '@/lib/backend'
import { demoThread, getRun, setScore, setSpanVerdict } from '@/lib/runs'
import { formatDateTime, timeLeft } from '@/lib/format'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { ChatDock } from './ChatDock'
import { DetectionPanel } from './DetectionPanel'
import { DraftPanel } from './DraftPanel'
import { WorkPanel, type Highlight } from './WorkPanel'

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="border-l border-line pl-3.5 first:border-l-0 first:pl-0">
      <div className="text-[11.5px] text-faint">{label}</div>
      <div className="mt-0.5 text-[12.5px] text-ink-soft">{children}</div>
    </div>
  )
}

export function ReviewPage() {
  const { runId = '' } = useParams()

  const [workspace, setWorkspace] = useState(() => getRun(runId))
  const [activePath, setActivePath] = useState<string | null>(null)
  const [highlight, setHighlight] = useState<Highlight | null>(null)
  const [activeQuote, setActiveQuote] = useState<string | null>(null)
  const [activeSpanId, setActiveSpanId] = useState<string | null>(null)
  const [approved, setApproved] = useState(false)
  const [shownRunId, setShownRunId] = useState(runId)

  /* Роутер переиспользует компонент между прогонами: без сброса на экране
     остались бы баллы предыдущей работы. */
  if (shownRunId !== runId) {
    setShownRunId(runId)
    setWorkspace(getRun(runId))
    setActivePath(null)
    setHighlight(null)
    setActiveQuote(null)
    setActiveSpanId(null)
    setApproved(false)
  }

  if (!workspace) {
    return (
      <div className="grid min-h-screen place-items-center px-6">
        <div className="max-w-[46ch] text-center">
          <h1 className="text-[17px] font-semibold text-ink">Прогон не найден</h1>
          <p className="mt-2 text-[13.5px] leading-[1.6] text-muted">
            Результаты проверки живут в памяти вкладки: у бэкенда пока нет хранилища сдач, поэтому
            после перезагрузки прогон нужно запустить заново.
          </p>
          <Link to="/check" className="mt-4 inline-block">
            <Button variant="primary">Запустить проверку</Button>
          </Link>
        </div>
      </div>
    )
  }

  const openEvidence = (evidence: Evidence) => {
    setActivePath(evidence.artifact)
    setActiveQuote(evidence.quote)
    setActiveSpanId(null)
    setHighlight({
      path: evidence.artifact,
      startLine: evidence.start_line ?? null,
      endLine: evidence.end_line ?? null,
      origin: 'evidence',
    })
  }

  const openSpan = (span: DetectionSpan) => {
    setActivePath(span.artifact)
    setActiveSpanId(span.id)
    setActiveQuote(null)
    setHighlight({
      path: span.artifact,
      startLine: span.start_line ?? null,
      endLine: span.end_line ?? null,
      origin: 'detection',
    })
  }

  return (
    <div className="flex min-h-screen flex-col bg-plane lg:h-screen">
      <header className="shrink-0 border-b border-line bg-surface px-5 py-3">
        <div className="flex items-center justify-between gap-4">
          <Link
            to="/queue"
            className="inline-flex items-center gap-1.5 text-[12.5px] text-muted transition-colors hover:text-ink"
          >
            <ArrowLeft size={13} strokeWidth={1.8} />
            Мои проверки
          </Link>
          {workspace.live ? null : (
            <Badge tone="accent" icon={<FlaskConical size={11} strokeWidth={1.8} />}>
              демо-прогон, без обращения к модели
            </Badge>
          )}
        </div>

        <div className="mt-2 flex items-start justify-between gap-6">
          <div className="flex items-center gap-2.5">
            <Badge tone="neutral">{workspace.course}</Badge>
            <h1 className="text-[17px] font-semibold tracking-[-0.01em] text-ink">
              {workspace.assignmentTitle}
            </h1>
          </div>

          <Link to="/check">
            <Button size="sm">Новая проверка</Button>
          </Link>
        </div>

        <div className="mt-2.5 flex flex-wrap items-start gap-x-3.5 gap-y-2">
          <Fact label="Студент">
            <span
              className="font-mono text-[12px]"
              title="внутренний идентификатор: имени и логина в бандле нет намеренно"
            >
              {workspace.studentLabel.length > 12
                ? `${workspace.studentLabel.slice(0, 12)}…`
                : workspace.studentLabel}
            </span>
          </Fact>
          {workspace.submittedAt ? (
            <Fact label="Сдано">
              {formatDateTime(workspace.submittedAt)}
              {workspace.deadlineAt ? `, ${timeLeft(workspace.submittedAt, workspace.deadlineAt)}` : ''}
            </Fact>
          ) : null}
          <Fact label="Файлов в разборе">{workspace.files.length}</Fact>
          <Fact label="Токенов">
            {workspace.tokensIn} → {workspace.tokensOut}
          </Fact>
        </div>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.15fr)_minmax(0,0.8fr)]">
        <WorkPanel
          files={workspace.files}
          activePath={activePath ?? workspace.files[0]?.path ?? ''}
          onSelect={setActivePath}
          highlight={highlight}
          link={workspace.link}
          prLabel={workspace.prLabel}
        />
        <DraftPanel
          workspace={workspace}
          approved={approved}
          scoreStep={workspace.scoreStep}
          activeQuote={activeQuote}
          onScore={(criterionId, score) => setWorkspace(setScore(workspace.id, criterionId, score))}
          onEvidence={openEvidence}
          onApprove={() => setApproved(true)}
        />
        <DetectionPanel
          report={workspace.detection}
          error={workspace.detectionError}
          activeSpanId={activeSpanId}
          onSpan={openSpan}
          onVerdict={(spanId, verdict) => setWorkspace(setSpanVerdict(workspace.id, spanId, verdict))}
        />
      </div>

      <ChatDock live={workspace.live} thread={demoThread(workspace.id)} />
    </div>
  )
}
