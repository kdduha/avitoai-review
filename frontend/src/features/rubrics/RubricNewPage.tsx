import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowLeft, CircleAlert, FileText, Wand2 } from 'lucide-react'
import { ApiError, backend, type Rubric, type RubricDraft } from '@/lib/backend'
import { blankRubric, normalizeRubric } from '@/lib/rubric'
import { Button } from '@/components/ui/Button'
import { Field, TextAreaField, TextField } from '@/components/ui/Field'
import { RubricEditor } from './RubricEditor'

interface Started {
  rubric: Rubric
  draft: RubricDraft | null
  groundedShare: number | null
}

export function RubricNewPage() {
  const [started, setStarted] = useState<Started | null>(null)

  const [assignmentId, setAssignmentId] = useState('')
  const [course, setCourse] = useState('')
  const [condition, setCondition] = useState('')
  const [hint, setHint] = useState('')

  const status = useQuery({ queryKey: ['init'], queryFn: backend.init, retry: false })

  const compile = useMutation({
    mutationFn: () =>
      backend.compileRubric({
        assignment_id: assignmentId.trim(),
        condition_text: condition,
        course: course.trim(),
        hint: hint.trim(),
      }),
    onSuccess: ({ draft, grounded_share }) =>
      setStarted({
        rubric: normalizeRubric(draft.rubric),
        draft,
        groundedShare: grounded_share,
      }),
  })

  const blank = () =>
    setStarted({
      rubric: {
        ...blankRubric(),
        assignment_id: assignmentId.trim(),
        course: course.trim(),
      },
      draft: null,
      groundedShare: null,
    })

  if (started) {
    return (
      <div>
        <div className="mx-auto max-w-[920px] px-6 pt-6">
          <button
            onClick={() => setStarted(null)}
            className="inline-flex items-center gap-1.5 text-[12.5px] text-muted transition-colors hover:text-ink"
          >
            <ArrowLeft size={13} strokeWidth={1.8} />
            К условию задания
          </button>
        </div>
        <RubricEditor
          initial={started.rubric}
          draft={started.draft}
          groundedShare={started.groundedShare}
          mode="create"
        />
      </div>
    )
  }

  const error = compile.error instanceof ApiError ? compile.error : null

  return (
    <div className="mx-auto max-w-[820px] px-6 py-6">
      <Link
        to="/rubrics"
        className="inline-flex items-center gap-1.5 text-[12.5px] text-muted transition-colors hover:text-ink"
      >
        <ArrowLeft size={13} strokeWidth={1.8} />
        Рубрики
      </Link>

      <h1 className="mt-3 text-[20px] font-semibold tracking-[-0.01em] text-ink">Новая рубрика</h1>
      <p className="mt-1 max-w-[72ch] text-[13.5px] leading-[1.6] text-muted">
        Условие задания разбирается в черновик рубрики: критерии с цитатами из условия, формальные
        требования и шкала. Черновик ничего не сохраняет — рубрикой он становится после того, как вы
        его прочитаете и подтвердите.
      </p>

      {status.isError ? (
        <div className="mt-5 flex items-start gap-2.5 rounded-card border border-[#f0d3d3] bg-critical-wash px-4 py-3">
          <CircleAlert size={15} strokeWidth={1.8} className="mt-0.5 shrink-0 text-critical" />
          <div>
            <div className="text-[13px] font-medium text-critical-ink">Бэкенд не отвечает</div>
            <p className="mt-1 max-w-[60ch] text-[12.5px] leading-[1.55] text-ink-soft">
              Компилятор и подтверждение рубрики живут на сервере — без него можно только посмотреть
              форму. Поднимите его на :8000.
            </p>
          </div>
        </div>
      ) : null}

      <div className="mt-5 space-y-4 rounded-card border border-line bg-surface px-5 py-5">
        <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_200px]">
          <Field label="Курс" hint="как он называется у методиста">
            <TextField value={course} onChange={setCourse} placeholder="Микросервисы на Go" />
          </Field>
          <Field label="Идентификатор задания" hint="им же будет назван файл">
            <TextField value={assignmentId} mono onChange={setAssignmentId} placeholder="go-task1" />
          </Field>
        </div>

        <Field
          label="Условие задания"
          hint="целиком, как его видит студент — вместе с требованиями к формату, шкалой и сроками"
        >
          <TextAreaField
            rows={12}
            value={condition}
            onChange={setCondition}
            placeholder="Разработайте сервис на Go…"
          />
        </Field>

        <Field
          label="Пожелание методиста"
          hint="необязательно: на чём сделать акцент, какая шкала, что учесть"
        >
          <TextAreaField
            rows={2}
            value={hint}
            onChange={setHint}
            placeholder="Шкала 10 баллов, отдельный критерий за тесты"
          />
        </Field>

        {error ? (
          <div className="rounded-lg border border-[#f0d3d3] bg-critical-wash px-3 py-2.5">
            <div className="text-[12.5px] font-medium text-critical-ink">Черновик не собрался</div>
            <p className="mt-1 text-[12px] leading-[1.5] text-critical-ink/90">{error.message}</p>
            <p className="mt-1.5 text-[12px] leading-[1.5] text-ink-soft">
              Рубрику можно собрать и руками — форма та же, просто без предзаполнения.
            </p>
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-3 border-t border-line-soft pt-4">
          <Button
            variant="primary"
            disabled={!assignmentId.trim() || !condition.trim() || compile.isPending}
            onClick={() => compile.mutate()}
            icon={<Wand2 size={14} strokeWidth={1.8} />}
          >
            {compile.isPending ? 'Разбираю условие' : 'Собрать черновик'}
          </Button>
          <Button variant="ghost" onClick={blank} icon={<FileText size={14} strokeWidth={1.7} />}>
            Начать с чистого листа
          </Button>
          {status.data ? (
            <span className="ml-auto text-[11.5px] text-faint">модель: {status.data.llm_provider}</span>
          ) : null}
        </div>

        <p className="max-w-[72ch] text-[12px] leading-[1.5] text-faint">
          Компилятор — единственное место конвейера, где ошибка модели тиражируется на весь поток:
          по рубрике проверяется каждая работа до конца курса. Поэтому он ничего не сохраняет сам, а
          каждый критерий несёт цитату из условия, сверенную с текстом программно.
          {compile.isPending ? ' Разбор условия занимает десятки секунд.' : ''}
        </p>
      </div>
    </div>
  )
}
