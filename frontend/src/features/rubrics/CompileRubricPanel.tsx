import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { CircleAlert, HelpCircle, Sparkles } from 'lucide-react'
import { ApiError, backend, type CompileRubricResponse } from '@/lib/backend'
import { cn } from '@/lib/cn'
import { plural } from '@/lib/format'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'

const inputClass =
  'h-9 w-full rounded-lg border border-line bg-raised px-3 text-[13.5px] text-ink outline-none placeholder:text-faint focus:border-accent-line'

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

const STATUS_TONE = { quoted: 'good', paraphrased: 'warn', missing: 'critical' } as const
const STATUS_LABEL = {
  quoted: 'дословная цитата',
  paraphrased: 'пересказ, не цитата',
  missing: 'источник не найден',
} as const

/** Условие задания → черновик рубрики → подтверждение методистом.
 *
 *  Черновик — предложение, а не рубрика: он не сохраняется в каталог, пока
 *  его не подтвердят. Единственная опасность шага — придуманный критерий,
 *  поэтому у каждого критерия здесь своя пометка "откуда он взялся" рядом с
 *  ним самим, а не общим числом сверху: `warnings` и `open_questions`
 *  показаны там же, где на них будут смотреть при подтверждении, а не в
 *  тексте, который проще пролистать не читая.
 */
