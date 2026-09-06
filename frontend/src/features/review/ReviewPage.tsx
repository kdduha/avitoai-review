import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, FlaskConical } from 'lucide-react'
import { ApiError, type DetectionSpan, type Evidence } from '@/lib/backend'
import { approveRun, demoThread, getRun, loadSubmission, setScore, setSpanVerdict } from '@/lib/runs'
import { formatDateTime, timeLeft } from '@/lib/format'
import { withPatchedDraft } from '@/lib/workspace'
import { cn } from '@/lib/cn'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Tabs } from '@/components/ui/Tabs'
import { ChatDock } from './ChatDock'
import { DetectionPanel } from './DetectionPanel'
import { DraftPanel } from './DraftPanel'
import { WorkPanel, type Highlight } from './WorkPanel'

type Panel = 'work' | 'draft' | 'detection'

/** Вкладки правого окна: черновик и детектор делят одно место. */
const RIGHT_PANELS = [
  { id: 'draft', label: 'Черновик оценки' },
  { id: 'detection', label: 'Признаки ГенИИ' },
]

const PANELS = [
  { id: 'work', label: 'Работа' },
  { id: 'draft', label: 'Черновик' },
  { id: 'detection', label: 'Признаки ГенИИ' },
]

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
  const [approved, setApproved] = useState(() => workspace?.status === 'approved')
  const [actionError, setActionError] = useState<string | null>(null)
  const [shownRunId, setShownRunId] = useState(runId)
  const [panel, setPanel] = useState<Panel>('draft')

  /* Роутер переиспользует компонент между прогонами: без сброса на экране
     остались бы баллы предыдущей работы. */
  if (shownRunId !== runId) {
    setShownRunId(runId)
    const next = getRun(runId)
    setWorkspace(next)
    setActivePath(null)
    setHighlight(null)
    setActiveQuote(null)
    setActiveSpanId(null)
    setApproved(next?.status === 'approved')
    setActionError(null)
    setPanel('draft')
  }

  // Открытие по прямой ссылке или из очереди: эта вкладка сама ничего не
  // запускала, локального кэша нет — тянем карточку с сервера по настоящему
  // submission_id (в отличие от `run-...` из свежего /check, тут id в URL —
  // это UUID сдачи).
  const remote = useQuery({
    queryKey: ['submission', runId],
    queryFn: () => loadSubmission(runId),
    enabled: !workspace,
    retry: false,
  })

  useEffect(() => {
    if (remote.data) {
      setWorkspace(remote.data)
      setApproved(remote.data.status === 'approved')
    }
  }, [remote.data])

  function describeError(error: unknown, fallback: string): string {
    return error instanceof ApiError ? error.message : fallback
  }

  if (!workspace) {
    if (remote.isLoading) {
      return (
        <div className="grid min-h-screen place-items-center px-6">
          <p className="text-[13.5px] text-muted">Загружаю сдачу…</p>
        </div>
      )
    }

    return (
      <div className="grid min-h-screen place-items-center px-6">
        <div className="max-w-[46ch] text-center">
          <h1 className="text-[17px] font-semibold text-ink">
            {remote.isError ? 'Сдача не найдена' : 'Прогон не найден'}
          </h1>
          <p className="mt-2 text-[13.5px] leading-[1.6] text-muted">
            {remote.isError
              ? describeError(remote.error, 'Не удалось загрузить сдачу — возможно, у вас нет к ней доступа.')
              : 'Результаты проверки живут в памяти вкладки: без бэкенда прогон нужно запустить заново.'}
          </p>
          <Link to="/check" className="mt-4 inline-block">
            <Button variant="primary">Запустить проверку</Button>
          </Link>
        </div>
      </div>
    )
  }

  /* Ниже `lg` три панели не помещаются рядом и встают в столбик, а связка
     «цитата → подсветка в коде» — главное, ради чего этот экран существует.
     В столбике она молча ломается: код уезжает на пол-экрана вверх, внутренний
     `scrollIntoView` страницу не двигает, и клик по цитате выглядит как
     промах. Поэтому на узком экране панели переключаются, а переход по цитате
     или спану сам открывает работу. На `lg` и шире всё как было. */
  const openEvidence = (evidence: Evidence) => {
    setPanel('work')
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
    setPanel('work')
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
    <div className="flex h-screen flex-col bg-plane">
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

      <div className="shrink-0 border-b border-line bg-surface px-4 lg:hidden">
        <Tabs items={PANELS} value={panel} onChange={(next) => setPanel(next as Panel)} />
      </div>

      {/* Две колонки, а не три. Панель детектора занимала треть ширины и почти
          всегда была пуста — «детектор не запускался», — а разбор из-за неё
          читался в две трети строки. Теперь справа одно окно, и ревьюер сам
          выбирает, что в нём: черновик или признаки ГенИИ. */}
      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,2fr)]">
        <div className={cn(panel === 'work' ? 'flex' : 'hidden', 'min-h-0 lg:flex')}>
        <WorkPanel
          files={workspace.files}
          activePath={activePath ?? workspace.files[0]?.path ?? ''}
          onSelect={setActivePath}
          highlight={highlight}
          link={workspace.link}
          prLabel={workspace.prLabel}
        />
        </div>

        <div
          className={cn(
            panel === 'work' ? 'hidden' : 'flex',
            'min-h-0 min-w-0 flex-col border-l border-line lg:flex',
          )}
        >
          {/* Переключатель только на широком экране: на узком те же вкладки
              уже стоят под шапкой и переключают все три панели сразу. */}
          <div className="hidden shrink-0 border-b border-line bg-surface px-4 lg:block">
            <Tabs
              items={RIGHT_PANELS}
              value={panel === 'work' ? 'draft' : panel}
              onChange={(next) => setPanel(next as Panel)}
            />
          </div>

        <div className={cn(panel === 'detection' ? 'hidden' : 'flex', 'min-h-0 flex-1 flex-col')}>
        <DraftPanel
          workspace={workspace}
          approved={approved}
          scoreStep={workspace.scoreStep}
          activeQuote={activeQuote}
          actionError={actionError}
          onScore={async (criterionId, score) => {
            setActionError(null)
            try {
              const next = await setScore(workspace.id, criterionId, score)
              if (next) setWorkspace(next)
            } catch (error) {
              setActionError(describeError(error, 'Правка не сохранилась'))
            }
          }}
          onEvidence={openEvidence}
          onApprove={async () => {
            setActionError(null)
            try {
              await approveRun(workspace.id)
              setApproved(true)
            } catch (error) {
              setActionError(describeError(error, 'Утвердить не удалось'))
            }
          }}
        />
        </div>
        <div className={cn(panel === 'detection' ? 'flex' : 'hidden', 'min-h-0 flex-1 flex-col')}>
        <DetectionPanel
          report={workspace.detection}
          error={workspace.detectionError}
          activeSpanId={activeSpanId}
          onSpan={openSpan}
          onVerdict={async (spanId, verdict) => {
            try {
              const next = await setSpanVerdict(workspace.id, spanId, verdict)
              if (next) setWorkspace(next)
            } catch (error) {
              setActionError(describeError(error, 'Вердикт по спану не сохранился'))
            }
          }}
        />
        </div>
        </div>
      </div>

      <ChatDock
        live={workspace.live}
        submissionId={workspace.submissionId}
        demoThread={demoThread(workspace.id)}
        onPatchApplied={(draft) => setWorkspace((prev) => (prev ? withPatchedDraft(prev, draft) : prev))}
      />
    </div>
  )
}
