import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarClock, CircleAlert, Clock, Send } from 'lucide-react'
import {
  ApiError,
  backend,
  type StudentAssignment,
  type StudentSubmission,
} from '@/lib/backend'
import { Button } from '@/components/ui/Button'
import { Field, inputClass } from '@/components/ui/Field'

function when(value: string | null | undefined, empty = 'срока нет'): string {
  if (!value) return empty
  return new Date(value).toLocaleString('ru-RU', {
    day: 'numeric',
    month: 'long',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function SubmitForm({ assignment, onDone }: { assignment: StudentAssignment; onDone: () => void }) {
  const [link, setLink] = useState('')
  const [error, setError] = useState<string | null>(null)
  const client = useQueryClient()

  const submit = useMutation({
    mutationFn: () => backend.submitWork({ assignment_id: assignment.id, link: link.trim(), source: 'github_pr' }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['my-submissions'] })
      client.invalidateQueries({ queryKey: ['my-assignments'] })
      onDone()
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : 'Не удалось сдать работу'),
  })

  return (
    <div className="mt-3 space-y-3 border-t border-line-soft pt-3">
      <Field label="Ссылка на работу" hint="pull request на GitHub">
        <input
          value={link}
          onChange={(event) => setLink(event.target.value)}
          placeholder="https://github.com/org/repo/pull/214"
          className={inputClass}
        />
      </Field>
      {error ? <p className="text-[12.5px] text-danger-ink">{error}</p> : null}
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          variant="primary"
          onClick={() => submit.mutate()}
          disabled={!link.trim() || submit.isPending}
          icon={<Send size={13} strokeWidth={1.8} />}
        >
          {submit.isPending ? 'Отправляю' : 'Сдать'}
        </Button>
        <Button size="sm" variant="ghost" onClick={onDone}>
          Отмена
        </Button>
        <span className="text-[12px] text-faint">
          Разбор занимает десятки секунд — вкладку лучше не закрывать.
        </span>
      </div>
    </div>
  )
}

function AssignmentCard({ assignment }: { assignment: StudentAssignment }) {
  const [open, setOpen] = useState(false)

  return (
    <li className="rounded-card border border-line bg-surface px-5 py-4">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="rounded-md bg-sunken px-1.5 py-0.5 text-[11.5px] font-medium text-muted">
          {assignment.course_key}/{assignment.stream_key}
        </span>
        <h3 className="text-[14px] font-semibold text-ink">{assignment.title}</h3>
        <span className="text-[12px] text-faint">максимум {assignment.max_score}</span>
      </div>

      {assignment.description ? (
        <p className="mt-2 max-w-[70ch] text-[13px] leading-[1.55] text-muted">
          {assignment.description}
        </p>
      ) : null}

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5">
        <span className="flex items-center gap-1.5 text-[12.5px] text-ink-soft">
          <CalendarClock size={13} strokeWidth={1.7} className="text-faint" />
          {when(assignment.deadline_at)}
        </span>
        {assignment.best_score !== null ? (
          <span className="text-[12.5px] text-ink-soft">
            зачтено: <span className="num font-semibold">{assignment.best_score}</span> из{' '}
            {assignment.max_score}
          </span>
        ) : assignment.submissions ? (
          <span className="text-[12.5px] text-muted">
            сдано {assignment.submissions}, ждёт проверки
          </span>
        ) : null}

        {!open ? (
          <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setOpen(true)}>
            {assignment.submissions ? 'Сдать ещё раз' : 'Сдать работу'}
          </Button>
        ) : null}
      </div>

      {open ? <SubmitForm assignment={assignment} onDone={() => setOpen(false)} /> : null}
    </li>
  )
}

