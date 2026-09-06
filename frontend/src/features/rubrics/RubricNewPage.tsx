import { Link, Navigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { blankRubric } from '@/lib/rubric'
import { RubricEditor } from './RubricEditor'
import { useSession } from '@/app/session'
import { atLeast } from '@/lib/types'

/** Рубрика с чистого листа.
 *
 *  Разбор условия компилятором живёт на экране рубрик (`CompileRubricPanel`) —
 *  второй формы для того же здесь нет. Этот путь для случая, когда условия под
 *  рукой нет или методист собирает рубрику сам. */
export function RubricNewPage() {
  const { role } = useSession()
  if (!atLeast(role, 'methodist')) return <Navigate to="/" replace />

  return (
    <div>
      <div className="mx-auto max-w-[920px] px-6 pt-6">
        <Link
          to="/rubrics"
          className="inline-flex items-center gap-1.5 text-[12.5px] text-muted transition-colors hover:text-ink"
        >
          <ArrowLeft size={13} strokeWidth={1.8} />
          Рубрики
        </Link>
      </div>
      <RubricEditor initial={blankRubric()} mode="create" />
    </div>
  )
}
