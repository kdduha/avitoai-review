import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CircleAlert, ClipboardCheck, FlaskConical, Play } from 'lucide-react'
import { ApiError, backend } from '@/lib/backend'
import { DEMO_RUN_ID, demoRunForRubric, startRun } from '@/lib/runs'
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
  const [assignmentId, setAssignmentId] = useState('')
  const [rubricId, setRubricId] = useState('')
  const [deadline, setDeadline] = useState('')
  const [student, setStudent] = useState('')
  const [studentName, setStudentName] = useState('')
  const [withDetection, setWithDetection] = useState(true)

  const status = useQuery({ queryKey: ['init'], queryFn: backend.init, retry: false })
  const rubrics = useQuery({ queryKey: ['rubrics'], queryFn: backend.rubrics, retry: false })
  const assignments = useQuery({
    queryKey: ['assignments'],
    queryFn: () => backend.assignments(),
    retry: false,
  })
  const cost = useQuery({ queryKey: ['cost'], queryFn: backend.cost, retry: false })

  const run = useMutation({
    mutationFn: () =>
      startRun({
        link: link.trim(),
        rubricId: assignment ? assignment.rubric_key : chosen,
        assignmentId: assignment?.id,
        deadlineAt: assignment ? undefined : deadline ? new Date(deadline).toISOString() : undefined,
        studentInternalId: student.trim() || undefined,
        studentName: studentName.trim() || undefined,
        withDetection,
      }),
    onSuccess: ({ workspace }) => {
      // Прогон только что потратил токены — карточка экономики обязана это увидеть.
      client.invalidateQueries({ queryKey: ['cost'] })
      // Сдача записана и назначена на того, кто её запустил: очередь обязана
      // показать её сразу, а не после ручного обновления страницы.
      client.invalidateQueries({ queryKey: ['queue'] })
      navigate(`/review/${workspace.id}`)
    },
  })

  /* Разбор идёт синхронно и молча: сборка из GitHub и вызовы модели занимают
     десятки секунд. Какой шаг идёт прямо сейчас, сервер не сообщает — врать
     про это нельзя, поэтому показываем честное: что именно происходит и
     сколько уже длится. */
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    if (!run.isPending) {
      setElapsed(0)
      return
    }
    const started = Date.now()
    const timer = setInterval(() => setElapsed(Math.round((Date.now() - started) / 1000)), 1000)
    return () => clearInterval(timer)
  }, [run.isPending])

  const offline = status.isError
  /* Задания — основной путь: методист выдал рубрику потоку и назвал срок.
     Пока каталог пуст, форма откатывается на прямой выбор рубрики: проверить
     работу надо уметь и до того, как заведён первый поток. */
  const planned = assignments.data ?? []
  const assignment = planned.find((item) => item.id === assignmentId) ?? planned[0]
  const chosen = rubricId || rubrics.data?.[0]?.assignment_id || ''
  /* Рубрику диктует задание, если оно выбрано: демо-прогон ищем по той же
     рубрике, против которой пойдёт настоящий разбор. */
  const rubricKey = assignment ? assignment.rubric_key : chosen
  /* Правило просрочки лежит в самой рубрике, в каталоге его нет — нужен
     отдельный запрос за полной рубрикой. */
  const rubricLatePolicy = useQuery({
    queryKey: ['rubric', rubricKey],
    queryFn: () => backend.rubric(rubricKey),
    enabled: Boolean(rubricKey),
    retry: false,
  })
  const demoRun = demoRunForRubric(rubricKey)
  const withDemo = (rubrics.data ?? []).filter((item) =>
    demoRunForRubric(item.assignment_id),
  ).length
  const rubric = rubrics.data?.find((item) => item.assignment_id === chosen)

  /* Что рубрика сделает с работой, сданной позже названного срока. Пока это
     видно только в итоге, ноль читается как «разбор ничего не нашёл». */
  const latePenalty = ((): string | null => {
    const at = assignment?.deadline_at ?? (deadline ? new Date(deadline).toISOString() : null)
    if (!at || new Date(at) >= new Date()) return null
    const policy = rubricLatePolicy.data?.late_policy
    if (!policy) return 'Срок в прошлом: работа будет разобрана как просроченная.'
    if (policy.grace_days === 0 && policy.after_grace === 'zero')
      return 'Срок в прошлом: по этой рубрике любая просрочка обнуляет балл — итог будет 0 при любом разборе.'
    if (policy.after_grace === 'zero')
      return `Срок в прошлом: по этой рубрике −${policy.penalty_per_grace_day ?? 0} за день, позже ${policy.grace_days} дн. — 0 баллов.`
    return `Срок в прошлом: по этой рубрике −${policy.penalty_per_grace_day ?? 0} за каждый день просрочки.`
  })()

  return (
    <div className="mx-auto max-w-[720px] px-6 py-7">
      <h1 className="text-[20px] font-semibold tracking-[-0.01em] text-ink">Проверить работу</h1>
      <p className="mt-1 max-w-[62ch] text-[13.5px] leading-[1.6] text-muted">
        Ссылка на pull request превращается в разбор: система собирает работу, проверяет обязательные
        требования, модель отвечает по каждому критерию с цитатой, а итоговый балл считается по
        фиксированным правилам, а не моделью.
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
            {/* Здесь рубрика ещё не выбрана — каталог не загрузился, — поэтому
                открывается конкретный записанный прогон, а не «разбор по вашей
                рубрике». Это не подстановка: обещание кнопки совпадает с тем,
                что она делает. */}
            <Button size="sm" className="mt-2.5" onClick={() => navigate(`/review/${DEMO_RUN_ID}`)}
              icon={<FlaskConical size={13} strokeWidth={1.8} />}>
              Открыть демо-прогон по Go
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

        {planned.length ? (
          <>
            <Field label="Задание" hint="поток, рубрика и срок — из настроек методиста">
              <select
                value={assignment?.id ?? ''}
                onChange={(event) => setAssignmentId(event.target.value)}
                className={cn(inputClass, 'appearance-none')}
              >
                {planned.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.course_key}/{item.stream_key} — {item.title}
                  </option>
                ))}
              </select>
            </Field>

            {assignment ? (
              <p className="text-[12px] text-faint">
                {assignment.criteria} критериев, максимум {assignment.max_score}
                {'. '}
                {assignment.deadline_at
                  ? `Срок: ${new Date(assignment.deadline_at).toLocaleString('ru-RU', {
                      day: 'numeric',
                      month: 'long',
                      hour: '2-digit',
                      minute: '2-digit',
                    })}`
                  : 'Срока нет — просрочки не бывает'}
              </p>
            ) : null}
          </>
        ) : (
          <>
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

            <Field label="Дедлайн" hint="нужен для штрафа за просрочку">
              <input
                type="datetime-local"
                value={deadline}
                onChange={(event) => setDeadline(event.target.value)}
                className={inputClass}
              />
            </Field>
            {/* Срок в прошлом обнуляет разбор целиком, и понять это по нулю в
                итоге невозможно: экран показывал безупречную работу как 0.
                Правило берём из самой рубрики, а не пересказываем общее. */}
            {latePenalty ? (
              <p className="-mt-2 flex items-start gap-1.5 text-[12px] leading-[1.5] text-critical-ink">
                <CircleAlert size={13} strokeWidth={1.8} className="mt-0.5 shrink-0" />
                {latePenalty}
              </p>
            ) : null}
            <p className="-mt-2 max-w-[62ch] text-[12px] leading-[1.5] text-faint">
              Заданий на потоках пока нет, поэтому рубрику и срок приходится называть здесь.
              Когда методист выдаст рубрику потоку и поставит дату, оба поля отсюда уйдут:
              срок принадлежит заданию, а не отдельной проверке.
            </p>
          </>
        )}

        <Field label="Внутренний id студента" hint="необязательно">
          <input
            value={student}
            onChange={(event) => setStudent(event.target.value)}
            placeholder="171345"
            className={inputClass}
          />
        </Field>

        {/* Поле осталось, объяснение — нет. Что имя не уходит в модель, а
            вычищается шлюзом, это свойство сервиса, а не подсказка к вводу:
            место такому тексту в документации, а не над каждым полем. */}
        <Field label="ФИО студента">
          <input
            value={studentName}
            onChange={(event) => setStudentName(event.target.value)}
            placeholder="Егор Пантелеев"
            className={inputClass}
          />
        </Field>

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
          {demoRun ? (
            <Button variant="ghost" onClick={() => navigate(`/review/${demoRun}`)}>
              Открыть демо-прогон
            </Button>
          ) : (
            <span className="max-w-[46ch] text-[12px] leading-[1.5] text-faint">
              Записанного разбора по этой рубрике нет: он есть у {withDemo} из{' '}
              {rubrics.data?.length ?? 0}. Показывать вместо него чужой — значит показать
              правдоподобное и неверное.
            </span>
          )}
          <Link to="/queue" className="ml-auto">
            <Button size="sm" variant="ghost" icon={<ClipboardCheck size={13} strokeWidth={1.8} />}>
              Мои проверки
            </Button>
          </Link>
          {status.data ? (
            <span className="text-[11.5px] text-faint">
              {/* Показываем модель, а не провайдер. «модель: fake» читалось как
                  имя модели, хотя fake — это способ подключения: заглушка без
                  ключа. На заглушке имени модели нет, и врать его незачем. */}
              {status.data.llm_provider === 'fake'
                ? 'без ключа: модель не вызывается'
                : `модель: ${status.data.llm_model || status.data.llm_provider}`}
            </span>
          ) : null}
        </div>

        {run.isPending ? (
          <div className="rounded-lg border border-line bg-sunken px-4 py-3">
            <div className="flex items-baseline justify-between gap-3">
              <span className="text-[13px] font-medium text-ink">Идёт разбор</span>
              <span className="num text-[12px] text-faint">{elapsed} с</span>
            </div>
            <p className="mt-1.5 max-w-[58ch] text-[12px] leading-[1.55] text-muted">
              Работа собирается из GitHub, проходит формальные проверки, затем модель отвечает
              по каждому критерию отдельно. Десятки секунд — вкладку лучше не закрывать.
            </p>
            <p className="mt-1.5 text-[12px] text-muted">
              Когда закончится, сдача откроется на разборе и появится в «Моих проверках».
            </p>
          </div>
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
