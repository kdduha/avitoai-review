import { Link, Navigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, CircleAlert } from 'lucide-react'
import { backend } from '@/lib/backend'
import { Button } from '@/components/ui/Button'
import { RubricEditor } from './RubricEditor'
import { useSession } from '@/app/session'
import { atLeast } from '@/lib/types'

export function RubricEditPage() {
  const { role } = useSession()
  const { assignmentId = '' } = useParams()

  const rubric = useQuery({
    queryKey: ['rubric', assignmentId],
    queryFn: () => backend.rubric(assignmentId),
    enabled: Boolean(assignmentId),
    retry: false,
  })

  if (!atLeast(role, 'methodist')) return <Navigate to="/" replace />

  return (
    <div>
      <div className="mx-auto max-w-[920px] px-6 pt-6">
        <Link
          to={`/rubrics?id=${encodeURIComponent(assignmentId)}`}
          className="inline-flex items-center gap-1.5 text-[12.5px] text-muted transition-colors hover:text-ink"
        >
          <ArrowLeft size={13} strokeWidth={1.8} />
          Рубрики
        </Link>
      </div>

      {rubric.isError ? (
        <div className="mx-auto max-w-[920px] px-6 py-5">
          <div className="flex items-start gap-2.5 rounded-card border border-[#f0d3d3] bg-critical-wash px-4 py-3">
            <CircleAlert size={15} strokeWidth={1.8} className="mt-0.5 shrink-0 text-critical" />
            <div>
              <div className="text-[13px] font-medium text-critical-ink">
                Рубрика {assignmentId} не загрузилась
              </div>
              <p className="mt-1 max-w-[62ch] text-[12.5px] leading-[1.55] text-ink-soft">
                Править рубрику вслепую нельзя: подтверждение отправляет её целиком, и то, чего не
                видно на экране, ушло бы на сервер как пустое.
              </p>
              <Link to="/rubrics" className="mt-2.5 inline-block">
                <Button size="sm">К списку рубрик</Button>
              </Link>
            </div>
          </div>
        </div>
      ) : null}

      {rubric.isLoading ? (
        <p className="mx-auto max-w-[920px] px-6 py-8 text-[13px] text-muted">Загружаю рубрику…</p>
      ) : null}

      {/* Ключ по идентификатору: без него переход на другую рубрику оставил бы
          в состоянии редактора критерии предыдущей. */}
      {rubric.data ? (
        <RubricEditor key={rubric.data.assignment_id} initial={rubric.data} mode="edit" />
      ) : null}
    </div>
  )
}
