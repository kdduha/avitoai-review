import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CircleAlert, Info, Plus, TriangleAlert } from 'lucide-react'
import {
  ApiError,
  backend,
  type FormatCheck,
  type LatePolicy,
  type Rubric,
  type RubricDraft,
  type Scale,
} from '@/lib/backend'
import {
  blankCheck,
  blankCriterion,
  g,
  lateInWords,
  normalizeRubric,
  reachableMax,
  rubricAdvisories,
  rubricProblems,
} from '@/lib/rubric'
import { plural } from '@/lib/format'
import { cn } from '@/lib/cn'
import { useSession } from '@/app/session'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import {
  CheckboxField,
  Field,
  NumberField,
  SelectField,
  TextAreaField,
  TextField,
} from '@/components/ui/Field'
import { CriterionEditor } from './CriterionEditor'
import { GateCheckEditor } from './GateCheckEditor'

interface Props {
  initial: Rubric
  /** Пришли от компилятора: оговорки, открытые вопросы и цитаты по критериям. */
  draft?: RubricDraft | null
  groundedShare?: number | null
  mode: 'create' | 'edit'
}

const AI_POLICIES = [
  { value: 'declare_required', label: 'использование разрешено, но должно быть заявлено' },
  { value: 'not_specified', label: 'условие про ИИ ничего не говорит' },
]

const uid = (): string => Math.random().toString(36).slice(2)

function swap<T>(items: T[], from: number, to: number): T[] {
  const next = [...items]
  ;[next[from], next[to]] = [next[to], next[from]]
  return next
}

function Section({
  title,
  hint,
  action,
  children,
}: {
  title: string
  hint?: string
  action?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <section className="card mt-4 overflow-hidden">
      <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-3.5">
        <div className="min-w-0">
          <h2 className="text-[13.5px] font-semibold text-ink">{title}</h2>
          {hint ? <p className="mt-0.5 max-w-[74ch] text-[12px] leading-[1.5] text-faint">{hint}</p> : null}
        </div>
        {action ? <div className="shrink-0">{action}</div> : null}
      </div>
      {children}
    </section>
  )
}

/** Что компилятор не смог вывести из условия сам.
 *
 *  Стоит перед критериями и не сворачивается: подтвердить рубрику, не прочитав
 *  открытые вопросы, — то же самое, что подтвердить её не читая. */
