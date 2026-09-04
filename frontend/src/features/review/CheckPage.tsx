import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CircleAlert, FlaskConical, Play } from 'lucide-react'
import { ApiError, backend } from '@/lib/backend'
import { demoRunForRubric, startRun } from '@/lib/runs'
import { cn } from '@/lib/cn'
import { Button } from '@/components/ui/Button'

function Field({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <label className="block">
      <span className="text-[12.5px] font-medium text-ink">{label}</span>
      {hint ? <span className="mt-0.5 block text-[12px] text-faint">{hint}</span> : null}
      <span className="mt-1.5 block">{children}</span>
    </label>
  )
}

const inputClass =
  'h-9 w-full rounded-lg border border-line bg-raised px-3 text-[13.5px] text-ink outline-none placeholder:text-faint focus:border-accent-line'

export function CheckPage() {
  const navigate = useNavigate()
  const client = useQueryClient()

  const [link, setLink] = useState('')
  const [rubricId, setRubricId] = useState('')
  const [deadline, setDeadline] = useState('')
  const [student, setStudent] = useState('')
  const [studentName, setStudentName] = useState('')
  const [withDetection, setWithDetection] = useState(true)

  const status = useQuery({ queryKey: ['init'], queryFn: backend.init, retry: false })
  const rubrics = useQuery({ queryKey: ['rubrics'], queryFn: backend.rubrics, retry: false })
  const cost = useQuery({ queryKey: ['cost'], queryFn: backend.cost, retry: false })

  const run = useMutation({
    mutationFn: () =>
      startRun({
        link: link.trim(),
        rubricId: rubricId || rubrics.data?.[0]?.assignment_id || '',
        deadlineAt: deadline ? new Date(deadline).toISOString() : undefined,
        studentInternalId: student.trim() || undefined,
        studentName: studentName.trim() || undefined,
        withDetection,
      }),
    onSuccess: ({ workspace }) => {
      // Прогон только что потратил токены — карточка экономики обязана это увидеть.
      client.invalidateQueries({ queryKey: ['cost'] })
      navigate(`/review/${workspace.id}`)
    },
  })

  const offline = status.isError
  const chosen = rubricId || rubrics.data?.[0]?.assignment_id || ''
  const rubric = rubrics.data?.find((item) => item.assignment_id === chosen)

  return (
    <div className="mx-auto max-w-[720px] px-6 py-7">
      <h1 className="text-[20px] font-semibold tracking-[-0.01em] text-ink">Проверить работу</h1>
      <p className="mt-1 max-w-[62ch] text-[13.5px] leading-[1.6] text-muted">
        Ссылка на pull request превращается в разбор: код собирает сдачу, гейт проверяет формальные
        требования, модель отвечает по каждому критерию с цитатой, балл считает агрегатор.
      </p>

      {offline ? (
        <div className="mt-5 flex items-start gap-2.5 rounded-card border border-[#f0d3d3] bg-critical-wash px-4 py-3">
          <CircleAlert size={15} strokeWidth={1.8} className="mt-0.5 shrink-0 text-critical" />
          <div>
            <div className="text-[13px] font-medium text-critical-ink">Бэкенд не отвечает</div>
            <p className="mt-1 max-w-[60ch] text-[12.5px] leading-[1.55] text-ink-soft">
              Поднимите его на :8000 —{' '}
              <code className="font-mono text-[12px]">cd backend &amp;&amp; uv run uvicorn avito_reviewer.app.main:app</code>
              . Посмотреть интерфейс без бэкенда можно на демо-прогоне.
            </p>
            <Button size="sm" className="mt-2.5" onClick={() => navigate(`/review/${demoRunForRubric(chosen)}`)}
              icon={<FlaskConical size={13} strokeWidth={1.8} />}>
              Открыть демо-прогон
            </Button>
          </div>
        </div>
      ) : null}

      <div className="mt-5 space-y-4 rounded-card border border-line bg-surface px-5 py-5">
        <Field label="Ссылка на работу" hint="pull request на GitHub">
          <input
            value={link}
            onChange={(event) => setLink(event.target.value)}
            placeholder="https://github.com/org/repo/pull/214"
            className={inputClass}
          />
        </Field>

        <Field label="Рубрика" hint="против чего ставится каждый вердикт">
          <select
            value={chosen}
            onChange={(event) => setRubricId(event.target.value)}
            disabled={!rubrics.data?.length}
            className={cn(inputClass, 'appearance-none disabled:text-faint')}
          >
            {rubrics.data?.length ? (
              rubrics.data.map((item) => (
                <option key={item.assignment_id} value={item.assignment_id}>
                  {item.title}
                </option>
              ))
            ) : (
              <option>Рубрики не загрузились</option>
            )}
          </select>
        </Field>

        {rubric ? (
          <p className="text-[12px] text-faint">
            {rubric.course}, {rubric.criteria} критериев, максимум {rubric.total_max}
            {rubric.pass_threshold ? `, порог зачёта ${rubric.pass_threshold}` : ''}
          </p>
        ) : null}

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Дедлайн" hint="нужен для штрафа за просрочку">
            <input
              type="datetime-local"
              value={deadline}
              onChange={(event) => setDeadline(event.target.value)}
              className={inputClass}
            />
          </Field>
          <Field label="Внутренний id студента" hint="необязательно">
            <input
              value={student}
              onChange={(event) => setStudent(event.target.value)}
              placeholder="171345"
              className={inputClass}
            />
          </Field>
        </div>

        <Field
          label="ФИО студента"
          hint="в модель не уходит: шлюз вычищает имя вместе с падежами и инициалами"
        >
          <input
            value={studentName}
            onChange={(event) => setStudentName(event.target.value)}
            placeholder="Егор Пантелеев"
            className={inputClass}
          />
        </Field>
        <p className="-mt-2 max-w-[62ch] text-[12px] leading-[1.5] text-faint">
          В сдаче имени нет намеренно, поэтому без этого поля оно остаётся на общих детекторах ПДн.
          Назвав его здесь, вы даёте шлюзу вычистить имя прицельно — в том числе там, где студент
          подписался в README или в комментарии.
        </p>

        <label className="flex cursor-pointer items-start gap-2.5">
          <input
            type="checkbox"
            checked={withDetection}
            onChange={(event) => setWithDetection(event.target.checked)}
            className="mt-0.5 size-4 accent-[#1c5cab]"
          />
          <span>
            <span className="block text-[13px] text-ink">Проверить на признаки ГенИИ</span>
            <span className="block text-[12px] text-faint">
              Отдельный прогон: сигнал рекомендательный и на балл не влияет.
            </span>
          </span>
        </label>

        {run.isError ? (
          <p className="rounded-lg border border-[#f0d3d3] bg-critical-wash px-3 py-2 text-[12.5px] text-critical-ink">
            {run.error instanceof ApiError ? run.error.message : 'Прогон не удался'}
          </p>
        ) : null}

        <div className="flex items-center gap-3 border-t border-line-soft pt-4">
          <Button
            variant="primary"
            onClick={() => run.mutate()}
            disabled={!link.trim() || !chosen || run.isPending}
            icon={<Play size={14} strokeWidth={1.9} />}
          >
            {run.isPending ? 'Разбираю работу' : 'Запустить разбор'}
          </Button>
          <Button variant="ghost" onClick={() => navigate(`/review/${demoRunForRubric(chosen)}`)}>
            Открыть демо-прогон
          </Button>
          {status.data ? (
            <span className="ml-auto text-[11.5px] text-faint">
              модель: {status.data.llm_provider}
            </span>
          ) : null}
        </div>

        {run.isPending ? (
          <p className="text-[12px] text-faint">
            Сборка сдачи из GitHub и вызов модели занимают десятки секунд — вкладку лучше не закрывать.
          </p>
        ) : null}
      </div>

      {cost.data ? (
        <section className="mt-4 rounded-card border border-line bg-surface px-5 py-4">
          <h2 className="text-[13.5px] font-semibold text-ink">Экономика прогона</h2>
          <p className="mt-0.5 text-[12px] text-faint">с момента запуска сервиса</p>

          <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2.5 sm:grid-cols-4">
            <div>
              <dt className="text-[12px] text-muted">Обращений к моделям</dt>
              <dd className="num mt-0.5 text-[17px] font-semibold text-ink">{cost.data.calls}</dd>
            </div>
            <div>
              <dt className="text-[12px] text-muted">Ушло наружу</dt>
              <dd className="num mt-0.5 text-[17px] font-semibold text-ink">{cost.data.external_calls}</dd>
            </div>
            <div>
              <dt className="text-[12px] text-muted">Обезличиваний</dt>
              <dd className="num mt-0.5 text-[17px] font-semibold text-ink">{cost.data.redactions}</dd>
            </div>
            <div>
              <dt className="text-[12px] text-muted">Потрачено</dt>
              <dd className="num mt-0.5 text-[17px] font-semibold text-ink">
                {cost.data.cost_rub.toFixed(2)} ₽
              </dd>
            </div>
          </dl>

          <p className="mt-3 max-w-[68ch] border-t border-line-soft pt-2.5 text-[12px] leading-[1.5] text-faint">
            «Ушло наружу» — вызовы во внешнюю модель; всё остальное отработало локально.
            «Обезличиваний» — сколько фрагментов ПДн шлюз вырезал перед отправкой.
            {cost.data.errors ? ` Ошибок провайдера: ${cost.data.errors}.` : ''}
          </p>
        </section>
      ) : null}
    </div>
  )
}
