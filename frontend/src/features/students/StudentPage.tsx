import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Sparkle } from 'lucide-react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '@/lib/api'
import { cn } from '@/lib/cn'
import { demoRunForCourse } from '@/lib/runs'
import { Avatar } from '@/components/ui/Avatar'
import { Badge } from '@/components/ui/Badge'
import { AXIS, ChartTooltip, GRID, Panel, SERIES } from '@/features/courses/chart'

const STATUS_LABEL: Record<string, string> = {
  approved: 'утверждено',
  draft_ready: 'черновик готов',
  in_review: 'на проверке',
  missing: 'не сдано',
  late: 'с опозданием',
}

export function StudentPage() {
  const { studentId = '' } = useParams()

  const { data: student } = useQuery({ queryKey: ['student', studentId], queryFn: () => api.student(studentId) })
  const { data: grades = [] } = useQuery({
    queryKey: ['student-grades', studentId],
    queryFn: () => api.gradesForStudent(studentId),
  })
  const { data: courses = [] } = useQuery({ queryKey: ['courses'], queryFn: api.courses })
  const { data: streams = [] } = useQuery({ queryKey: ['streams'], queryFn: () => api.streams() })
  const { data: curators = [] } = useQuery({ queryKey: ['curators'], queryFn: api.curators })
  const { data: assignments = [] } = useQuery({
    queryKey: ['assignments', student?.courseId],
    queryFn: () => api.assignments(student?.courseId),
    enabled: Boolean(student),
  })

  if (!student) return null

  const course = courses.find((item) => item.id === student.courseId)
  const stream = streams.find((item) => item.id === student.streamId)
  const curator = curators.find((item) => item.id === student.curatorId)

  const runId = demoRunForCourse(student.courseId)
  const scored = grades.filter((g) => g.score !== null)
  const average = scored.length
    ? Math.round((scored.reduce((sum, g) => sum + (g.score ?? 0), 0) / scored.length) * 10) / 10
    : null
  const flags = grades.filter((g) => g.aiFlag !== null)

  const maxScore = assignments[0]?.maxScore ?? 10

  const trend = grades.map((grade) => ({
    code: assignments.find((item) => item.id === grade.assignmentId)?.code ?? grade.assignmentId,
    score: grade.score,
  }))

  return (
    <div className="mx-auto max-w-[960px] px-6 py-6">
      <Link
        to={`/courses/${student.courseId}?stream=${student.streamId}`}
        className="inline-flex items-center gap-1.5 text-[12.5px] text-muted transition-colors hover:text-ink"
      >
        <ArrowLeft size={13} strokeWidth={1.8} />
        {course?.title}
      </Link>

      <header className="mt-3 flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <Avatar name={student.name} size={44} />
          <div>
            <h1 className="text-[20px] font-semibold tracking-[-0.01em] text-ink">{student.name}</h1>
            <div className="mt-0.5 flex flex-wrap items-center gap-x-3 text-[12.5px] text-muted">
              <span className="font-mono text-[12px] text-faint">{student.alias}</span>
              <span>{stream?.title}</span>
              <span>ревьюер: {curator?.name ?? 'не назначен'}</span>
            </div>
          </div>
        </div>

        <div className="text-right">
          <div className="text-[12.5px] text-muted">Средний балл</div>
          <div className="mt-0.5 text-[30px] font-semibold leading-none tracking-[-0.02em] text-ink">
            {average ?? '—'}
          </div>
        </div>
      </header>

      <div className="mt-6 grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
        <section className="card overflow-hidden">
          <h2 className="border-b border-line px-4 py-3 text-[13.5px] font-semibold text-ink">Работы</h2>
          <div>
            {grades.map((grade) => {
              const assignment = assignments.find((item) => item.id === grade.assignmentId)
              const body = (
                <>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <Badge tone="neutral">{assignment?.code}</Badge>
                      <span className="truncate text-[13.5px] text-ink">{assignment?.title}</span>
                    </div>
                    <div className="mt-1 flex items-center gap-2 text-[12px] text-faint">
                      <span>{STATUS_LABEL[grade.status]}</span>
                      {grade.daysLate ? <span className="text-warn-ink">+{grade.daysLate} дн</span> : null}
                      {grade.aiFlag !== null ? (
                        <span className="flex items-center gap-1 text-warn-ink">
                          <Sparkle size={10} strokeWidth={2} />
                          сигнал {grade.aiFlag.toFixed(2)}
                        </span>
                      ) : null}
                    </div>
                  </div>
                  <span
                    className={cn(
                      'num shrink-0 text-[15px] font-semibold',
                      grade.score === null
                        ? 'text-faint'
                        : grade.score < (assignments.find((item) => item.id === grade.assignmentId)?.passThreshold ?? 0)
                          ? 'text-critical-ink'
                          : 'text-ink',
                    )}
                  >
                    {grade.score ?? '—'}
                  </span>
                </>
              )

              return grade.submissionId && runId ? (
                <Link
                  key={grade.assignmentId}
                  to={`/review/${runId}`}
                  className="flex items-center gap-3 border-b border-line-soft px-4 py-3 last:border-b-0 hover:bg-[#f8f9f6]"
                >
                  {body}
                </Link>
              ) : (
                <div
                  key={grade.assignmentId}
                  className="flex items-center gap-3 border-b border-line-soft px-4 py-3 last:border-b-0"
                >
                  {body}
                </div>
              )
            })}
          </div>
        </section>

        <div className="space-y-4">
          <Panel title="Динамика" hint="балл по каждому заданию курса">
            <ResponsiveContainer width="100%" height={168}>
              <LineChart data={trend} margin={{ left: -18, right: 12, top: 8, bottom: 4 }}>
                <CartesianGrid {...GRID} />
                <XAxis dataKey="code" {...AXIS} />
                <YAxis domain={[0, maxScore]} {...AXIS} />
                <Tooltip content={<ChartTooltip />} cursor={{ stroke: '#dcdcd6' }} />
                <Line
                  type="linear"
                  dataKey="score"
                  name="балл"
                  stroke={SERIES.primary}
                  strokeWidth={2}
                  connectNulls
                  dot={{ r: 4, fill: SERIES.primary, stroke: '#fbfbfa', strokeWidth: 2 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </Panel>

          <Panel title="Сигналы ГенИИ по курсу" hint="решение принимает ревьюер, на балл не влияет">
            {flags.length ? (
              <ul className="space-y-2">
                {flags.map((grade) => (
                  <li key={grade.assignmentId} className="flex items-center justify-between gap-3 text-[13px]">
                    <span className="text-ink-soft">
                      {assignments.find((item) => item.id === grade.assignmentId)?.code}
                    </span>
                    <span className="num text-warn-ink">{grade.aiFlag?.toFixed(2)}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[13px] text-muted">Сигналов по работам этого студента нет.</p>
            )}
          </Panel>
        </div>
      </div>
    </div>
  )
}
