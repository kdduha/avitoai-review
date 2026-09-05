import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarClock, CircleAlert, Plus } from 'lucide-react'
import { ApiError, backend, type AssignmentOut } from '@/lib/backend'
import { useSession } from '@/app/session'
import { atLeast } from '@/lib/types'
import { cn } from '@/lib/cn'
import { Button } from '@/components/ui/Button'
import { Field, inputClass } from '@/components/ui/Field'

/** Срок задания человеку, а не машине. `null` — это не «не заполнили»:
 *  у большинства курсов сроков в условиях нет вовсе, и просрочки там не
 *  бывает. Поэтому пустая дата подписана словами, а не прочерком. */
function deadlineLabel(value: string | null | undefined): string {
  if (!value) return 'срока нет'
  return new Date(value).toLocaleString('ru-RU', {
    day: 'numeric',
    month: 'long',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** `datetime-local` не понимает ISO с зоной, а `toISOString` уводит время в
 *  UTC и показывает методисту не ту дату, которую он поставил. */
function toLocalInput(value: string | null | undefined): string {
  if (!value) return ''
  const date = new Date(value)
  const shifted = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return shifted.toISOString().slice(0, 16)
}

function AssignmentCard({ assignment }: { assignment: AssignmentOut }) {
  const client = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [deadline, setDeadline] = useState(toLocalInput(assignment.deadline_at))
  const [error, setError] = useState<string | null>(null)

  const save = useMutation({
    mutationFn: () =>
      backend.patchAssignment(assignment.id, {
        // Пустое поле — это снять срок, а не «не менять». `null` в JSON от
        // «не передавали» неотличим, поэтому у сервера для этого свой флаг.
        deadline_at: deadline ? new Date(deadline).toISOString() : null,
        clear_deadline: !deadline,
      }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['assignments'] })
      setEditing(false)
      setError(null)
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : 'Не удалось сохранить'),
  })

  return (
    <li className="rounded-card border border-line bg-surface px-5 py-4">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="rounded-md bg-sunken px-1.5 py-0.5 text-[11.5px] font-medium text-muted">
          {assignment.course_key}/{assignment.stream_key}
        </span>
        <h3 className="text-[14px] font-semibold text-ink">{assignment.title}</h3>
        <span className="text-[12px] text-faint">
          {assignment.criteria} критериев, максимум {assignment.max_score}
        </span>
      </div>

      {assignment.description ? (
        <p className="mt-2 max-w-[70ch] text-[13px] leading-[1.55] text-muted">
          {assignment.description}
        </p>
      ) : null}

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <span className="flex items-center gap-1.5 text-[12.5px] text-ink-soft">
          <CalendarClock size={13} strokeWidth={1.7} className="text-faint" />
          {deadlineLabel(assignment.deadline_at)}
        </span>
        <span className="text-[12px] text-faint">
          рубрика {assignment.rubric_key} · сдач {assignment.submissions}
        </span>
        {!editing ? (
          <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setEditing(true)}>
            Изменить срок
          </Button>
        ) : null}
      </div>

      {editing ? (
        <div className="mt-3 flex flex-wrap items-end gap-3 border-t border-line-soft pt-3">
          <Field label="Срок сдачи" hint="пусто — срока нет, просрочки не бывает">
            <input
              type="datetime-local"
              value={deadline}
              onChange={(event) => setDeadline(event.target.value)}
              className={inputClass}
            />
          </Field>
          <Button size="sm" variant="primary" onClick={() => save.mutate()} disabled={save.isPending}>
            {save.isPending ? 'Сохраняю' : 'Сохранить'}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
            Отмена
          </Button>
        </div>
      ) : null}

      {assignment.submissions > 0 && editing ? (
        <p className="mt-2 max-w-[68ch] text-[12px] leading-[1.5] text-faint">
          По заданию уже {assignment.submissions} сдач. Новый срок подействует только на
          следующие разборы — уже оценённые работы хранят тот срок, против которого их
          проверяли, и задним числом не пересчитываются.
        </p>
      ) : null}

      {error ? <p className="mt-2 text-[12.5px] text-danger-ink">{error}</p> : null}
    </li>
  )
}

