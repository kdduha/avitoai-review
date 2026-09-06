import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { backend, type AssignmentOut, type CourseOut, type StreamOut } from '@/lib/backend'
import { Button } from '@/components/ui/Button'
import { Field, TextField, inputClass } from '@/components/ui/Field'
import { ConfirmDelete, Empty, ErrorLine, Section, errorText, plural } from './parts'

/** `datetime-local` не понимает ISO с зоной, а `toISOString` уводит время в UTC
 *  и показывает не ту дату, которую поставили. */
function toLocalInput(value: string | null | undefined): string {
  if (!value) return ''
  const date = new Date(value)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
}

const nameInput =
  'h-8 rounded-lg border border-transparent bg-transparent px-2 text-[13.5px] text-ink outline-none hover:border-line focus:border-accent-line'
const dateInput =
  'h-8 rounded-lg border border-line bg-raised px-2 text-[12.5px] text-ink outline-none focus:border-accent-line'

function Members({ streamId, kind }: { streamId: string; kind: 'student' | 'reviewer' }) {
  const client = useQueryClient()
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const isStudents = kind === 'student'

  const members = useQuery<{ username: string; display_name: string }[]>({
    queryKey: [isStudents ? 'stream-students' : 'stream-reviewers', streamId],
    queryFn: async () =>
      isStudents ? await backend.streamStudents(streamId) : await backend.streamReviewers(streamId),
  })
  const accounts = useQuery({ queryKey: ['users'], queryFn: backend.users, enabled: adding })

  const refresh = () => {
    client.invalidateQueries({ queryKey: [isStudents ? 'stream-students' : 'stream-reviewers', streamId] })
    client.invalidateQueries({ queryKey: ['streams'] })
  }
  const add = useMutation({
    mutationFn: async (username: string) => {
      if (isStudents) await backend.enrollStudents(streamId, [username])
      else await backend.assignReviewers(streamId, [username])
    },
    onSuccess: () => {
      setError(null)
      setAdding(false)
      refresh()
    },
    onError: (err) => setError(errorText(err, 'Не удалось добавить')),
  })
  const remove = useMutation({
    mutationFn: async (username: string) => {
      if (isStudents) await backend.unenrollStudent(streamId, username)
      else await backend.unassignReviewer(streamId, username)
    },
    onSuccess: () => {
      setError(null)
      refresh()
    },
    onError: (err) => setError(errorText(err, 'Не удалось убрать')),
  })

  const present = new Set((members.data ?? []).map((row) => row.username))
  const candidates = (accounts.data ?? []).filter((account) =>
    isStudents
      ? account.role === 'student' && !present.has(account.username)
      : account.role !== 'student' && !present.has(account.username),
  )

  return (
    <Section
      title={isStudents ? 'Студенты' : 'Ревьюеры'}
      action={
        !adding ? (
          <Button size="sm" variant="ghost" onClick={() => setAdding(true)}>
            {isStudents ? 'Зачислить' : 'Назначить'}
          </Button>
        ) : null
      }
    >
      {members.data?.length ? (
        <ul className="mt-2 space-y-1">
          {members.data.map((row) => (
            <li key={row.username} className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="text-[13px] text-ink">{row.display_name || row.username}</span>
              <span className="font-mono text-[12px] text-faint">{row.username}</span>
              <span className="ml-auto">
                <ConfirmDelete
                  label={isStudents ? 'Отчислить' : 'Снять'}
                  what={row.username}
                  onConfirm={() => remove.mutate(row.username)}
                />
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <Empty>{isStudents ? 'Никого не зачислено.' : 'Никого не назначено.'}</Empty>
      )}

      {adding ? (
        <div className="mt-2 flex flex-wrap gap-2">
          {candidates.length ? (
            candidates.map((account) => (
              <Button
                key={account.username}
                size="sm"
                variant="ghost"
                onClick={() => add.mutate(account.username)}
              >
                + {account.display_name || account.username}
              </Button>
            ))
          ) : (
            <span className="text-[12.5px] text-muted">
              {isStudents ? 'Свободных студентов нет — заведите аккаунт.' : 'Свободных ревьюеров нет.'}
            </span>
          )}
          <Button size="sm" variant="ghost" onClick={() => setAdding(false)}>
            Отмена
          </Button>
        </div>
      ) : null}

      <ErrorLine>{error}</ErrorLine>
    </Section>
  )
}

function AssignmentRow({ assignment }: { assignment: AssignmentOut }) {
  const client = useQueryClient()
  const [title, setTitle] = useState(assignment.title)
  const [deadline, setDeadline] = useState(toLocalInput(assignment.deadline_at))
  const [error, setError] = useState<string | null>(null)

  const refresh = () => client.invalidateQueries({ queryKey: ['assignments'] })
  const patch = useMutation({
    mutationFn: (body: Parameters<typeof backend.patchAssignment>[1]) =>
      backend.patchAssignment(assignment.id, body),
    onSuccess: () => {
      setError(null)
      refresh()
    },
    onError: (err) => setError(errorText(err, 'Не удалось сохранить')),
  })
  const remove = useMutation({
    mutationFn: () => backend.deleteAssignment(assignment.id),
    onSuccess: refresh,
    onError: (err) => setError(errorText(err, 'Не удалось удалить')),
  })

  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1">
      <input
        value={title}
        placeholder={assignment.rubric_key}
        aria-label={`Задание ${assignment.rubric_key}`}
        onChange={(event) => setTitle(event.target.value)}
        onBlur={() => {
          if (title !== assignment.title) patch.mutate({ title, clear_deadline: false })
        }}
        className={`${nameInput} w-[26ch]`}
      />
      <input
        type="datetime-local"
        value={deadline}
        aria-label={`Срок задания ${assignment.rubric_key}`}
        onChange={(event) => {
          setDeadline(event.target.value)
          patch.mutate({
            deadline_at: event.target.value ? new Date(event.target.value).toISOString() : null,
            clear_deadline: !event.target.value,
          })
        }}
        className={`${dateInput} w-[21ch]`}
      />
      <span className="text-[12px] text-faint">
        {plural(assignment.submissions, 'сдача', 'сдачи', 'сдач')}
        {assignment.deadline_at ? '' : ' · срока нет'}
      </span>
      <span className="ml-auto">
        <ConfirmDelete what={assignment.title || assignment.rubric_key} onConfirm={() => remove.mutate()} />
      </span>
      <ErrorLine>{error}</ErrorLine>
    </li>
  )
}

function Assignments({ streamId }: { streamId: string }) {
  const client = useQueryClient()
  const [adding, setAdding] = useState(false)
  const [rubricKey, setRubricKey] = useState('')
  const [deadline, setDeadline] = useState('')
  const [error, setError] = useState<string | null>(null)

  const assignments = useQuery({
    queryKey: ['assignments', streamId],
    queryFn: () => backend.assignments(streamId),
  })
  const rubrics = useQuery({ queryKey: ['rubrics'], queryFn: backend.rubrics, enabled: adding })
  const rubric = rubrics.data?.find((item) => item.assignment_id === rubricKey) ?? rubrics.data?.[0]

  const create = useMutation({
    mutationFn: () =>
      backend.createAssignment({
        stream_id: streamId,
        rubric_key: rubric!.assignment_id,
        title: '',
        description: '',
        opens_at: null,
        deadline_at: deadline ? new Date(deadline).toISOString() : null,
      }),
    onSuccess: () => {
      setError(null)
      setAdding(false)
      setDeadline('')
      client.invalidateQueries({ queryKey: ['assignments'] })
      client.invalidateQueries({ queryKey: ['streams'] })
    },
    onError: (err) => setError(errorText(err, 'Не удалось выдать')),
  })

  return (
    <Section
      title="Задания"
      action={
        !adding ? (
          <Button size="sm" variant="ghost" onClick={() => setAdding(true)}>
            Выдать рубрику
          </Button>
        ) : null
      }
    >
      {assignments.data?.length ? (
        <ul className="mt-2 space-y-1.5">
          {assignments.data.map((item) => (
            <AssignmentRow key={item.id} assignment={item} />
          ))}
        </ul>
      ) : (
        <Empty>Заданий нет — выдайте потоку рубрику.</Empty>
      )}

      {adding ? (
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <Field label="Рубрика" className="w-[30ch]">
            <select
              value={rubric?.assignment_id ?? ''}
              onChange={(event) => setRubricKey(event.target.value)}
              className={`${inputClass} h-8 appearance-none`}
            >
              {rubrics.data?.map((item) => (
                <option key={item.assignment_id} value={item.assignment_id}>
                  {item.title}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Срок" hint="пусто — срока нет" className="w-[21ch]">
            <input
              type="datetime-local"
              value={deadline}
              onChange={(event) => setDeadline(event.target.value)}
              className={`${inputClass} h-8`}
            />
          </Field>
          <Button size="sm" variant="primary" disabled={!rubric || create.isPending} onClick={() => create.mutate()}>
            {create.isPending ? 'Выдаю' : 'Выдать'}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setAdding(false)}>
            Отмена
          </Button>
        </div>
      ) : null}

      <ErrorLine>{error}</ErrorLine>
    </Section>
  )
}

function StreamRow({ stream }: { stream: StreamOut }) {
  const client = useQueryClient()
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState(stream.title)
  const [error, setError] = useState<string | null>(null)

  const refresh = () => client.invalidateQueries({ queryKey: ['streams'] })
  const patch = useMutation({
    mutationFn: (body: Parameters<typeof backend.patchStream>[1]) =>
      backend.patchStream(stream.id, body),
    onSuccess: () => {
      setError(null)
      refresh()
    },
    onError: (err) => setError(errorText(err, 'Не удалось сохранить')),
  })
  const remove = useMutation({
    mutationFn: () => backend.deleteStream(stream.id),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['streams'] })
      client.invalidateQueries({ queryKey: ['courses'] })
    },
    onError: (err) => setError(errorText(err, 'Не удалось удалить')),
  })

  return (
    <li className="rounded-card border border-line bg-raised px-4 py-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <button
          onClick={() => setOpen(!open)}
          className="rounded-md bg-sunken px-1.5 py-0.5 font-mono text-[11.5px] font-medium text-muted"
          aria-label={`Поток ${stream.key}`}
        >
          {stream.key}
        </button>
        <input
          value={title}
          placeholder="без названия"
          aria-label={`Поток ${stream.key}`}
          onChange={(event) => setTitle(event.target.value)}
          onBlur={() => {
            if (title !== stream.title) patch.mutate({ title })
          }}
          className={`${nameInput} w-[26ch]`}
        />
        <span className="text-[12px] text-faint">
          {plural(stream.assignments, 'задание', 'задания', 'заданий')} ·{' '}
          {plural(stream.students, 'студент', 'студента', 'студентов')}
        </span>
        <span className="ml-auto flex items-center gap-2">
          <Button size="sm" variant="ghost" onClick={() => setOpen(!open)}>
            {open ? 'Свернуть' : 'Состав'}
          </Button>
          <ConfirmDelete what={stream.key} onConfirm={() => remove.mutate()} pending={remove.isPending} />
        </span>
      </div>

      <ErrorLine>{error}</ErrorLine>

      {open ? (
        <>
          <Assignments streamId={stream.id} />
          <Members streamId={stream.id} kind="student" />
          <Members streamId={stream.id} kind="reviewer" />
        </>
      ) : null}
    </li>
  )
}

function NewStream({ course, onDone }: { course: CourseOut; onDone: () => void }) {
  const client = useQueryClient()
  const [key, setKey] = useState('')
  const [title, setTitle] = useState('')
  const [error, setError] = useState<string | null>(null)

  const create = useMutation({
    mutationFn: () => backend.createStream({ course_id: course.id, key, title }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['streams'] })
      client.invalidateQueries({ queryKey: ['courses'] })
      onDone()
    },
    onError: (err) => setError(errorText(err, 'Не удалось создать')),
  })

  return (
    <div className="mt-2 flex flex-wrap items-end gap-3 rounded-card border border-line bg-surface px-4 py-3">
      <Field label="Ключ потока" className="w-[14ch]">
        <TextField value={key} onChange={setKey} mono placeholder="a" className="h-8" />
      </Field>
      <Field label="Название потока" className="w-[26ch]">
        <TextField value={title} onChange={setTitle} placeholder="Осень 2026" className="h-8" />
      </Field>
      <Button size="sm" variant="primary" disabled={!key || create.isPending} onClick={() => create.mutate()}>
        {create.isPending ? 'Создаю' : 'Создать'}
      </Button>
      <Button size="sm" variant="ghost" onClick={onDone}>
        Отмена
      </Button>
      <ErrorLine>{error}</ErrorLine>
    </div>
  )
}

