import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarClock, CircleAlert, Clock, Loader, Send } from 'lucide-react'
import {
  ApiError,
  backend,
  type StudentAssignment,
  type StudentSubmission,
  type SubmissionStatus,
} from '@/lib/backend'
import { Button } from '@/components/ui/Button'
import { Field, inputClass } from '@/components/ui/Field'

/** Задания по курсам, в порядке первого появления: сортировку по сроку задал
 *  сервер, и перетасовывать её здесь значило бы спорить с ним. */
function byCourse(items: StudentAssignment[]): [string, StudentAssignment[]][] {
  const groups = new Map<string, StudentAssignment[]>()
  for (const item of items) {
    const key = item.course_key || '—'
    groups.set(key, [...(groups.get(key) ?? []), item])
  }
  return [...groups.entries()]
}

function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return one
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few
  return many
}

function when(value: string | null | undefined, empty = 'срока нет'): string {
  if (!value) return empty
  return new Date(value).toLocaleString('ru-RU', {
    day: 'numeric',
    month: 'long',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** Поле и кнопка. Что происходит после нажатия, показывает не форма, а список
 *  «Сданное»: работа обязана появиться там сразу, а не через десятки секунд. */
function SubmitForm({ onSend, onDone }: { onSend: (link: string) => void; onDone: () => void }) {
  const [link, setLink] = useState('')

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
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          variant="primary"
          onClick={() => onSend(link.trim())}
          disabled={!link.trim()}
          icon={<Send size={13} strokeWidth={1.8} />}
        >
          Сдать
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

function AssignmentCard({
  assignment,
  onSend,
}: {
  assignment: StudentAssignment
  onSend: (link: string) => void
}) {
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

      {open ? (
        <SubmitForm
          onSend={(link) => {
            onSend(link)
            setOpen(false)
          }}
          onDone={() => setOpen(false)}
        />
      ) : null}
    </li>
  )
}

/** Что с работой прямо сейчас. `approved` этого не различал: и «ждёт
 *  ревьюера», и «разбор сломался» выглядели одинаковым «на проверке». */
const STATUS: Record<SubmissionStatus, string> = {
  analyzing: 'Разбор идёт',
  draft_ready: 'Ждёт ревьюера',
  in_review: 'У ревьюера',
  approved: 'Оценена',
  failed: 'Разбор не удался',
}

function Elapsed({ since }: { since: number }) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])
  return <span className="num">{Math.round((now - since) / 1000)} с</span>
}

/** Отправленная работа до того, как сервер ответил. Запрос идёт десятки
 *  секунд, и всё это время список «Сданное» выглядел так, будто ничего не
 *  происходило. Карточка живёт ровно пока идёт запрос — сервер о ней ещё не
 *  знает, и обещать за него нечего. */
function SendingCard({ title, link, since }: { title: string; link: string; since: number }) {
  return (
    <li className="rounded-card border border-line bg-surface px-5 py-4">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="text-[14px] font-semibold text-ink">{title}</h3>
        <a href={link} target="_blank" rel="noreferrer" className="text-[12px] text-accent hover:underline">
          работа
        </a>
      </div>
      <p className="mt-2.5 flex items-center gap-1.5 text-[13px] text-muted">
        <Loader size={13} strokeWidth={1.7} className="animate-spin text-faint" />
        Отправляю: собираю работу с GitHub и считаю разбор · <Elapsed since={since} />
      </p>
      <p className="mt-1 text-[12px] text-faint">Вкладку лучше не закрывать.</p>
    </li>
  )
}

