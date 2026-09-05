import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CircleAlert, Shuffle, UserMinus, UserPlus } from 'lucide-react'
import {
  ApiError,
  backend,
  type AssignmentStats,
  type StreamOut,
  type StreamStats,
} from '@/lib/backend'
import { useSession } from '@/app/session'
import { atLeast } from '@/lib/types'
import { cn } from '@/lib/cn'
import { Button } from '@/components/ui/Button'

/** Число, которого нет, — это не ноль.

 *  Утверждённых работ нет — среднего балла нет. Ноль на его месте читался бы
 *  как «все написали на ноль», и хуже этого рядом с настоящими числами ничего
 *  не придумать. Поэтому прочерк, а не `0`. */
function num(value: number | null | undefined, suffix = ''): string {
  return value === null || value === undefined ? '—' : `${value}${suffix}`
}

function percent(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : `${Math.round(value * 100)}%`
}

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div>
      <div className="text-[12px] text-muted">{label}</div>
      <div className="num mt-0.5 text-[19px] font-semibold text-ink">{value}</div>
      {hint ? <div className="text-[11.5px] text-faint">{hint}</div> : null}
    </div>
  )
}

/** Гистограмма долями максимума, а не баллами: у заданий шкалы 6, 10 и 20, и
 *  в баллах один поток был бы несравним сам с собой. */