function CourseCard({ course, streams }: { course: CourseOut; streams: StreamOut[] }) {
  const client = useQueryClient()
  const [title, setTitle] = useState(course.title)
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const patch = useMutation({
    mutationFn: () => backend.patchCourse(course.id, { title }),
    onSuccess: () => {
      setError(null)
      client.invalidateQueries({ queryKey: ['courses'] })
    },
    onError: (err) => setError(errorText(err, 'Не удалось сохранить')),
  })
  const remove = useMutation({
    mutationFn: () => backend.deleteCourse(course.id),
    onSuccess: () => client.invalidateQueries({ queryKey: ['courses'] }),
    onError: (err) => setError(errorText(err, 'Не удалось удалить')),
  })

  return (
    <li className="rounded-card border border-line bg-surface px-5 py-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="rounded-md bg-sunken px-1.5 py-0.5 font-mono text-[11.5px] font-medium text-muted">
          {course.key}
        </span>
        <input
          value={title}
          aria-label={`Курс ${course.key}`}
          onChange={(event) => setTitle(event.target.value)}
          onBlur={() => {
            if (title !== course.title) patch.mutate()
          }}
          className={`${nameInput} w-[32ch] text-[14px] font-semibold`}
        />
        <span className="ml-auto flex items-center gap-2">
          <Button size="sm" variant="ghost" onClick={() => setAdding(true)}>
            Новый поток
          </Button>
          <ConfirmDelete what={course.key} onConfirm={() => remove.mutate()} pending={remove.isPending} />
        </span>
      </div>

      <ErrorLine>{error}</ErrorLine>
      {adding ? <NewStream course={course} onDone={() => setAdding(false)} /> : null}

      {streams.length ? (
        <ul className="mt-3 space-y-2">
          {streams.map((stream) => (
            <StreamRow key={stream.id} stream={stream} />
          ))}
        </ul>
      ) : (
        <Empty>Потоков нет — заведите первый.</Empty>
      )}
    </li>
  )
}

