import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, UserPlus } from 'lucide-react'
import { api } from '@/lib/api'
import { cn } from '@/lib/cn'
import { formatDuration, percent, plural } from '@/lib/format'
import type { Curator, Stream } from '@/lib/types'
import { useSession } from '@/app/session'
import { Avatar } from '@/components/ui/Avatar'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'

interface Props {
  stream: Stream
  courseTitle: string
}

function CuratorCard({ curator, students }: { curator: Curator; students: number }) {
  const load = curator.committedMinutes / curator.capacityMinutes

  return (
    <div className="card flex items-start gap-3 px-4 py-3.5">
      <Avatar name={curator.name} size={34} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[14px] font-medium text-ink">{curator.name}</span>
          {curator.onboarding ? <Badge tone="mark">на онбординге</Badge> : null}
        </div>
        <div className="mt-0.5 text-[12.5px] text-muted">{curator.skills.join(', ')}</div>

        <div className="mt-2.5 flex items-baseline justify-between text-[12px]">
          <span className="text-muted">
            {students} {plural(students, 'студент', 'студента', 'студентов')} на потоке
          </span>
          <span className="num text-faint">
            {formatDuration(curator.committedMinutes)} из {formatDuration(curator.capacityMinutes)}
          </span>
        </div>
        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-[#e3ecf9]">
          <div
            className="h-full rounded-full"
            style={{
              width: `${Math.min(1, load) * 100}%`,
              background: load > 0.85 ? '#d68a00' : '#2a78d6',
            }}
          />
        </div>
        <div className="num mt-1 text-[11px] text-faint">
          {percent(load)} ёмкости, медиана {curator.medianMinutesPerWork} мин на работу
        </div>
      </div>
    </div>
  )
}

export function CuratorsTab({ stream, courseTitle }: Props) {
  const { role } = useSession()
  const client = useQueryClient()
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState<string[]>([])

  const { data: curators = [] } = useQuery({ queryKey: ['curators'], queryFn: api.curators })
  const { data: students = [] } = useQuery({
    queryKey: ['students', stream.id],
    queryFn: () => api.students(stream.id),
  })

  const assign = useMutation({
    mutationFn: async (ids: string[]) => {
      for (const curator of curators) {
        const shouldHave = ids.includes(curator.id)
        const has = curator.streamIds.includes(stream.id)
        if (shouldHave === has) continue
        await api.setCuratorStreams(
          curator.id,
          shouldHave
            ? [...curator.streamIds, stream.id]
            : curator.streamIds.filter((id) => id !== stream.id),
        )
      }
    },
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['curators'] })
      setOpen(false)
    },
  })

  const onStream = curators.filter((c) => c.streamIds.includes(stream.id))

  const openDialog = () => {
    setSelected(onStream.map((c) => c.id))
    setOpen(true)
  }

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3">
        <p className="text-[13px] text-muted">
          {onStream.length
            ? `${onStream.length} ${plural(onStream.length, 'ревьюер', 'ревьюера', 'ревьюеров')} на потоке`
            : 'На поток пока никого не назначили'}
        </p>
        {role === 'admin' ? (
          <Button size="sm" onClick={openDialog} icon={<UserPlus size={13} strokeWidth={1.8} />}>
            Назначить ревьюеров
          </Button>
        ) : null}
      </div>

      {onStream.length ? (
        <div className="grid gap-3 md:grid-cols-2">
          {onStream.map((curator) => (
            <CuratorCard
              key={curator.id}
              curator={curator}
              students={students.filter((s) => s.curatorId === curator.id).length}
            />
          ))}
        </div>
      ) : (
        <div className="card grid place-items-center px-6 py-12 text-center">
          <p className="max-w-[42ch] text-[13.5px] text-muted">
            Работы этого потока некому распределить. Назначьте ревьюеров — после этого движок
            распределения сможет разложить сдачи по ним.
          </p>
          {role === 'admin' ? (
            <Button variant="primary" size="sm" className="mt-3" onClick={openDialog}>
              Назначить ревьюеров
            </Button>
          ) : (
            <p className="mt-2 text-[12.5px] text-faint">Назначение делает руководитель программы.</p>
          )}
        </div>
      )}

      <Modal
        open={open}
        title="Ревьюеры на потоке"
        description={`${courseTitle}, ${stream.title.toLowerCase()}`}
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button size="sm" onClick={() => setOpen(false)}>
              Отмена
            </Button>
            <Button size="sm" variant="primary" onClick={() => assign.mutate(selected)} disabled={assign.isPending}>
              {assign.isPending ? 'Сохраняю' : 'Сохранить'}
            </Button>
          </>
        }
      >
        <div className="space-y-1">
          {curators.map((curator) => {
            const checked = selected.includes(curator.id)
            const load = curator.committedMinutes / curator.capacityMinutes
            return (
              <button
                key={curator.id}
                onClick={() =>
                  setSelected(checked ? selected.filter((id) => id !== curator.id) : [...selected, curator.id])
                }
                className={cn(
                  'flex w-full items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors',
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
                <Avatar name={curator.name} size={28} />
                <span className="min-w-0 flex-1">
                  <span className="block text-[13.5px] font-medium text-ink">{curator.name}</span>
                  <span className="block truncate text-[12px] text-muted">{curator.skills.join(', ')}</span>
                </span>
                <span className="num shrink-0 text-right text-[11.5px] text-faint">
                  {percent(load)} ёмкости
                  {curator.onboarding ? <span className="block text-mark-ink">онбординг</span> : null}
                </span>
              </button>
            )
          })}
        </div>
      </Modal>
    </div>
  )
}