function Histogram({ stats }: { stats: AssignmentStats }) {
  const buckets = stats.histogram ?? []
  const total = buckets.reduce((sum, b) => sum + b.count, 0)
  if (!total) return null

  return (
    <div className="mt-2 flex items-end gap-1" aria-label="распределение баллов">
      {buckets.map((bucket) => {
        const share = bucket.count / total
        return (
          <div key={bucket.lo} className="flex-1">
            <div
              className="rounded-t-[3px] bg-accent-wash"
              style={{ height: `${Math.max(3, share * 46)}px` }}
              title={`${Math.round(bucket.lo * 100)}–${Math.round(bucket.hi * 100)}% максимума: ${bucket.count}`}
            />
            <div className="mt-1 text-center text-[10.5px] text-faint">
              {Math.round(bucket.lo * 100)}–{Math.round(bucket.hi * 100)}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function Reviewers({ streamId }: { streamId: string }) {
  const { role } = useSession()
  const canEdit = role === 'admin'
  const client = useQueryClient()
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const reviewers = useQuery({
    queryKey: ['stream-reviewers', streamId],
    queryFn: () => backend.streamReviewers(streamId),
  })
  const accounts = useQuery({ queryKey: ['users'], queryFn: backend.users, enabled: canEdit && adding })

  const refresh = () => {
    client.invalidateQueries({ queryKey: ['stream-reviewers', streamId] })
    client.invalidateQueries({ queryKey: ['stream-stats', streamId] })
  }

  const add = useMutation({
    mutationFn: (username: string) => backend.assignReviewers(streamId, [username]),
    onSuccess: () => {
      refresh()
      setAdding(false)
      setError(null)
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : 'Не удалось назначить'),
  })
  const remove = useMutation({
    mutationFn: (username: string) => backend.unassignReviewer(streamId, username),
    onSuccess: refresh,
    onError: (err) => setError(err instanceof ApiError ? err.message : 'Не удалось снять'),
  })

  const assigned = new Set((reviewers.data ?? []).map((r) => r.username))
  const candidates = (accounts.data ?? []).filter(
    (a) => a.role !== 'student' && !assigned.has(a.username),
  )

  return (
    <div className="mt-4 border-t border-line-soft pt-3">
      <div className="flex items-center gap-2">
        <h4 className="text-[12.5px] font-semibold text-ink">Ревьюеры потока</h4>
        {canEdit && !adding ? (
          <Button
            size="sm"
            variant="ghost"
            className="ml-auto"
            onClick={() => setAdding(true)}
            icon={<UserPlus size={13} strokeWidth={1.8} />}
          >
            Назначить
          </Button>
        ) : null}
      </div>

      {reviewers.data?.length ? (
        <ul className="mt-2 space-y-1.5">
          {reviewers.data.map((reviewer) => (
            <li key={reviewer.username} className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="text-[13px] text-ink">{reviewer.display_name}</span>
              <span className="text-[12px] text-faint">{reviewer.username}</span>
              <span className="text-[12px] text-faint">
                {reviewer.capacity_minutes} мин/нед
                {/* Карточки каталога и аккаунты связаны только именем. Не
                    нашлось — ёмкость взята по умолчанию, и это сказано, а не
                    подставлено молча. */}
                {reviewer.roster_id ? '' : ' (по умолчанию — карточки в каталоге нет)'}
              </span>
              {canEdit ? (
                <Button
                  size="sm"
                  variant="ghost"
                  className="ml-auto"
                  onClick={() => remove.mutate(reviewer.username)}
                  icon={<UserMinus size={13} strokeWidth={1.8} />}
                >
                  Снять
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-[12.5px] text-muted">
          Никто не назначен — распределять работы этого потока не на кого.
        </p>
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
            <span className="text-[12.5px] text-muted">Свободных аккаунтов нет.</span>
          )}
          <Button size="sm" variant="ghost" onClick={() => setAdding(false)}>
            Отмена
          </Button>
        </div>
      ) : null}

      {error ? <p className="mt-2 text-[12.5px] text-danger-ink">{error}</p> : null}
    </div>
  )
}

function StreamCard({ stream }: { stream: StreamOut }) {
  const { role } = useSession()
  const client = useQueryClient()
  const [open, setOpen] = useState(false)
  const [note, setNote] = useState<string | null>(null)

  const stats = useQuery({
    queryKey: ['stream-stats', stream.id],
    queryFn: () => backend.streamStats(stream.id),
    enabled: open,
  })

  const spread = useMutation({
    mutationFn: () => backend.distributeStream(stream.id),
    onSuccess: (result) => {
      client.invalidateQueries({ queryKey: ['stream-stats', stream.id] })
      setNote(
        result.assigned === 0 && result.unassigned === 0
          ? 'Нераспределённых работ не было.'
          : `Роздано: ${result.assigned}. Осталось без ревьюера: ${result.unassigned}.` +
              (result.reasons?.length ? ` ${result.reasons.join('; ')}` : ''),
      )
    },
    onError: (err) =>
      setNote(err instanceof ApiError ? err.message : 'Не удалось разложить работы'),
  })

  const data: StreamStats | undefined = stats.data

  return (
    <li className="rounded-card border border-line bg-surface px-5 py-4">
      <button onClick={() => setOpen(!open)} className="flex w-full items-baseline gap-3 text-left">
        <span className="rounded-md bg-sunken px-1.5 py-0.5 text-[11.5px] font-medium text-muted">
          {stream.course_key}/{stream.key}
        </span>
        <span className="text-[14px] font-semibold text-ink">{stream.title || stream.key}</span>
        <span className="text-[12px] text-faint">
          {stream.assignments} заданий · {stream.students} студентов
        </span>
        <span className="ml-auto text-[12px] text-faint">{open ? 'свернуть' : 'развернуть'}</span>
      </button>

      {open ? (
        stats.isLoading ? (
          <p className="mt-3 text-[12.5px] text-faint">Считаю…</p>
        ) : data ? (
          <>
            <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
              <Tile label="Сдач" value={String(data.submissions)} />
              <Tile
                label="Ждут проверки"
                value={String(data.awaiting)}
                hint={data.unassigned ? `${data.unassigned} без ревьюера` : undefined}
              />
              <Tile label="Просрочено" value={String(data.overdue)} hint="срок вышел, оценки нет" />
              <Tile
                label="Средний балл"
                value={num(data.average_score)}
                hint={data.approved ? `по ${data.approved} утверждённым` : 'утверждённых нет'}
              />
            </dl>

            {role === 'admin' ? (
              <div className="mt-4 flex flex-wrap items-center gap-3">
                <Button
                  size="sm"
                  variant="primary"
                  onClick={() => spread.mutate()}
                  disabled={spread.isPending}
                  icon={<Shuffle size={13} strokeWidth={1.8} />}
                >
                  {spread.isPending ? 'Раскладываю' : 'Разложить работы'}
                </Button>
                <span className="max-w-[60ch] text-[12px] leading-[1.5] text-faint">
                  Раздаются только работы без ревьюера. Уже назначенные не перекладываются:
                  разбор мог начаться.
                </span>
              </div>
            ) : null}
            {note ? <p className="mt-2 text-[12.5px] text-ink-soft">{note}</p> : null}

            <div className="mt-4 border-t border-line-soft pt-3">
              <h4 className="text-[12.5px] font-semibold text-ink">По заданиям</h4>
              {data.by_assignment?.length ? (
                <ul className="mt-2 space-y-3">
                  {data.by_assignment.map((item) => (
                    <li key={item.id} className="flex flex-wrap items-start gap-x-6 gap-y-1">
                      <div className="min-w-[26ch] flex-1">
                        <div className="text-[13px] text-ink">{item.title}</div>
                        <div className="text-[12px] text-faint">
                          сдач {item.submissions} · утверждено {item.approved}
                          {item.late ? ` · с просрочкой ${item.late}` : ''}
                          {item.needs_attention
                            ? ` · требуют внимания ${item.needs_attention}`
                            : ''}
                        </div>
                      </div>
                      <div className="text-[12.5px] text-ink-soft">
                        средний {num(item.average_score)} из {item.max_score} · зачёт{' '}
                        {percent(item.pass_rate)}
                      </div>
                      <div className="w-[160px]">
                        <Histogram stats={item} />
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-[12.5px] text-muted">Заданий на потоке нет.</p>
              )}
            </div>

            {data.by_reviewer?.length ? (
              <div className="mt-4 border-t border-line-soft pt-3">
                <h4 className="text-[12.5px] font-semibold text-ink">Нагрузка</h4>
                <ul className="mt-2 space-y-1">
                  {data.by_reviewer.map((row) => (
                    <li key={row.username} className="flex items-baseline gap-3">
                      <span className="text-[13px] text-ink">{row.display_name}</span>
                      <span className="text-[12px] text-faint">
                        всего {row.assigned} · утверждено {row.approved} · в работе {row.awaiting}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            <Reviewers streamId={stream.id} />
          </>
        ) : (
          <p className="mt-3 text-[12.5px] text-muted">Статистика не загрузилась.</p>
        )
      ) : null}
    </li>
  )
}

/** Потоки с настоящими числами: сдачи, очередь, просрочка, баллы.
 *
 *  Ревьюер это читает — прятать от человека результат его же работы незачем;
 *  назначает ревьюеров и раскладывает работы только руководитель. */
export function StreamsPage() {
  const { role } = useSession()
  const streams = useQuery({ queryKey: ['streams'], queryFn: () => backend.streams() })

  if (!atLeast(role, 'reviewer')) return null

  return (
    <div className="mx-auto max-w-[900px] px-6 py-7">
      <h1 className="text-[20px] font-semibold tracking-[-0.01em] text-ink">Потоки</h1>
      <p className="mt-1 max-w-[64ch] text-[13.5px] leading-[1.6] text-muted">
        Числа считаются по сданным работам. Балл появляется у работы только после того, как
        ревьюер её утвердил, поэтому средние здесь — по утверждённым, а не по черновикам.
      </p>

      {streams.isError ? (
        <div className="mt-5 flex gap-2.5 rounded-card border border-line bg-surface px-5 py-4">
          <CircleAlert size={15} strokeWidth={1.8} className="mt-0.5 shrink-0 text-faint" />
          <p className="text-[13px] text-muted">Бэкенд не отвечает.</p>
        </div>
      ) : null}

      {streams.data?.length ? (
        <ul className={cn('mt-5 space-y-3')}>
          {streams.data.map((stream) => (
            <StreamCard key={stream.id} stream={stream} />
          ))}
        </ul>
      ) : !streams.isError ? (
        <p className="mt-5 max-w-[64ch] text-[13px] leading-[1.6] text-muted">
          Потоков нет. Поток заводит методист — он же выдаёт потоку рубрики и ставит сроки.
        </p>
      ) : null}
    </div>
  )
}