function FailedCard({ title, message, onRetry }: { title: string; message: string; onRetry: () => void }) {
  return (
    <li className="rounded-card border border-[#f0d3d3] bg-critical-wash px-5 py-4">
      <h3 className="text-[14px] font-semibold text-critical-ink">{title}</h3>
      <p className="mt-1.5 text-[13px] leading-[1.55] text-ink-soft">Работа не отправилась: {message}</p>
      <Button size="sm" variant="ghost" className="mt-2" onClick={onRetry}>
        Скрыть
      </Button>
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
                submission.passed === null
                  ? 'text-[13px] font-medium text-muted'
                  : submission.passed
                    ? 'text-[13px] font-medium text-success-ink'
                    : 'text-[13px] font-medium text-danger-ink'
              }
            >
              {submission.passed === null
                ? 'оценено'
                : submission.passed
                  ? 'зачёт'
                  : 'не зачтено'}
            </span>
          </div>
          {submission.pass_explanation ? (
            <p className="mt-1 max-w-[70ch] text-[12.5px] leading-[1.5] text-faint">
              {submission.pass_explanation}
              {submission.late_explanation ? ` ${submission.late_explanation}` : ''}
            </p>
          ) : null}

          {/* Отзыв словами — перед разбором по критериям: сначала человек
              читает, что о работе думают в целом, потом сверяется по пунктам.
              Нет отзыва — блока нет: пустых заголовков не рисуем. */}
          {submission.summary ? (
            <div className="mt-3 border-t border-line-soft pt-3">
              {submission.summary.strengths?.length ? (
                <>
                  <h4 className="text-[12.5px] font-semibold text-ink">Что получилось</h4>
                  <ul className="mt-1 space-y-1">
                    {submission.summary.strengths.map((item) => (
                      <li key={item} className="text-[13px] leading-[1.55] text-muted">
                        — {item}
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}
              {submission.summary.improvements?.length ? (
                <>
                  <h4 className="mt-3 text-[12.5px] font-semibold text-ink">Что доработать</h4>
                  <ul className="mt-1 space-y-1">
                    {submission.summary.improvements.map((item) => (
                      <li key={item} className="text-[13px] leading-[1.55] text-muted">
                        — {item}
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}
              {submission.summary.encouragement ? (
                <p className="mt-3 rounded-lg bg-accent-wash px-3 py-2 text-[13px] leading-[1.55] text-accent-ink">
                  {submission.summary.encouragement}
                </p>
              ) : null}
            </div>
          ) : null}

          <ul className="mt-3 space-y-2.5 border-t border-line-soft pt-3">
            <li className="text-[12.5px] font-semibold text-ink">По критериям</li>
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
          {submission.status === 'failed'
            ? 'Разбор не удался — работа осталась, скажите ревьюеру, он перезапустит.'
            : `${STATUS[submission.status]} — оценка появится, когда ревьюер её утвердит.`}
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
  const client = useQueryClient()
  const assignments = useQuery({ queryKey: ['my-assignments'], queryFn: backend.myAssignments })
  const submissions = useQuery({ queryKey: ['my-submissions'], queryFn: backend.mySubmissions })

  /* Отправка живёт на странице, а не в форме под заданием: показать её надо в
     списке «Сданное», а форма к тому моменту уже закрыта. */
  const [sending, setSending] = useState<{ title: string; link: string; since: number } | null>(null)
  const [error, setError] = useState<{ title: string; message: string } | null>(null)

  async function send(assignment: StudentAssignment, link: string): Promise<void> {
    setError(null)
    setSending({ title: assignment.title, link, since: Date.now() })
    try {
      await backend.submitWork({ assignment_id: assignment.id, link, source: 'github_pr' })
      client.invalidateQueries({ queryKey: ['my-submissions'] })
      client.invalidateQueries({ queryKey: ['my-assignments'] })
    } catch (err) {
      // Сдача не сохранилась — сервер разбирает её одним синхронным запросом,
      // и упавший запрос не оставляет строки. Молчать об этом нельзя: работа
      // просто исчезала бы.
      setError({
        title: assignment.title,
        message: err instanceof ApiError ? err.message : 'бэкенд не ответил',
      })
    } finally {
      setSending(null)
    }
  }

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

      {/* Группируем по курсу: студент учится на нескольких сразу, и плоский
          список заданий из четырёх разных курсов читается как свалка. */}
      {assignments.data?.length ? (
        byCourse(assignments.data).map(([key, group]) => (
          <section key={key}>
            <h2 className="mt-6 flex items-baseline gap-2 text-[13px] font-semibold text-ink">
              {group[0].course_title || key}
              <span className="text-[12px] font-normal text-faint">
                поток {group[0].stream_title || group[0].stream_key} · {group.length}{' '}
                {plural(group.length, 'задание', 'задания', 'заданий')}
              </span>
            </h2>
            <ul className="mt-3 space-y-3">
              {group.map((item) => (
                <AssignmentCard key={item.id} assignment={item} onSend={(link) => send(item, link)} />
              ))}
            </ul>
          </section>
        ))
      ) : !failed ? (
        <>
        <h2 className="mt-6 text-[13px] font-semibold text-ink">К сдаче</h2>
        <p className="mt-3 max-w-[64ch] text-[13px] leading-[1.6] text-muted">
          Заданий нет: вы ещё не зачислены ни на один поток, либо методист не выдал потоку ни
          одной рубрики.
        </p>
        </>
      ) : null}

      <h2 className="mt-8 text-[13px] font-semibold text-ink">Сданное</h2>
      {sending || error || submissions.data?.length ? (
        <ul className="mt-3 space-y-3">
          {sending ? <SendingCard {...sending} /> : null}
          {error ? (
            <FailedCard {...error} onRetry={() => setError(null)} />
          ) : null}
          {submissions.data?.map((item) => (
            <SubmissionCard key={item.id} submission={item} />
          ))}
        </ul>
      ) : !failed ? (
        <p className="mt-3 text-[13px] text-muted">Пока ничего не сдано.</p>
      ) : null}
    </div>
  )
}