function NewAssignment({ onDone }: { onDone: () => void }) {
  const streams = useQuery({ queryKey: ['streams'], queryFn: () => backend.streams() })
  const rubrics = useQuery({ queryKey: ['rubrics'], queryFn: backend.rubrics })
  const [streamId, setStreamId] = useState('')
  const [rubricKey, setRubricKey] = useState('')
  const [deadline, setDeadline] = useState('')
  const [error, setError] = useState<string | null>(null)
  const client = useQueryClient()

  const stream = streams.data?.find((s) => s.id === streamId) ?? streams.data?.[0]
  const rubric = rubrics.data?.find((r) => r.assignment_id === rubricKey) ?? rubrics.data?.[0]

  const create = useMutation({
    mutationFn: () =>
      backend.createAssignment({
        stream_id: stream!.id,
        rubric_key: rubric!.assignment_id,
        title: '',
        description: '',
        opens_at: null,
        deadline_at: deadline ? new Date(deadline).toISOString() : null,
      }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['assignments'] })
      onDone()
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : 'Не удалось создать'),
  })

  if (!streams.data?.length) {
    return (
      <div className="rounded-card border border-line bg-surface px-5 py-4 text-[13px] text-muted">
        Потоков ещё нет. Задание — это рубрика, выданная потоку, поэтому сначала нужен поток.
      </div>
    )
  }

  return (
    <div className="space-y-4 rounded-card border border-line bg-surface px-5 py-5">
      <Field label="Поток" hint="кому выдаётся задание">
        <select
          value={stream?.id ?? ''}
          onChange={(event) => setStreamId(event.target.value)}
          className={cn(inputClass, 'appearance-none')}
        >
          {streams.data.map((item) => (
            <option key={item.id} value={item.id}>
              {item.course_key}/{item.key} {item.title ? `— ${item.title}` : ''}
            </option>
          ))}
        </select>
      </Field>

      <Field label="Рубрика" hint="требования: критерии, шкала, формальные проверки">
        <select
          value={rubric?.assignment_id ?? ''}
          onChange={(event) => setRubricKey(event.target.value)}
          className={cn(inputClass, 'appearance-none')}
        >
          {rubrics.data?.map((item) => (
            <option key={item.assignment_id} value={item.assignment_id}>
              {item.title}
            </option>
          ))}
        </select>
      </Field>

      <Field label="Срок сдачи" hint="пусто — срока нет; выдумывать дату за условие не нужно">
        <input
          type="datetime-local"
          value={deadline}
          onChange={(event) => setDeadline(event.target.value)}
          className={inputClass}
        />
      </Field>

      {error ? <p className="text-[12.5px] text-danger-ink">{error}</p> : null}

      <div className="flex gap-2">
        <Button
          variant="primary"
          onClick={() => create.mutate()}
          disabled={create.isPending || !stream || !rubric}
        >
          {create.isPending ? 'Создаю' : 'Выдать потоку'}
        </Button>
        <Button variant="ghost" onClick={onDone}>
          Отмена
        </Button>
      </div>
    </div>
  )
}

/** Что настраивает методист: какая рубрика выдана какому потоку и до какого
 *  числа. Ревьюер это только читает — в форме проверки задание выбирается, а
 *  срок не вводится. */
export function AssignmentsPage() {
  const { role } = useSession()
  const [creating, setCreating] = useState(false)
  const assignments = useQuery({ queryKey: ['assignments'], queryFn: () => backend.assignments() })
  const canEdit = atLeast(role, 'methodist')

  return (
    <div className="mx-auto max-w-[860px] px-6 py-7">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-[20px] font-semibold tracking-[-0.01em] text-ink">Задания</h1>
          <p className="mt-1 max-w-[64ch] text-[13.5px] leading-[1.6] text-muted">
            Задание — это рубрика, выданная потоку в срок. Требования живут в рубрике и
            действуют на всех потоках сразу; дата — здесь, потому что у каждого потока она
            своя.
          </p>
        </div>
        {canEdit && !creating ? (
          <Button variant="primary" onClick={() => setCreating(true)} icon={<Plus size={14} strokeWidth={2} />}>
            Новое задание
          </Button>
        ) : null}
      </div>

      {assignments.isError ? (
        <div className="mt-5 flex gap-2.5 rounded-card border border-line bg-surface px-5 py-4">
          <CircleAlert size={15} strokeWidth={1.8} className="mt-0.5 shrink-0 text-faint" />
          <p className="text-[13px] leading-[1.55] text-muted">
            Каталог заданий не загрузился — бэкенд не отвечает.
          </p>
        </div>
      ) : null}

      {creating ? (
        <div className="mt-5">
          <NewAssignment onDone={() => setCreating(false)} />
        </div>
      ) : null}

      {assignments.data?.length ? (
        <ul className="mt-5 space-y-3">
          {assignments.data.map((item) => (
            <AssignmentCard key={item.id} assignment={item} />
          ))}
        </ul>
      ) : !assignments.isError && !creating ? (
        <p className="mt-5 max-w-[64ch] text-[13px] leading-[1.6] text-muted">
          Заданий пока нет. Пока их нет, ревьюер называет рубрику и срок прямо в форме
          проверки — это работает, но срок там вводится заново на каждой работе.
        </p>
      ) : null}
    </div>
  )
}
