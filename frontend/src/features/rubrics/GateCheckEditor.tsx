import { useEffect, useRef, useState } from 'react'
import { ChevronDown, CircleHelp, Trash2 } from 'lucide-react'
import type { FormatCheck } from '@/lib/backend'
import { checkLabel, gateKind, GATE_KINDS, type ParamField } from '@/lib/rubric'
import { cn } from '@/lib/cn'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Field, NumberField, SelectField, TextAreaField, TextField } from '@/components/ui/Field'

type Params = Record<string, unknown>

const LEVELS = [
  { value: 'blocking' as const, label: 'блокирует — к ревьюеру без прогона модели' },
  { value: 'warning' as const, label: 'предупреждает — флаг в карточке' },
  { value: 'info' as const, label: 'справочно — факт в контекст ревью-агента' },
]

/** Те же слова, что на экране чтения рубрики: одна проверка не должна
 *  называться по-разному в списке и в правке. */
const LEVEL_BADGE = {
  blocking: { tone: 'critical' as const, label: 'блокирует' },
  warning: { tone: 'warn' as const, label: 'предупреждает' },
  info: { tone: 'neutral' as const, label: 'справочно' },
}

const CUSTOM = '__custom__'

const asList = (value: unknown): string =>
  Array.isArray(value) ? value.map(String).join('\n') : typeof value === 'string' ? value : ''

function ParamInput({
  field,
  params,
  onChange,
}: {
  field: ParamField
  params: Params
  onChange: (params: Params) => void
}) {
  const value = params[field.key]

  if (field.kind === 'number') {
    return (
      <NumberField
        value={typeof value === 'number' ? value : null}
        nullable
        placeholder="не задано"
        onChange={(next) => onChange({ ...params, [field.key]: next ?? undefined })}
      />
    )
  }

  if (field.kind === 'list') {
    return (
      <TextAreaField
        mono
        rows={2}
        value={asList(value)}
        onChange={(next) =>
          onChange({
            ...params,
            [field.key]: next
              .split('\n')
              .map((line) => line.trim())
              .filter(Boolean),
          })
        }
      />
    )
  }

  return (
    <TextField
      mono={field.key === 'pattern'}
      value={typeof value === 'string' ? value : ''}
      onChange={(next) => onChange({ ...params, [field.key]: next })}
    />
  )
}

/** Параметры, которых нет в справочнике, редактируются как есть.
 *
 *  `params` у проверки — свободный словарь, и справочник покрывает только то,
 *  что встречалось в рубриках. Спрятать остальное значит потерять его при
 *  первом сохранении, поэтому неизвестное правится текстом JSON. */
function RawParams({ params, onChange }: { params: Params; onChange: (params: Params) => void }) {
  const show = (input: Params) => JSON.stringify(input, null, 2)
  const [text, setText] = useState(() => show(params))
  const [broken, setBroken] = useState(false)
  const dirty = useRef(false)

  useEffect(() => {
    if (!dirty.current) setText(show(params))
  }, [params])

  return (
    <div>
      <TextAreaField
        mono
        rows={4}
        value={text}
        onChange={(next) => {
          dirty.current = true
          setText(next)
          try {
            const parsed: unknown = JSON.parse(next || '{}')
            if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
              setBroken(false)
              onChange(parsed as Params)
            } else {
              setBroken(true)
            }
          } catch {
            setBroken(true)
          }
        }}
        onBlur={() => {
          dirty.current = false
          if (!broken) setText(show(params))
        }}
        className={cn(broken && 'border-[#f0d3d3]')}
      />
      {broken ? (
        <p className="mt-1 text-[11.5px] text-critical-ink">
          Это не объект JSON — правка не применяется, пока текст не станет разбираемым.
        </p>
      ) : null}
    </div>
  )
}

