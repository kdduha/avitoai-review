import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, Play } from 'lucide-react'
import { api } from '@/lib/api'
import { ASSIGNMENTS } from '@/mocks/catalog'
import { DEMO_RUN_ID } from '@/mocks/demoRun'
import { plural } from '@/lib/format'
import { useSession } from '@/app/session'
import { Avatar } from '@/components/ui/Avatar'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { MockNotice } from '@/components/ui/MockNotice'

export function QueuePage() {
  const { curatorId } = useSession()

  const { data: students = [] } = useQuery({ queryKey: ['students', 'go-12'], queryFn: () => api.students('go-12') })
  const { data: grades = [] } = useQuery({ queryKey: ['grades', 'go-12'], queryFn: () => api.grades('go-12') })

  const mine = new Set(students.filter((student) => student.curatorId === curatorId).map((s) => s.id))
  const queue = grades
    .filter((grade) => mine.has(grade.studentId))
    .filter((grade) => grade.status === 'draft_ready' || grade.status === 'in_review')
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
          Очередь на демо-данных: у бэкенда нет хранилища сдач, он работает от ссылки на pull request.
          Любая карточка открывает демо-прогон — настоящий разбор запускается кнопкой «Проверить работу».
        </MockNotice>
      </div>

      <div className="space-y-2">
        {queue.map((grade) => {
          const student = students.find((item) => item.id === grade.studentId)
          const assignment = ASSIGNMENTS.find((item) => item.id === grade.assignmentId)
          return (
            <Link
              key={`${grade.studentId}-${grade.assignmentId}`}
              to={`/review/${DEMO_RUN_ID}`}
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
