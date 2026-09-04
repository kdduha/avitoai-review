import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, Play } from 'lucide-react'
import { api } from '@/lib/api'
import { demoRunForCourse } from '@/lib/runs'
import { plural } from '@/lib/format'
import { useSession } from '@/app/session'
import { Avatar } from '@/components/ui/Avatar'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { MockNotice } from '@/components/ui/MockNotice'

export function QueuePage() {
  const { curatorId } = useSession()

  const { data: me } = useQuery({ queryKey: ['me'], queryFn: api.me })
  const { data: assignments = [] } = useQuery({ queryKey: ['assignments'], queryFn: () => api.assignments() })

  const streamIds = me?.streamIds ?? []
  const { data: students = [] } = useQuery({
    queryKey: ['students', streamIds],
    queryFn: async () => (await Promise.all(streamIds.map((id) => api.students(id)))).flat(),
    enabled: streamIds.length > 0,
  })
  const { data: grades = [] } = useQuery({
    queryKey: ['grades', streamIds],
    queryFn: async () => (await Promise.all(streamIds.map((id) => api.grades(id)))).flat(),
    enabled: streamIds.length > 0,
  })

  const mine = new Set(students.filter((student) => student.curatorId === curatorId).map((s) => s.id))
  const queue = grades
    .filter((grade) => mine.has(grade.studentId))
    .filter((grade) => grade.status === 'draft_ready' || grade.status === 'in_review')
    .map((grade) => ({
      grade,
      assignment: assignments.find((item) => item.id === grade.assignmentId),
    }))
    .filter((row) => Boolean(demoRunForCourse(row.assignment?.courseId)))
    .slice(0, 6)

  return (
    <div className="mx-auto max-w-[880px] px-6 py-7">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-[20px] font-semibold tracking-[-0.01em] text-ink">Мои проверки</h1>
          <p className="mt-1 text-[13.5px] text-muted">
            {queue.length} {plural(queue.length, 'работа', 'работы', 'работ')} с готовым черновиком.
          </p>
        </div>
        <Link to="/check">
          <Button variant="primary" icon={<Play size={14} strokeWidth={1.9} />}>
            Проверить работу
          </Button>
        </Link>
      </div>

      <div className="mt-5">
        <MockNotice>
          Очередь синтетическая: у бэкенда нет хранилища сдач, он работает от ссылки на pull request.
          В ней только программы, для которых есть рубрика, и карточка открывает демонстрационный
          разбор этой программы. Настоящий разбор запускается кнопкой «Проверить работу».
        </MockNotice>
      </div>

      <div className="space-y-2">
        {queue.map(({ grade, assignment }) => {
          const student = students.find((item) => item.id === grade.studentId)
          return (
            <Link
              key={`${grade.studentId}-${grade.assignmentId}`}
              to={`/review/${demoRunForCourse(assignment?.courseId)}`}
              className="group flex items-center gap-4 rounded-card border border-line bg-surface px-4 py-3.5 transition-colors hover:border-[#d6d7d1] hover:bg-raised"
            >
              <Avatar name={student?.name ?? '—'} size={32} />

              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <Badge tone="neutral">{assignment?.code}</Badge>
                  <span className="truncate text-[14px] font-medium text-ink">{assignment?.title}</span>
                </div>
                <div className="mt-1 text-[12.5px] text-muted">
                  {student?.name}
                  <span className="ml-2 font-mono text-[11.5px] text-faint">{grade.studentId}</span>
                </div>
              </div>

              <Badge tone="mark">черновик готов</Badge>

              <ArrowRight
                size={16}
                strokeWidth={1.7}
                className="shrink-0 text-faint transition-colors group-hover:text-accent"
              />
            </Link>
          )
        })}
      </div>
    </div>
  )
}