export function GateCheckEditor({
  check,
  defaultOpen,
  onChange,
  onRemove,
}: {
  check: FormatCheck
  defaultOpen: boolean
  onChange: (patch: Partial<FormatCheck>) => void
  onRemove: () => void
}) {
  const [open, setOpen] = useState(defaultOpen)
  const kind = gateKind(check.check)
  const params = (check.params ?? {}) as Params
  const known = new Set([...(kind?.params ?? []).map((field) => field.key), 'label'])
  const extra = Object.keys(params).filter((key) => !known.has(key))
  const badge = LEVEL_BADGE[check.level]

  return (
    <div className="border-b border-line-soft last:border-b-0">
      <div className="flex items-start gap-3 px-5 py-3">
        <button
          onClick={() => setOpen(!open)}
          className="mt-0.5 shrink-0 text-faint transition-colors hover:text-ink"
          aria-label={open ? 'Свернуть проверку' : 'Развернуть проверку'}
        >
          <ChevronDown size={15} strokeWidth={1.8} className={cn('transition-transform', open && 'rotate-180')} />
        </button>

        <div className="min-w-0 flex-1">
          <button onClick={() => setOpen(!open)} className="block w-full text-left">
            <span className="text-[13.5px] text-ink">
              {checkLabel(check) || <span className="text-faint">Проверка без формулировки</span>}
            </span>
          </button>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <Badge tone={badge.tone}>{badge.label}</Badge>
            <span className="font-mono text-[11.5px] text-faint">{check.check || '—'}</span>
            {kind && !kind.executed ? <Badge tone="neutral">гейт не исполняет</Badge> : null}
            {!kind && check.check ? <Badge tone="neutral">обработчика нет</Badge> : null}
          </div>
        </div>

        <Button
          variant="ghost"
          size="sm"
          className="shrink-0"
          onClick={onRemove}
          aria-label="Убрать проверку"
          icon={<Trash2 size={14} strokeWidth={1.7} />}
        />
      </div>

      {open ? (
      <div className="border-t border-line-soft bg-[#f8f9f6] px-5 py-4">
      <div className="flex items-start gap-2.5">
        <div className="grid min-w-0 flex-1 gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
          <Field label="Что проверяем">
            <SelectField
              value={kind ? check.check : CUSTOM}
              onChange={(next) =>
                next === CUSTOM
                  ? onChange({ check: '' })
                  : onChange({ check: next, params: { ...(params.label ? { label: params.label } : {}) } })
              }
              options={[
                ...GATE_KINDS.map((item) => ({ value: item.check, label: item.label })),
                { value: CUSTOM, label: 'другая проверка' },
              ]}
            />
          </Field>
          <Field label="Уровень">
            <SelectField
              value={check.level}
              onChange={(level) => onChange({ level })}
              options={LEVELS}
            />
          </Field>
        </div>
      </div>

      {kind ? (
        <p className="mt-1.5 text-[12px] leading-[1.45] text-faint">{kind.hint}</p>
      ) : (
        <div className="mt-3">
          <Field label="Идентификатор проверки" hint="как её назовёт гейт в отчёте">
            <TextField value={check.check} mono onChange={(next) => onChange({ check: next })} />
          </Field>
        </div>
      )}

      {kind && !kind.executed ? (
        <div className="mt-2.5 flex items-start gap-2 rounded-lg bg-sunken px-3 py-2">
          <CircleHelp size={13} strokeWidth={1.7} className="mt-0.5 shrink-0 text-faint" />
          <p className="max-w-[72ch] text-[12px] leading-[1.5] text-muted">
            Гейт эту проверку не исполняет и молча её не теряет: она уйдёт ревьюеру со статусом
            «ответить по доступным данным нельзя». Это не провал работы, но и не проверка — учтите
            это, выбирая уровень.
          </p>
        </div>
      ) : null}

      {!kind && check.check ? (
        <div className="mt-2.5 flex items-start gap-2 rounded-lg bg-sunken px-3 py-2">
          <CircleHelp size={13} strokeWidth={1.7} className="mt-0.5 shrink-0 text-faint" />
          <p className="max-w-[72ch] text-[12px] leading-[1.5] text-muted">
            Обработчика с таким именем у гейта нет — проверка уйдёт ревьюеру как непроверенная.
          </p>
        </div>
      ) : null}

      <div className="mt-3 space-y-3">
        <Field label="Формулировка для ревьюера" hint="ей проверка называется в отчёте гейта">
          <TextField
            value={typeof params.label === 'string' ? params.label : ''}
            onChange={(label) => onChange({ params: { ...params, label } })}
            placeholder={kind?.label ?? 'что увидит человек'}
          />
        </Field>

        {(kind?.params ?? []).map((field) => (
          <Field key={field.key} label={field.label} hint={field.hint}>
            <ParamInput field={field} params={params} onChange={(next) => onChange({ params: next })} />
          </Field>
        ))}

        {!kind || extra.length ? (
          <Field
            label="Параметры целиком"
            hint={
              kind
                ? `в этой проверке есть поля вне справочника: ${extra.join(', ')}`
                : 'у своей проверки параметры произвольные'
            }
          >
            <RawParams params={params} onChange={(next) => onChange({ params: next })} />
          </Field>
        ) : null}

        <Field label="Откуда требование" hint="цитата из условия — по ней проверку потом можно защитить">
          <TextAreaField
            rows={2}
            value={check.note ?? ''}
            onChange={(note) => onChange({ note })}
            placeholder="«Разделите код на логические директории (cmd/, internal/, pkg/)»"
          />
        </Field>
      </div>

      {check.level === 'blocking' ? (
        <p className="mt-3 text-[12px] leading-[1.5] text-critical-ink">
          Блокирующая: работа уйдёт человеку, модель не запустится и прогон не будет стоить ничего.
        </p>
      ) : null}
      </div>
      ) : null}
    </div>
  )
}