function NewCourse({ onDone }: { onDone: () => void }) {
  const client = useQueryClient()
  const [key, setKey] = useState('')
  const [title, setTitle] = useState('')
  const [error, setError] = useState<string | null>(null)

  const create = useMutation({
    mutationFn: () => backend.createCourse({ key, title }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['courses'] })
      onDone()
    },
    onError: (err) => setError(errorText(err, 'Не удалось создать')),
  })

  return (
    <div className="mt-4 flex flex-wrap items-end gap-3 rounded-card border border-line bg-surface px-5 py-4">
      <Field label="Ключ курса" className="w-[16ch]">
        <TextField value={key} onChange={setKey} mono placeholder="go" className="h-8" />
      </Field>
      <Field label="Название курса" className="w-[30ch]">
        <TextField value={title} onChange={setTitle} placeholder="Разработка на Go" className="h-8" />
      </Field>
      <Button size="sm" variant="primary" disabled={!key || !title || create.isPending} onClick={() => create.mutate()}>
        {create.isPending ? 'Создаю' : 'Создать'}
      </Button>
      <Button size="sm" variant="ghost" onClick={onDone}>
        Отмена
      </Button>
      <ErrorLine>{error}</ErrorLine>
    </div>
  )
}

export function CatalogPanel() {
  const [creating, setCreating] = useState(false)
  const courses = useQuery({ queryKey: ['courses'], queryFn: backend.courses })
  const streams = useQuery({ queryKey: ['streams'], queryFn: () => backend.streams() })

  return (
    <div>
      <div className="flex items-center justify-between gap-3">
        <p className="text-[13px] text-muted">Курс, его потоки, задания и состав.</p>
        {!creating ? (
          <Button size="sm" variant="primary" icon={<Plus size={14} strokeWidth={2} />} onClick={() => setCreating(true)}>
            Новый курс
          </Button>
        ) : null}
      </div>

      {creating ? <NewCourse onDone={() => setCreating(false)} /> : null}

      {courses.isError ? <Empty>Каталог не загрузился — бэкенд не отвечает.</Empty> : null}

      {courses.data?.length ? (
        <ul className="mt-4 space-y-3">
          {courses.data.map((course) => (
            <CourseCard
              key={course.id}
              course={course}
              streams={(streams.data ?? []).filter((stream) => stream.course_id === course.id)}
            />
          ))}
        </ul>
      ) : !courses.isError && !courses.isLoading ? (
        <Empty>Курсов нет — заведите первый.</Empty>
      ) : null}
    </div>
  )
}
