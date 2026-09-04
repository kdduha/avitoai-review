import { useEffect } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { cn } from '@/lib/cn'
import { Tabs } from '@/components/ui/Tabs'
import { MockNotice } from '@/components/ui/MockNotice'
import { CourseDashboard } from './CourseDashboard'
import { CuratorsTab } from './CuratorsTab'
import { GradesTable } from './GradesTable'

const TABS = [
  { id: 'grades', label: 'Ведомость' },
  { id: 'dashboard', label: 'Дашборд' },
  { id: 'curators', label: 'Кураторы' },
]

export function CoursePage() {
  const { courseId = '' } = useParams()
  const [params, setParams] = useSearchParams()

  const { data: course } = useQuery({ queryKey: ['course', courseId], queryFn: () => api.course(courseId) })
  const { data: streams = [] } = useQuery({ queryKey: ['streams', courseId], queryFn: () => api.streams(courseId) })

  const streamId = params.get('stream') ?? streams[0]?.id ?? ''
  const tab = params.get('tab') ?? 'grades'

  useEffect(() => {
    if (!params.get('stream') && streams.length) {
      setParams({ stream: streams[0].id, tab }, { replace: true })
    }
  }, [streams, params, setParams, tab])

  const stream = streams.find((s) => s.id === streamId)

  const { data: students = [] } = useQuery({
    queryKey: ['students', streamId],
    queryFn: () => api.students(streamId),
    enabled: Boolean(streamId),
  })
  const { data: assignments = [] } = useQuery({
    queryKey: ['assignments', courseId],
    queryFn: () => api.assignments(courseId),
  })
  const { data: grades = [] } = useQuery({
    queryKey: ['grades', streamId],
    queryFn: () => api.grades(streamId),
    enabled: Boolean(streamId),
  })
  const { data: curators = [] } = useQuery({ queryKey: ['curators'], queryFn: api.curators })
  const { data: totals = [] } = useQuery({
    queryKey: ['totals', streamId],
    queryFn: () => api.totals(streamId),
    enabled: Boolean(streamId),
  })
  const { data: stats } = useQuery({
    queryKey: ['stats', streamId],
    queryFn: () => api.stats(streamId),
    enabled: Boolean(streamId),
  })

  if (!course) return null

  /* Поток берётся из адресной строки: на неизвестный id нужен внятный экран,
     а не пустая вкладка. */
  const unknownStream = Boolean(streams.length) && !stream

  return (
    <div className="px-6 py-6">
      <header>
        <h1 className="text-[20px] font-semibold tracking-[-0.01em] text-ink">{course.title}</h1>
        <p className="mt-1 text-[13.5px] text-muted">{course.subtitle}</p>

        {streams.length > 1 ? (
          <div className="mt-4 flex items-center gap-1.5">
            {streams.map((item) => (
              <button
                key={item.id}
                onClick={() => setParams({ stream: item.id, tab })}
                className={cn(
                  'rounded-lg border px-3 py-1.5 text-[13px] transition-colors',
                  item.id === streamId
                    ? 'border-accent-line bg-accent-wash font-medium text-accent-ink'
                    : 'border-line bg-surface text-muted hover:text-ink',
                )}
              >
                {item.title}
              </button>
            ))}
          </div>
        ) : null}
      </header>

      <Tabs
        className="mt-5"
        items={TABS}
        value={tab}
        onChange={(next) => setParams({ stream: streamId, tab: next })}
      />

      <div className="pt-5">
        <MockNotice>
          Курсы, потоки и ведомость пока на демо-данных: у бэкенда есть разбор работы по ссылке, но нет
          хранилища сдач и учебного каталога. Формы объектов взяты из схемы данных архитектуры.
        </MockNotice>
        {unknownStream ? (
          <div className="card grid place-items-center px-6 py-12 text-center">
            <p className="max-w-[46ch] text-[13.5px] text-muted">
              Потока <span className="font-mono text-[12.5px]">{streamId}</span> нет на этом курсе.
              Выберите поток выше.
            </p>
          </div>
        ) : (
          <>
            {tab === 'grades' ? (
              <GradesTable
                students={students}
                assignments={assignments}
                grades={grades}
                curators={curators}
                totals={totals}
              />
            ) : null}
            {tab === 'dashboard' && stats ? <CourseDashboard stats={stats} /> : null}
            {tab === 'curators' && stream ? <CuratorsTab stream={stream} courseTitle={course.title} /> : null}
          </>
        )}
      </div>
    </div>
  )
}