function DraftNotes({ draft, groundedShare }: { draft: RubricDraft; groundedShare: number | null }) {
  const warnings = draft.warnings ?? []
  const questions = draft.open_questions ?? []
  const share = groundedShare ?? 0

  return (
    <div className="card mt-4 overflow-hidden border-[#f0e2c2]">
      <div className="flex items-start justify-between gap-4 border-b border-[#f0e2c2] bg-warn-wash px-5 py-3">
        <div>
          <h2 className="text-[13.5px] font-semibold text-warn-ink">Черновик компилятора</h2>
          <p className="mt-0.5 max-w-[74ch] text-[12px] leading-[1.5] text-warn-ink/85">
            Рубрикой это станет только после вашего подтверждения. Всё, чего в условии нет, модель
            не выдумывала, а вынесла сюда.
          </p>
        </div>
        <div className="shrink-0 text-right">
          <div className="num text-[17px] font-semibold text-warn-ink">{Math.round(share * 100)}%</div>
          <div className="text-[11px] text-warn-ink/85">критериев с дословной цитатой</div>
        </div>
      </div>

      {questions.length ? (
        <div className="border-b border-line-soft px-5 py-3.5">
          <div className="text-[12.5px] font-medium text-ink">Решает методист</div>
          <ul className="mt-1.5 space-y-1">
            {questions.map((question) => (
              <li key={question} className="flex items-start gap-2 text-[12.5px] leading-[1.5] text-ink-soft">
                <span className="mt-[7px] size-1 shrink-0 rounded-full bg-mark-rule" />
                <span className="max-w-[74ch]">{question}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {warnings.length ? (
        <div className="px-5 py-3.5">
          <div className="text-[12.5px] font-medium text-ink">Оговорки компилятора</div>
          <ul className="mt-1.5 space-y-1">
            {warnings.map((warning) => (
              <li key={warning} className="flex items-start gap-2 text-[12.5px] leading-[1.5] text-muted">
                <TriangleAlert size={12} strokeWidth={1.8} className="mt-[3px] shrink-0 text-warn" />
                <span className="max-w-[74ch]">{warning}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {!questions.length && !warnings.length ? (
        <p className="border-b border-line-soft px-5 py-3.5 text-[12.5px] leading-[1.5] text-muted">
          Компилятор не оставил ни оговорок, ни открытых вопросов — условие оказалось полным.
          Проверьте цитаты у критериев: это единственное, что подтверждает, что рубрика собрана по
          условию, а не по памяти модели.
        </p>
      ) : null}

      <p className="num px-5 py-2.5 text-[11.5px] text-faint">
        сборка черновика: {draft.tokens_in} → {draft.tokens_out} токенов, {draft.cost_rub.toFixed(2)} ₽ —
        один раз на задание, дальше по рубрике проверяется весь поток
      </p>
    </div>
  )
}

export function RubricEditor({ initial, draft = null, groundedShare = null, mode }: Props) {
  const navigate = useNavigate()
  const client = useQueryClient()
  const { name } = useSession()

  const [rubric, setRubric] = useState<Rubric>(() => normalizeRubric(initial))
  const criteria = rubric.criteria ?? []
  const gate = rubric.format_gate ?? []

  /* Ключи списков не могут быть идентификаторами: методист правит `id` прямо в
     поле, и на каждом нажатии карточка пересоздавалась бы, теряя фокус. */
  const [criterionKeys, setCriterionKeys] = useState<string[]>(() => criteria.map(uid))
  const [gateKeys, setGateKeys] = useState<string[]>(() => gate.map(uid))
  const [opened, setOpened] = useState<string | null>(null)

  const [dialog, setDialog] = useState(false)
  const [confirmedBy, setConfirmedBy] = useState(name)
  const [overwrite, setOverwrite] = useState(false)

  const list = useQuery({ queryKey: ['rubrics'], queryFn: backend.rubrics, retry: false })
  const exists = Boolean(list.data?.some((item) => item.assignment_id === rubric.assignment_id))
  const renamed = mode === 'edit' && rubric.assignment_id !== initial.assignment_id

  const problems = useMemo(() => rubricProblems(rubric), [rubric])
  const advisories = useMemo(() => rubricAdvisories(rubric), [rubric])
  const reachable = reachableMax(rubric)
  const dirty = useMemo(
    () => JSON.stringify(rubric) !== JSON.stringify(normalizeRubric(initial)),
    [rubric, initial],
  )

  /* Правки живут в памяти вкладки до подтверждения — перезагрузка их теряет. */
  useEffect(() => {
    if (!dirty) return
    const guard = (event: BeforeUnloadEvent) => event.preventDefault()
    window.addEventListener('beforeunload', guard)
    return () => window.removeEventListener('beforeunload', guard)
  }, [dirty])

  const patch = (next: Partial<Rubric>) => setRubric((current) => ({ ...current, ...next }))
  const patchScale = (next: Partial<Scale>) =>
    setRubric((current) => ({ ...current, scale: { ...current.scale, ...next } }))
  const patchLate = (next: Partial<LatePolicy>) =>
    setRubric((current) => ({
      ...current,
      late_policy: { ...(current.late_policy as LatePolicy), ...next },
    }))

  const save = useMutation({
    mutationFn: () =>
      backend.confirmRubric({
        rubric,
        confirmed_by: confirmedBy.trim(),
        overwrite: overwrite && !renamed,
      }),
    onSuccess: ({ rubric: saved }) => {
      client.invalidateQueries({ queryKey: ['rubrics'] })
      client.invalidateQueries({ queryKey: ['rubric', saved.assignment_id] })
      navigate(`/rubrics?id=${encodeURIComponent(saved.assignment_id)}`, { replace: true })
    },
  })

  const error = save.error instanceof ApiError ? save.error : null
  const ids = criteria.map((criterion) => criterion.id)

  const openDialog = () => {
    setOverwrite(exists && !renamed)
    save.reset()
    setDialog(true)
  }

  return (
    <div className="mx-auto max-w-[920px] px-6 py-6 pb-4">
      <h1 className="text-[20px] font-semibold tracking-[-0.01em] text-ink">
        {mode === 'edit' ? 'Правка рубрики' : 'Новая рубрика'}
      </h1>
      <p className="mt-1 max-w-[74ch] text-[13.5px] leading-[1.6] text-muted">
        {mode === 'edit'
          ? 'Рубрика действует до конца курса: по ней уже могли быть выставлены баллы, и правка меняет то, против чего они ставились.'
          : 'Промпт собирается из этой структуры, а не пишется руками. Пока рубрика не подтверждена, её нет в каталоге.'}
      </p>

      {draft ? <DraftNotes draft={draft} groundedShare={groundedShare} /> : null}

      <Section title="Паспорт задания">
        <div className="space-y-4 px-5 py-4">
          <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_180px]">
            <Field label="Название" hint="его увидит ревьюер в списке рубрик">
              <TextField
                value={rubric.title}
                onChange={(title) => patch({ title })}
                placeholder="Сервис на Go: HTTP-эндпоинты и graceful shutdown"
              />
            </Field>
            <Field label="Идентификатор" hint="им же называется файл рубрики">
              <TextField
                value={rubric.assignment_id}
                mono
                onChange={(assignment_id) => patch({ assignment_id })}
                placeholder="go-task1"
              />
            </Field>
          </div>

          <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_180px]">
            <Field label="Курс">
              <TextField
                value={rubric.course}
                onChange={(course) => patch({ course })}
                placeholder="Микросервисы на Go"
              />
            </Field>
            <Field label="Этап" hint="необязательно">
              <TextField
                value={rubric.stage ?? ''}
                onChange={(stage) => patch({ stage: stage.trim() ? stage : null })}
                placeholder="task1"
              />
            </Field>
          </div>

          <Field
            label="Политика по ИИ"
            hint="нарушением бывает не сам ИИ, а незаявленный — от этого зависит, как читается сигнал детектора"
          >
            <SelectField
              value={rubric.ai_policy}
              onChange={(ai_policy) => patch({ ai_policy })}
              options={
                AI_POLICIES.some((item) => item.value === rubric.ai_policy)
                  ? AI_POLICIES
                  : [...AI_POLICIES, { value: rubric.ai_policy, label: rubric.ai_policy }]
              }
            />
          </Field>

          <Field
            label="Откуда рубрика"
            hint="метку черновика сервер снимет сам и допишет, кто и когда подтвердил"
          >
            <TextAreaField
              rows={2}
              value={rubric.source_note}
              onChange={(source_note) => patch({ source_note })}
              placeholder="Собрано по условию задания от 12.02"
            />
          </Field>
        </div>
      </Section>

      <Section
        title="Шкала и просрочка"
        hint="шаг, порог и штраф применяет агрегатор — он же считает итог работы, поэтому числа здесь решают за весь поток"
      >
        <div className="space-y-4 px-5 py-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Максимум за работу">
              <NumberField
                value={rubric.scale.total_max}
                onChange={(value) => patchScale({ total_max: value ?? 0 })}
              />
            </Field>
            <Field label="Порог зачёта" hint="пусто — порога нет">
              <NumberField
                value={rubric.scale.pass_threshold ?? null}
                nullable
                placeholder="нет"
                onChange={(value) => patchScale({ pass_threshold: value })}
              />
            </Field>
            <Field label="Шаг шкалы" hint="баллы бывают дробными">
              <NumberField value={rubric.scale.step} onChange={(value) => patchScale({ step: value ?? 1 })} />
            </Field>
          </div>

          <div className="grid gap-3 border-t border-line-soft pt-4 sm:grid-cols-3">
            <Field label="Грейс-период, дней" hint="сколько дней досдача ещё принимается">
              <NumberField
                value={rubric.late_policy?.grace_days ?? 0}
                onChange={(value) => patchLate({ grace_days: Math.round(value ?? 0) })}
              />
            </Field>
            <Field label="Штраф за день">
              <NumberField
                value={rubric.late_policy?.penalty_per_grace_day ?? 0}
                onChange={(value) => patchLate({ penalty_per_grace_day: value ?? 0 })}
              />
            </Field>
            <Field label="После грейс-периода">
              <SelectField
                value={rubric.late_policy?.after_grace ?? 'zero'}
                onChange={(after_grace) => patchLate({ after_grace })}
                options={[
                  { value: 'zero' as const, label: 'работа оценивается в ноль' },
                  { value: 'continue' as const, label: 'штраф продолжает расти' },
                ]}
              />
            </Field>
          </div>

          <p className="rounded-lg bg-sunken px-3 py-2 text-[12.5px] leading-[1.5] text-ink-soft">
            Ревьюер прочтёт это так: {lateInWords(rubric.late_policy)}.
          </p>
        </div>
      </Section>

      <Section
        title={`Критерии · ${criteria.length}`}
        hint="модель отвечает по каждому отдельно и обязана приложить цитату; сумму считает агрегатор"
        action={
          <Button
            size="sm"
            icon={<Plus size={13} strokeWidth={1.9} />}
            onClick={() => {
              const key = uid()
              setRubric((current) => ({
                ...current,
                criteria: [...(current.criteria ?? []), blankCriterion(current)],
              }))
              setCriterionKeys((keys) => [...keys, key])
              setOpened(key)
            }}
          >
            Критерий
          </Button>
        }
      >
        {criteria.length ? (
          criteria.map((criterion, index) => (
            <CriterionEditor
              key={criterionKeys[index]}
              criterion={criterion}
              source={draft?.sources?.find((item) => item.criterion_id === criterion.id) ?? null}
              duplicateId={ids.indexOf(criterion.id) !== ids.lastIndexOf(criterion.id)}
              first={index === 0}
              last={index === criteria.length - 1}
              defaultOpen={criterionKeys[index] === opened}
              onChange={(next) =>
                setRubric((current) => ({
                  ...current,
                  criteria: (current.criteria ?? []).map((item, position) =>
                    position === index ? { ...item, ...next } : item,
                  ),
                }))
              }
              onMove={(delta) => {
                setRubric((current) => ({
                  ...current,
                  criteria: swap(current.criteria ?? [], index, index + delta),
                }))
                setCriterionKeys((keys) => swap(keys, index, index + delta))
              }}
              onRemove={() => {
                setRubric((current) => ({
                  ...current,
                  criteria: (current.criteria ?? []).filter((_, position) => position !== index),
                }))
                setCriterionKeys((keys) => keys.filter((_, position) => position !== index))
              }}
            />
          ))
        ) : (
          <p className="px-5 py-8 text-center text-[13px] text-muted">
            Без критериев рубрика не считается и в каталог не попадёт.
          </p>
        )}
      </Section>

      <Section
        title={`Format Gate · ${gate.length}`}
        hint="проходят до модели и не стоят ни одного токена: работа, не принимаемая по формату, не должна стоить ни рубля"
        action={
          <Button
            size="sm"
            icon={<Plus size={13} strokeWidth={1.9} />}
            onClick={() => {
              const key = uid()
              setRubric((current) => ({
                ...current,
                format_gate: [...(current.format_gate ?? []), blankCheck()],
              }))
              setGateKeys((keys) => [...keys, key])
              setOpened(key)
            }}
          >
            Проверка
          </Button>
        }
      >
        {gate.length ? (
          gate.map((check, index) => (
            <GateCheckEditor
              key={gateKeys[index]}
              check={check}
              defaultOpen={gateKeys[index] === opened}
              onChange={(next: Partial<FormatCheck>) =>
                setRubric((current) => ({
                  ...current,
                  format_gate: (current.format_gate ?? []).map((item, position) =>
                    position === index ? { ...item, ...next } : item,
                  ),
                }))
              }
              onRemove={() => {
                setRubric((current) => ({
                  ...current,
                  format_gate: (current.format_gate ?? []).filter((_, position) => position !== index),
                }))
                setGateKeys((keys) => keys.filter((_, position) => position !== index))
              }}
            />
          ))
        ) : (
          <p className="px-5 py-8 text-center text-[13px] text-muted">
            Формальных проверок нет — всё, что можно было проверить кодом, уйдёт в модель за деньги.
          </p>
        )}
      </Section>

      {/* Одно громкое место — то, что рубрика вообще считается; кнопка стоит
          рядом с числом, которое подтверждает. */}
      <div className="sticky bottom-0 z-20 -mx-6 mt-4 border-t border-line bg-raised px-6 shadow-[0_-1px_10px_rgba(27,26,24,0.05)]">
        {problems.length || advisories.length ? (
          <div className="max-h-[136px] overflow-y-auto border-b border-line-soft py-2.5">
            <ul className="space-y-1">
              {problems.map((problem) => (
                <li key={problem} className="flex items-start gap-2 text-[12.5px] leading-[1.5] text-critical-ink">
                  <CircleAlert size={13} strokeWidth={1.8} className="mt-[3px] shrink-0 text-critical" />
                  <span className="max-w-[80ch]">{problem}</span>
                </li>
              ))}
              {advisories.map((note) => (
                <li key={note} className="flex items-start gap-2 text-[12.5px] leading-[1.5] text-muted">
                  <Info size={13} strokeWidth={1.8} className="mt-[3px] shrink-0 text-faint" />
                  <span className="max-w-[80ch]">{note}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className="flex flex-wrap items-center justify-between gap-4 py-3">
          <div>
            <div className="flex items-baseline gap-1.5">
              <span className="num text-[24px] font-semibold leading-none tracking-[-0.02em] text-ink">
                {g(reachable)}
              </span>
              <span className="num text-[14px] leading-none text-faint">/ {g(rubric.scale.total_max)}</span>
            </div>
            <div className="mt-1 text-[11.5px] text-faint">
              набирается по критериям с весами · {criteria.length}{' '}
              {plural(criteria.length, 'критерий', 'критерия', 'критериев')} · {gate.length}{' '}
              {plural(gate.length, 'проверка', 'проверки', 'проверок')}
            </div>
          </div>

          <div className="flex items-center gap-3">
            {problems.length ? (
              <span className="text-[12.5px] text-critical-ink">
                {problems.length}{' '}
                {plural(problems.length, 'поломка', 'поломки', 'поломок')} — сервер такую рубрику не примет
              </span>
            ) : exists && !renamed ? (
              <Badge tone="warn">перепишет рубрику {rubric.assignment_id}</Badge>
            ) : null}
            <Button variant="primary" onClick={openDialog} disabled={problems.length > 0}>
              Подтвердить рубрику
            </Button>
          </div>
        </div>
      </div>

      <Modal
        open={dialog}
        title="Подтвердить рубрику"
        description="С этого момента по ней проверяются работы потока."
        onClose={() => setDialog(false)}
        footer={
          <>
            <Button size="sm" onClick={() => setDialog(false)}>
              Отмена
            </Button>
            <Button
              size="sm"
              variant="primary"
              disabled={save.isPending || !confirmedBy.trim() || (exists && !renamed && !overwrite)}
              onClick={() => save.mutate()}
            >
              {save.isPending ? 'Сохраняю' : 'Подтвердить'}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="Кто подтверждает" hint="имя попадёт в рубрику рядом с датой">
            <TextField value={confirmedBy} onChange={setConfirmedBy} placeholder="Ирина Ходасевич" />
          </Field>

          {renamed ? (
            <div className="rounded-lg border border-[#f0e2c2] bg-warn-wash px-3 py-2.5">
              <div className="text-[12.5px] font-medium text-warn-ink">Идентификатор изменён</div>
              <p className="mt-1 text-[12px] leading-[1.5] text-warn-ink/85">
                Рубрика ляжет в каталог как новая — <span className="font-mono">{rubric.assignment_id}</span>, а
                прежняя <span className="font-mono">{initial.assignment_id}</span> останется на месте вместе с
                работами, проверенными по ней. Удалить её отсюда нельзя.
              </p>
            </div>
          ) : exists ? (
            <div className="rounded-lg border border-[#f0d3d3] bg-critical-wash px-3 py-2.5">
              <div className="text-[12.5px] font-medium text-critical-ink">
                Рубрика {rubric.assignment_id} уже есть в каталоге
              </div>
              <p className="mt-1 text-[12px] leading-[1.5] text-critical-ink/85">
                По старой версии уже могли быть проверены работы. Их баллы останутся прежними, но
                объяснить их новой рубрикой будет нельзя — расхождение обнаружится при первом споре
                со студентом.
              </p>
              <div className="mt-2.5">
                <CheckboxField
                  checked={overwrite}
                  onChange={setOverwrite}
                  label="Переписать существующую рубрику"
                />
              </div>
            </div>
          ) : null}

          {error ? (
            <div className="rounded-lg border border-[#f0d3d3] bg-critical-wash px-3 py-2.5">
              <div className="text-[12.5px] font-medium text-critical-ink">
                {error.status === 409
                  ? 'Такая рубрика уже есть'
                  : error.status === 422
                    ? 'Сервер не принял рубрику'
                    : 'Не сохранилось'}
              </div>
              {error.problems.length > 1 ? (
                <ul className="mt-1.5 space-y-1">
                  {error.problems.map((problem) => (
                    <li key={problem} className="text-[12px] leading-[1.5] text-critical-ink/90">
                      — {problem}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-[12px] leading-[1.5] text-critical-ink/90">{error.message}</p>
              )}
            </div>
          ) : null}

          <p className={cn('text-[12px] leading-[1.5] text-faint')}>
            Проверку рубрики делает сервер: он смотрит, что она вообще считается — недостижимый порог,
            минимум выше максимума критерия, повторяющиеся идентификаторы. Список слева повторяет эти
            же правила, чтобы поломка была видна во время правки, но последнее слово за сервером.
          </p>
        </div>
      </Modal>
    </div>
  )
}