function SubmissionCard({ submission }: { submission: StudentSubmission }) {
  return (
    <li className="rounded-card border border-line bg-surface px-5 py-4">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="rounded-md bg-sunken px-1.5 py-0.5 text-[11.5px] font-medium text-muted">
          {submission.course_key}/{submission.stream_key}
        </span>
        <h3 className="text-[14px] font-semibold text-ink">{submission.assignment_title}</h3>
        <a
          href={submission.origin_url}
          target="_blank"
          rel="noreferrer"
          className="text-[12px] text-accent hover:underline"
        >
          работа
        </a>
      </div>

      {submission.approved ? (
        <>
          <div className="mt-3 flex flex-wrap items-baseline gap-x-3">
            <span className="num text-[22px] font-semibold text-ink">{submission.score}</span>
            <span className="text-[13px] text-muted">из {submission.max_score}</span>
            <span
              className={
                submission.passed
                  ? 'text-[13px] font-medium text-success-ink'
                  : 'text-[13px] font-medium text-danger-ink'
              }
            >
              {submission.passed ? 'зачёт' : 'не зачтено'}
            </span>
          </div>
          {submission.pass_explanation ? (
            <p className="mt-1 max-w-[70ch] text-[12.5px] leading-[1.5] text-faint">
              {submission.pass_explanation}
              {submission.late_explanation ? ` ${submission.late_explanation}` : ''}
            </p>
          ) : null}

          <ul className="mt-3 space-y-2.5 border-t border-line-soft pt-3">
            {(submission.verdicts ?? []).map((verdict) => (
              <li key={verdict.criterion_id}>
                <div className="flex items-baseline gap-2">
                  <span className="num text-[13px] font-semibold text-ink">
                    {verdict.score}/{verdict.max_score}
                  </span>
                  <span className="text-[13px] font-medium text-ink">{verdict.title}</span>
                </div>
                <p className="mt-0.5 max-w-[74ch] text-[13px] leading-[1.55] text-muted">
                  {verdict.feedback}
                </p>
                {verdict.improvement_hint ? (
                  <p className="mt-0.5 max-w-[74ch] text-[12.5px] leading-[1.5] text-faint">
                    Что докрутить: {verdict.improvement_hint}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </>
      ) : (
        /* До утверждения балла нет вовсе — и это не «загружается».
           Разбор уже посчитан моделью, но оценку ставит человек, и пока он её
           не поставил, показывать число значило бы объявить чужое решение. */
        <p className="mt-3 flex items-center gap-1.5 text-[13px] text-muted">
          <Clock size={13} strokeWidth={1.7} className="text-faint" />
          На проверке у ревьюера — оценка появится, когда он её утвердит.
        </p>
      )}

      <p className="mt-2.5 text-[12px] text-faint">
        сдано {when(submission.submitted_at, '—')}
        {submission.deadline_at ? ` · срок ${when(submission.deadline_at)}` : ''}
      </p>
    </li>
  )
}

/** Кабинет студента: что сдавать, что уже сдано и что за это получено. */
export function StudentHomePage() {
  const assignments = useQuery({ queryKey: ['my-assignments'], queryFn: backend.myAssignments })
  const submissions = useQuery({ queryKey: ['my-submissions'], queryFn: backend.mySubmissions })

  const failed = assignments.isError || submissions.isError

  return (
    <div className="mx-auto max-w-[860px] px-6 py-7">
      <h1 className="text-[20px] font-semibold tracking-[-0.01em] text-ink">Мои работы</h1>
      <p className="mt-1 max-w-[64ch] text-[13.5px] leading-[1.6] text-muted">
        Работа сдаётся ссылкой на pull request. Разбор готовится сразу, но оценка появляется
        после того, как её утвердит ревьюер.
      </p>

      {failed ? (
        <div className="mt-5 flex gap-2.5 rounded-card border border-line bg-surface px-5 py-4">
          <CircleAlert size={15} strokeWidth={1.8} className="mt-0.5 shrink-0 text-faint" />
          <p className="text-[13px] leading-[1.55] text-muted">Бэкенд не отвечает.</p>
        </div>
      ) : null}

      <h2 className="mt-6 text-[13px] font-semibold text-ink">К сдаче</h2>
      {assignments.data?.length ? (
        <ul className="mt-3 space-y-3">
          {assignments.data.map((item) => (
            <AssignmentCard key={item.id} assignment={item} />
          ))}
        </ul>
      ) : !failed ? (
        <p className="mt-3 max-w-[64ch] text-[13px] leading-[1.6] text-muted">
          Заданий нет: вы ещё не зачислены ни на один поток, либо методист не выдал потоку ни
          одной рубрики.
        </p>
      ) : null}

      <h2 className="mt-8 text-[13px] font-semibold text-ink">Сданное</h2>
      {submissions.data?.length ? (
        <ul className="mt-3 space-y-3">
          {submissions.data.map((item) => (
            <SubmissionCard key={item.id} submission={item} />
          ))}
        </ul>
      ) : !failed ? (
        <p className="mt-3 text-[13px] text-muted">Пока ничего не сдано.</p>
      ) : null}
    </div>
  )
}
