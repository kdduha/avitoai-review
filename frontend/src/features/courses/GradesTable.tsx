import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Search, Sparkle } from 'lucide-react'
import { DEMO_RUN_ID } from '@/lib/runs'
import type { Assignment, Curator, Grade, Student } from '@/lib/types'
import { cn } from '@/lib/cn'
import { Avatar } from '@/components/ui/Avatar'

interface Props {
  students: Student[]
  assignments: Assignment[]
  grades: Grade[]
  curators: Curator[]
}

const STATUS_HINT: Record<Grade['status'], string> = {
  approved: 'утверждено',
  draft_ready: 'черновик готов, ждёт куратора',
  in_review: 'на проверке',
  missing: 'не сдано',
  late: 'сдано с опозданием',
}

type SortKey = 'name' | 'total'

function GradeCell({ grade, passThreshold }: { grade: Grade | undefined; passThreshold: number }) {
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

  return (
    <td className="px-2 py-2 text-center">
      <Link
        to={`/review/${DEMO_RUN_ID}`}
        title={`${STATUS_HINT[grade.status]}${grade.daysLate ? `, +${grade.daysLate} дн` : ''}`}
        className="group inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 transition-colors hover:bg-sunken"
      >
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
      </Link>
    </td>
  )
}

export function GradesTable({ students, assignments, grades, curators }: Props) {
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<SortKey>('name')

  const byStudent = useMemo(() => {
    const map = new Map<string, Grade[]>()
    for (const grade of grades) map.set(grade.studentId, [...(map.get(grade.studentId) ?? []), grade])
    return map
  }, [grades])

  const totals = useMemo(() => {
    const map = new Map<string, number | null>()
    for (const student of students) {
      const scored = (byStudent.get(student.id) ?? []).filter((g) => g.score !== null)
      map.set(
        student.id,
        scored.length
          ? Math.round((scored.reduce((sum, g) => sum + (g.score ?? 0), 0) / scored.length) * 10) / 10
          : null,
      )
    }
    return map
  }, [students, byStudent])

  const averageThreshold = assignments.length
    ? assignments.reduce((sum, item) => sum + item.passThreshold, 0) / assignments.length
    : 0

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
        : (totals.get(b.id) ?? -1) - (totals.get(a.id) ?? -1),
    )
  }, [students, query, sort, totals])

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
                  className={cn('text-[12.5px] transition-colors', sort === 'total' ? 'font-semibold text-ink' : 'font-medium text-muted hover:text-ink')}
                >
                  Средний
                </button>
              </th>
              <th className="px-4 py-2.5 text-[12.5px] font-medium text-muted">Куратор</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((student) => {
              const total = totals.get(student.id) ?? null
              const curator = curators.find((c) => c.id === student.curatorId)
              return (
                <tr key={student.id} className="border-b border-line-soft last:border-b-0 hover:bg-[#f8f9f6]">
                  <td className="sticky left-0 z-10 bg-inherit px-4 py-2">
                    <Link to={`/students/${student.id}`} className="group flex items-center gap-2">
                      <Avatar name={student.name} size={24} />
                      <span className="text-[13.5px] text-ink group-hover:text-accent-ink">{student.name}</span>
                      <span className="font-mono text-[11px] text-faint">{student.alias}</span>
                    </Link>
                  </td>
                  {assignments.map((assignment) => (
                    <GradeCell
                      key={assignment.id}
                      passThreshold={assignment.passThreshold}
                      grade={(byStudent.get(student.id) ?? []).find((g) => g.assignmentId === assignment.id)}
                    />
                  ))}
                  <td className="px-3 py-2 text-center">
                    <span className={cn('num text-[13.5px] font-semibold', total !== null && total < averageThreshold ? 'text-critical-ink' : 'text-ink')}>
                      {total ?? '—'}
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
