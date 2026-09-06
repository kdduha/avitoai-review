import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, ArrowRight, CircleAlert, Play } from 'lucide-react'
import { ApiError, backend, type SubmissionStatus } from '@/lib/backend'
import { prLabel } from '@/lib/workspace'
import { formatDateTime, plural } from '@/lib/format'
import { cn } from '@/lib/cn'
import { useSession } from '@/app/session'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'

const STATUS_LABEL: Record<SubmissionStatus, string> = {
  draft_ready: 'черновик готов',
  analyzing: 'считается заново',
  in_review: 'на проверке',
  approved: 'утверждена',
  failed: 'сбой разбора',
}

const STATUS_TONE: Record<SubmissionStatus, 'neutral' | 'good' | 'warn' | 'critical' | 'mark'> = {
  draft_ready: 'mark',
  analyzing: 'neutral',
  in_review: 'neutral',
  approved: 'good',
  failed: 'critical',
}

export function QueuePage() {
  const { role } = useSession()
  /* Руководителю очередь показывалась только целиком, и работу, которую он
     запустил сам, было не найти среди чужих. Своя — по умолчанию, весь поток —
     переключателем рядом. */
  const [seeAll, setSeeAll] = useState(false)

  const queue = useQuery({
    queryKey: ['queue', seeAll],
    queryFn: () => backend.myQueue(seeAll),
    retry: false,
  })
  const rubrics = useQuery({ queryKey: ['rubrics'], queryFn: backend.rubrics, retry: false })

  const rubricById = new Map((rubrics.data ?? []).map((item) => [item.assignment_id, item]))

  if (queue.isError) {
    return (
      <div className="mx-auto max-w-[720px] px-6 py-7">
        <div className="flex items-start gap-2.5 rounded-card border border-[#f0d3d3] bg-critical-wash px-4 py-3">
          <CircleAlert size={15} strokeWidth={1.8} className="mt-0.5 shrink-0 text-critical" />
          <div>
            <div className="text-[13px] font-medium text-critical-ink">Очередь не загрузилась</div>
            <p className="mt-1 max-w-[60ch] text-[12.5px] leading-[1.55] text-ink-soft">
              {queue.error instanceof ApiError ? queue.error.message : 'Бэкенд недоступен'}
            </p>
          </div>
        </div>
      </div>
    )
  }

  const rows = queue.data ?? []

  return (
    <div className="mx-auto max-w-[880px] px-6 py-7">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-[20px] font-semibold tracking-[-0.01em] text-ink">
            {seeAll ? 'Все проверки' : 'Мои проверки'}
          </h1>
          <p className="mt-1 text-[13.5px] text-muted">
            {queue.isLoading
              ? 'Загружаю…'
              : `${rows.length} ${plural(rows.length, 'сдача', 'сдачи', 'сдач')}${seeAll ? ' по всему потоку' : ''}.`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {role === 'admin' ? (
            <div className="flex items-center rounded-lg border border-line bg-surface p-0.5">
              {([false, true] as const).map((value) => (
                <button
                  key={String(value)}
                  onClick={() => setSeeAll(value)}
                  aria-pressed={seeAll === value}
                  className={cn(
                    'rounded-[6px] px-2.5 py-1 text-[12.5px] font-medium transition-colors',
                    seeAll === value ? 'bg-raised text-ink shadow-soft' : 'text-muted hover:text-ink',
                  )}
                >
                  {value ? 'Весь поток' : 'Мои'}
                </button>
              ))}
            </div>
          ) : null}
          <Link to="/check">
            <Button variant="primary" icon={<Play size={14} strokeWidth={1.9} />}>
              Проверить работу
            </Button>
          </Link>
        </div>
      </div>

      <div className="mt-5 space-y-2">
        {rows.map((submission) => {
          const rubric = rubricById.get(submission.assignment_id)
          return (
            <Link
              key={submission.id}
              to={`/review/${submission.id}`}
              className="group flex items-center gap-4 rounded-card border border-line bg-surface px-4 py-3.5 transition-colors hover:border-[#d6d7d1] hover:bg-raised"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <Badge tone="neutral">{rubric?.course ?? submission.assignment_id}</Badge>
                  <span className="truncate text-[14px] font-medium text-ink">
                    {rubric?.title ?? submission.assignment_id}
                  </span>
                  {submission.needs_human_attention ? (
                    <AlertTriangle size={13} strokeWidth={1.9} className="shrink-0 text-warn" />
                  ) : null}
                </div>
                <div className="mt-1 flex items-center gap-2 text-[12.5px] text-muted">
                  <span>{prLabel(submission.origin_url)}</span>
                  {seeAll && submission.reviewer_username ? (
                    <>
                      <span className="text-faint">·</span>
                      <span>{submission.reviewer_username}</span>
                    </>
                  ) : null}
                  {submission.submitted_at ? (
                    <>
                      <span className="text-faint">·</span>
                      <span>{formatDateTime(submission.submitted_at)}</span>
                    </>
                  ) : null}
                </div>
              </div>

              <span className="shrink-0 text-[13px] tabular-nums text-ink-soft">
                {submission.score.toFixed(1)} / {submission.max_score.toFixed(1)}
              </span>

              <Badge tone={STATUS_TONE[submission.status]}>{STATUS_LABEL[submission.status]}</Badge>

              <ArrowRight
                size={16}
                strokeWidth={1.7}
                className="shrink-0 text-faint transition-colors group-hover:text-accent"
              />
            </Link>
          )
        })}

        {!queue.isLoading && rows.length === 0 ? (
          <p className="rounded-card border border-line bg-surface px-4 py-6 text-center text-[13px] text-muted">
            {seeAll ? 'Пока ни одной сдачи в потоке.' : 'В вашей очереди пока пусто.'}
          </p>
        ) : null}
      </div>
    </div>
  )
}