export function CompileRubricPanel({ onConfirmed }: { onConfirmed: (assignmentId: string) => void }) {
  const client = useQueryClient()

  const [assignmentId, setAssignmentId] = useState('')
  const [course, setCourse] = useState('')
  const [hint, setHint] = useState('')
  const [conditionText, setConditionText] = useState('')
  const [confirmedBy, setConfirmedBy] = useState('')
  const [draft, setDraft] = useState<CompileRubricResponse | null>(null)

  const compile = useMutation({
    mutationFn: () =>
      backend.compileRubric({
        assignment_id: assignmentId.trim(),
        condition_text: conditionText,
        course: course.trim(),
        hint: hint.trim(),
      }),
    onSuccess: (response) => setDraft(response),
  })

  const confirm = useMutation({
    mutationFn: () => {
      if (!draft) throw new Error('нет черновика')
      return backend.confirmRubric({
        rubric: draft.draft.rubric,
        confirmed_by: confirmedBy.trim(),
        overwrite: false,
      })
    },
    onSuccess: (response) => {
      client.invalidateQueries({ queryKey: ['rubrics'] })
      onConfirmed(response.rubric.assignment_id)
    },
  })

  const sourceFor = (criterionId: string) => draft?.draft.sources?.find((s) => s.criterion_id === criterionId)

  return (
    <div className="space-y-4">
      <div className="rounded-card border border-line bg-surface px-5 py-5">
        <Field label="Идентификатор задания" hint="латиница, цифры, точка, дефис — станет именем файла">
          <input
            value={assignmentId}
            onChange={(event) => setAssignmentId(event.target.value)}
            placeholder="sysdesign-lab2"
            className={cn(inputClass, 'font-mono')}
          />
        </Field>

        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <Field label="Курс" hint="необязательно">
            <input value={course} onChange={(event) => setCourse(event.target.value)} className={inputClass} />
          </Field>
          <Field label="Пожелание методиста" hint="шкала, акценты, что учесть — необязательно">
            <input value={hint} onChange={(event) => setHint(event.target.value)} className={inputClass} />
          </Field>
        </div>

        <Field label="Условие задания" hint="текст целиком — модель цитирует его дословно, ничего не выдумывая">
          <textarea
            value={conditionText}
            onChange={(event) => setConditionText(event.target.value)}
            rows={10}
            placeholder="Вставьте условие целиком — критерии, шкалу, штрафы, всё как есть."
            className={cn(inputClass, 'h-auto resize-y py-2 leading-[1.5]')}
          />
        </Field>

        {compile.isError ? (
          <p className="mt-3 rounded-lg border border-[#f0d3d3] bg-critical-wash px-3 py-2 text-[12.5px] text-critical-ink">
            {compile.error instanceof ApiError ? compile.error.message : 'Компилятор не ответил'}
          </p>
        ) : null}

        <div className="mt-4 flex items-center gap-3 border-t border-line-soft pt-4">
          <Button
            variant="primary"
            onClick={() => compile.mutate()}
            disabled={conditionText.trim().length < 40 || !assignmentId.trim() || compile.isPending}
            icon={<Sparkles size={14} strokeWidth={1.9} />}
          >
            {compile.isPending ? 'Разбираю условие' : 'Собрать рубрику'}
          </Button>
          {conditionText.trim().length > 0 && conditionText.trim().length < 40 ? (
            <span className="text-[12px] text-faint">условие короче 40 символов — не похоже на условие</span>
          ) : null}
        </div>
      </div>

      {draft ? (
        <div className="rounded-card border border-line bg-surface">
          <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
            <div>
              <h2 className="text-[15px] font-semibold text-ink">{draft.draft.rubric.title || assignmentId}</h2>
              <p className="mt-0.5 text-[12.5px] text-muted">
                {draft.draft.rubric.criteria?.length ?? 0}{' '}
                {plural(draft.draft.rubric.criteria?.length ?? 0, 'критерий', 'критерия', 'критериев')}, максимум{' '}
                {draft.draft.rubric.scale?.total_max}
                {draft.draft.rubric.scale?.pass_threshold ? `, порог зачёта ${draft.draft.rubric.scale.pass_threshold}` : ''}
              </p>
            </div>
            <Badge tone={draft.grounded_share >= 1 ? 'good' : draft.grounded_share >= 0.6 ? 'warn' : 'critical'}>
              цитатами подтверждено {Math.round(draft.grounded_share * 100)}%
            </Badge>
          </div>

          {draft.draft.warnings?.length || draft.draft.open_questions?.length ? (
            <div className="border-b border-line-soft bg-warn-wash/40 px-5 py-4">
              {draft.draft.warnings?.length ? (
                <div className="flex items-start gap-2.5">
                  <CircleAlert size={15} strokeWidth={1.8} className="mt-0.5 shrink-0 text-warn-ink" />
                  <div>
                    <div className="text-[13px] font-medium text-warn-ink">
                      {plural(draft.draft.warnings.length, 'предупреждение', 'предупреждения', 'предупреждений')}
                    </div>
                    <ul className="mt-1 space-y-1">
                      {draft.draft.warnings.map((warning, index) => (
                        <li key={index} className="max-w-[68ch] text-[12.5px] leading-[1.5] text-ink-soft">
                          {warning}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              ) : null}
              {draft.draft.open_questions?.length ? (
                <div className={cn('flex items-start gap-2.5', draft.draft.warnings?.length ? 'mt-3' : '')}>
                  <HelpCircle size={15} strokeWidth={1.8} className="mt-0.5 shrink-0 text-warn-ink" />
                  <div>
                    <div className="text-[13px] font-medium text-warn-ink">
                      {plural(draft.draft.open_questions.length, 'открытый вопрос', 'открытых вопроса', 'открытых вопросов')}{' '}
                      — задаёт методист, компилятор не выдумывает
                    </div>
                    <ul className="mt-1 space-y-1">
                      {draft.draft.open_questions.map((question, index) => (
                        <li key={index} className="max-w-[68ch] text-[12.5px] leading-[1.5] text-ink-soft">
                          {question}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}

          <ul>
            {draft.draft.rubric.criteria?.map((criterion) => {
              const source = sourceFor(criterion.id)
              const status = source?.status ?? 'missing'
              return (
                <li key={criterion.id} className="border-b border-line-soft px-5 py-3.5 last:border-b-0">
                  <div className="flex items-start justify-between gap-3">
                    <h3 className="text-[13.5px] font-medium text-ink">{criterion.title}</h3>
                    <div className="flex shrink-0 items-center gap-2">
                      <span className="num text-[12.5px] text-muted">до {criterion.max_score}</span>
                      <Badge tone={STATUS_TONE[status]}>{STATUS_LABEL[status]}</Badge>
                    </div>
                  </div>
                  {source?.quote ? (
                    <blockquote className="mt-1.5 max-w-[70ch] border-l-2 border-line pl-3 text-[12.5px] italic leading-[1.5] text-ink-soft">
                      «{source.quote}»
                    </blockquote>
                  ) : null}
                  {source?.note ? (
                    <p className="mt-1 max-w-[70ch] text-[12px] leading-[1.45] text-faint">{source.note}</p>
                  ) : null}
                </li>
              )
            })}
          </ul>

          <div className="border-t border-line px-5 py-4">
            <Field label="Кто подтверждает" hint="попадёт в рубрику как автор подтверждения">
              <input
                value={confirmedBy}
                onChange={(event) => setConfirmedBy(event.target.value)}
                placeholder="Ирина Ходасевич"
                className={cn(inputClass, 'max-w-[320px]')}
              />
            </Field>

            {confirm.isError ? (
              <p className="mt-3 rounded-lg border border-[#f0d3d3] bg-critical-wash px-3 py-2 text-[12.5px] text-critical-ink">
                {confirm.error instanceof ApiError ? confirm.error.message : 'Подтверждение не удалось'}
              </p>
            ) : null}

            <div className="mt-3 flex items-center gap-3">
              <Button
                variant="primary"
                onClick={() => confirm.mutate()}
                disabled={confirmedBy.trim().length < 2 || confirm.isPending}
              >
                {confirm.isPending ? 'Сохраняю' : 'Подтвердить и добавить в каталог'}
              </Button>
              <span className="text-[12px] text-faint">
                рубрика вступит в силу для всего потока — правки задним числом требуют явного overwrite
              </span>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
