import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Search, Sparkle } from 'lucide-react'
import { demoRunForCourse } from '@/lib/runs'
import type { Assignment, Curator, Grade, Student, StudentTotals } from '@/lib/types'
import { cn } from '@/lib/cn'
import { Avatar } from '@/components/ui/Avatar'

interface Props {
  students: Student[]
  assignments: Assignment[]
  grades: Grade[]
  curators: Curator[]
  totals: StudentTotals[]
}

const STATUS_HINT: Record<Grade['status'], string> = {
  approved: 'утверждено',
  draft_ready: 'черновик готов, ждёт куратора',
  in_review: 'на проверке',
  missing: 'не сдано',
  late: 'сдано с опозданием',
}

type SortKey = 'name' | 'total'

function GradeCell({
  grade,
  passThreshold,
  runId,
}: {
  grade: Grade | undefined
  passThreshold: number
  runId: string | null
}) {
  if (!grade || grade.score === null) {
    return (
      <td className="px-2 py-2 text-center">
        <span className="text-[13px] text-faint" title="не сдано">
          —
        </span>
      </td>
    )
  }

  const pending = grade.status === 'draft_ready' || grade.status === 'in_review'
  const hint = `${STATUS_HINT[grade.status]}${grade.daysLate ? `, +${grade.daysLate} дн` : ''}`

  const body = (
    <>
        <span
          className={cn(
            'num text-[13px]',
            grade.score < passThreshold ? 'text-critical-ink' : 'text-ink',
            pending ? 'font-normal text-muted' : 'font-medium',
          )}
        >
          {grade.score}
        </span>
        {pending ? <span className="size-1.5 rounded-full bg-mark-rule" title="ждёт куратора" /> : null}
        {grade.status === 'late' ? <span className="text-[10.5px] text-warn-ink">+{grade.daysLate}д</span> : null}
      {grade.aiFlag !== null ? (
        <Sparkle size={10} strokeWidth={2} className="text-warn" aria-label="сигнал ГенИИ" />
      ) : null}
    </>
  )

  return (
    <td className="px-2 py-2 text-center">
      {runId ? (
        <Link
          to={`/review/${runId}`}
          title={hint}
          className="group inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 transition-colors hover:bg-sunken"
        >
          {body}
        </Link>
      ) : (
        <span
          className="inline-flex items-center gap-1 px-1.5 py-0.5"
          title={`${hint} · разбор для этой программы ещё не собран`}
        >
          {body}
        </span>
      )}
    </td>
  )
}

export function GradesTable({ students, assignments, grades, curators, totals }: Props) {
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<SortKey>('name')

  const byStudent = useMemo(() => {
    const map = new Map<string, Grade[]>()
    for (const grade of grades) map.set(grade.studentId, [...(map.get(grade.studentId) ?? []), grade])
    return map
  }, [grades])

  const byStudentTotals = useMemo(
    () => new Map(totals.map((row) => [row.studentId, row])),
    [totals],
  )

  const rows = useMemo(() => {
    const filtered = students.filter(
      (s) =>
        !query ||
        s.name.toLowerCase().includes(query.toLowerCase()) ||
        s.alias.toLowerCase().includes(query.toLowerCase()),
    )
    return [...filtered].sort((a, b) =>
      sort === 'name'
        ? a.name.localeCompare(b.name)
        : (byStudentTotals.get(b.id)?.total ?? -1) - (byStudentTotals.get(a.id)?.total ?? -1),
    )
  }, [students, query, sort, byStudentTotals])

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3">
        <div className="relative">
          <Search size={14} strokeWidth={1.8} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-faint" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Найти студента"
            className="h-8 w-[220px] rounded-lg border border-line bg-surface pl-8 pr-3 text-[13px] outline-none placeholder:text-faint focus:border-accent-line"
          />
        </div>

        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1.5 text-[12px] text-muted">
            <span className="size-1.5 rounded-full bg-mark-rule" /> ждёт куратора
          </span>
          <span className="flex items-center gap-1.5 text-[12px] text-muted">
            <Sparkle size={11} strokeWidth={2} className="text-warn" /> сигнал ГенИИ
          </span>
        </div>
      </div>

      <div className="overflow-x-auto rounded-card border border-line bg-surface">
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="border-b border-line">
              <th className="sticky left-0 z-10 bg-surface px-4 py-2.5">
                <button
                  onClick={() => setSort('name')}
                  className={cn('text-[12.5px] transition-colors', sort === 'name' ? 'font-semibold text-ink' : 'font-medium text-muted hover:text-ink')}
                >
                  Студент
                </button>
              </th>
              {assignments.map((assignment) => (
                <th key={assignment.id} className="px-2 py-2.5 text-center align-bottom">
                  <div className="text-[12.5px] font-medium text-ink">{assignment.code}</div>
                  <div className="mx-auto mt-0.5 max-w-[13ch] truncate text-[11px] font-normal text-faint" title={assignment.title}>
                    {assignment.title}
                  </div>
                </th>
              ))}
              <th className="px-3 py-2.5 text-center">
                <button
                  onClick={() => setSort('total')}
                  title="сумма за ДЗ × 0,5 + экзамен × 0,4 + вовлечённость / 10"
                  className={cn('text-[12.5px] transition-colors', sort === 'total' ? 'font-semibold text-ink' : 'font-medium text-muted hover:text-ink')}
                >
                  Итог
                </button>
              </th>
              <th className="px-3 py-2.5 text-center text-[12.5px] font-medium text-muted">Оценка</th>
              <th className="px-4 py-2.5 text-[12.5px] font-medium text-muted">Куратор</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((student) => {
              const row = byStudentTotals.get(student.id)
              const curator = curators.find((c) => c.id === student.curatorId)
              return (
                <tr key={student.id} className="group border-b border-line-soft last:border-b-0 hover:bg-[#f8f9f6]">
                  <td className="sticky left-0 z-10 bg-surface px-4 py-2 group-hover:bg-[#f8f9f6]">
                    <Link to={`/students/${student.id}`} className="group flex items-center gap-2">
                      <Avatar name={student.name} size={24} />
                      <span className="text-[13.5px] text-ink group-hover:text-accent-ink">{student.name}</span>
                      <span className="font-mono text-[11px] text-faint">{student.alias}</span>
                    </Link>
                  </td>
                  {assignments.map((assignment) => (
                    <GradeCell
                      key={assignment.id}
                      runId={demoRunForCourse(assignment.courseId)}
                      passThreshold={assignment.passThreshold}
                      grade={(byStudent.get(student.id) ?? []).find((g) => g.assignmentId === assignment.id)}
                    />
                  ))}
                  <td className="num px-3 py-2 text-center text-[13.5px] text-ink-soft">
                    {row ? row.total : '—'}
                  </td>
                  <td className="px-3 py-2 text-center">
                    <span
                      className={cn(
                        'num text-[13.5px] font-semibold',
                        !row ? 'text-faint' : row.mark >= 8 ? 'text-good-ink' : row.mark >= 6 ? 'text-ink' : 'text-critical-ink',
                      )}
                    >
                      {row ? row.mark : '—'}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-[12.5px] text-muted">{curator?.name ?? '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
