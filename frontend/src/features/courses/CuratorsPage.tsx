import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check } from 'lucide-react'
import { api } from '@/lib/api'
import { cn } from '@/lib/cn'
import { formatDuration, percent, plural } from '@/lib/format'
import { useSession } from '@/app/session'
import { Avatar } from '@/components/ui/Avatar'
import { MockNotice } from '@/components/ui/MockNotice'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'

export function CuratorsPage() {
  const { role } = useSession()
  const client = useQueryClient()
  const [editing, setEditing] = useState<string | null>(null)
  const [selected, setSelected] = useState<string[]>([])

  const { data: curators = [] } = useQuery({ queryKey: ['curators'], queryFn: api.curators })
  const { data: courses = [] } = useQuery({ queryKey: ['mock-courses'], queryFn: api.courses })
  const { data: allStreams = [] } = useQuery({ queryKey: ['mock-streams'], queryFn: () => api.streams() })

  const save = useMutation({
    mutationFn: ({ id, streamIds }: { id: string; streamIds: string[] }) =>
      api.setCuratorStreams(id, streamIds),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['curators'] })
      setEditing(null)
    },
  })

  const current = curators.find((c) => c.id === editing)

  return (
    <div className="mx-auto max-w-[900px] px-6 py-6">
      <h1 className="text-[20px] font-semibold tracking-[-0.01em] text-ink">Ревьюеры</h1>
      <p className="mt-1 text-[13.5px] text-muted">
        Кто на каких потоках проверяет работы. Ёмкость — в минутах разбора, не в штуках.
      </p>

      <div className="mt-5">
        <MockNotice>
          Состав и нагрузка нарисованы. Настоящее назначение ревьюеров на поток — на «Потоках».
        </MockNotice>
      </div>

      <div className="mt-2 space-y-2">
        {curators.map((curator) => {
          const load = curator.committedMinutes / curator.capacityMinutes
          const streams = allStreams.filter((item) => curator.streamIds.includes(item.id))

          return (
            <div key={curator.id} className="card flex flex-wrap items-center gap-4 px-4 py-3.5">
              <Avatar name={curator.name} size={36} />

              <div className="min-w-[190px] flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[14px] font-medium text-ink">{curator.name}</span>
                  {curator.onboarding ? <Badge tone="mark">на онбординге</Badge> : null}
                </div>
                <div className="mt-0.5 text-[12.5px] text-muted">{curator.skills.join(', ')}</div>
              </div>

              <div className="min-w-[210px] flex-1">
                {streams.length ? (
                  <div className="flex flex-wrap gap-1.5">
                    {streams.map((stream) => (
                      <span key={stream.id} className="rounded-md bg-sunken px-2 py-0.5 text-[12px] text-ink-soft">
                        {courses.find((c) => c.id === stream.courseId)?.short}, {stream.short.toLowerCase()}
                      </span>
                    ))}
                  </div>
                ) : (
                  <span className="text-[12.5px] text-faint">без потоков</span>
                )}
              </div>

              <div className="w-[140px]">
                <div className="h-1.5 overflow-hidden rounded-full bg-[#e3ecf9]">
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${Math.min(1, load) * 100}%`, background: load > 0.85 ? '#d68a00' : '#2a78d6' }}
                  />
                </div>
                <div className="num mt-1 text-[11.5px] text-faint">
                  {percent(load)} из {formatDuration(curator.capacityMinutes)} в неделю
                </div>
              </div>

              {role === 'admin' ? (
                <Button
                  size="sm"
                  onClick={() => {
                    setSelected(curator.streamIds)
                    setEditing(curator.id)
                  }}
                >
                  Потоки
                </Button>
              ) : null}
            </div>
          )
        })}
      </div>

      <Modal
        open={Boolean(current)}
        title={current ? `Потоки: ${current.name}` : ''}
        description="Ревьюер увидит только работы студентов выбранных потоков."
        onClose={() => setEditing(null)}
        footer={
          <>
            <Button size="sm" onClick={() => setEditing(null)}>
              Отмена
            </Button>
            <Button
              size="sm"
              variant="primary"
              disabled={save.isPending}
              onClick={() => current && save.mutate({ id: current.id, streamIds: selected })}
            >
              {save.isPending ? 'Сохраняю' : 'Сохранить'}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {courses.map((course) => (
            <div key={course.id}>
              <div className="pb-1 text-[12px] text-faint">{course.title}</div>
              <div className="space-y-1">
                {allStreams.filter((item) => item.courseId === course.id).map((stream) => {
                  const checked = selected.includes(stream.id)
                  return (
                    <button
                      key={stream.id}
                      onClick={() =>
                        setSelected(
                          checked ? selected.filter((id) => id !== stream.id) : [...selected, stream.id],
                        )
                      }
                      className={cn(
                        'flex w-full items-center gap-2.5 rounded-lg border px-3 py-2 text-left transition-colors',
                        checked ? 'border-accent-line bg-accent-wash' : 'border-line hover:bg-[#f6f7f4]',
                      )}
                    >
                      <span
                        className={cn(
                          'grid size-[18px] shrink-0 place-items-center rounded-[5px] border',
                          checked ? 'border-accent bg-accent text-white' : 'border-[#cfcfc8] bg-raised',
                        )}
                      >
                        {checked ? <Check size={12} strokeWidth={2.5} /> : null}
                      </span>
                      <span className="text-[13.5px] text-ink">{stream.title}</span>
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
        <p className="mt-3 text-[12px] text-faint">
          {plural(selected.length, 'Выбран', 'Выбрано', 'Выбрано')} {selected.length}{' '}
          {plural(selected.length, 'поток', 'потока', 'потоков')}.
        </p>
      </Modal>
    </div>
  )
}
