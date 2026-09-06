import { useState } from 'react'
import { ChevronDown, ChevronUp, Plus, Quote, Trash2 } from 'lucide-react'
import type { Criterion, CriterionSource } from '@/lib/backend'
import { cn } from '@/lib/cn'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import {
  CheckboxField,
  Field,
  NumberField,
  TextAreaField,
  TextField,
} from '@/components/ui/Field'

interface Props {
  criterion: Criterion
  source: CriterionSource | null
  duplicateId: boolean
  first: boolean
  last: boolean
  defaultOpen: boolean
  onChange: (patch: Partial<Criterion>) => void
  onMove: (delta: number) => void
  onRemove: () => void
}

/** Откуда критерий взялся в черновике компилятора.
 *
 *  Показывается вплотную к критерию, а не общим списком внизу: подтверждение
 *  без видимого источника — это кнопка «ок», а не решение методиста. Цитата
 *  сверена с текстом условия программно, тем же механизмом, что цитаты ревью. */
function Source({ source }: { source: CriterionSource }) {
  if (source.status === 'quoted') {
    return (
      <div className="mark mt-2 rounded-r-md py-1.5 pl-2.5 pr-3">
        <div className="flex items-start gap-1.5">
          <Quote size={12} strokeWidth={1.7} className="mt-1 shrink-0 text-mark-rule" />
          <p className="max-w-[70ch] text-[12.5px] leading-[1.5] text-mark-ink">{source.quote}</p>
        </div>
      </div>
    )
  }

  const missing = source.status === 'missing'
  return (
    <div
      className={cn(
        'mt-2 rounded-lg px-3 py-2',
        missing ? 'bg-sunken' : 'border border-[#f0e2c2] bg-warn-wash',
      )}
    >
      <div className={cn('text-[12px] font-medium', missing ? 'text-muted' : 'text-warn-ink')}>
        {missing ? 'Фрагмента условия нет' : 'Критерий держится на пересказе'}
      </div>
      {source.quote ? (
        <p className={cn('mt-1 max-w-[70ch] text-[12.5px] leading-[1.5]', missing ? 'text-faint' : 'text-warn-ink/85')}>
          {source.quote}
        </p>
      ) : null}
      <p className={cn('mt-1 text-[11.5px] leading-[1.45]', missing ? 'text-faint' : 'text-warn-ink/85')}>
        {source.note || 'сверьте формулировку с условием сами'}
      </p>
    </div>
  )
}

/** Строковый список: проверочные пункты рубрики. Модель отвечает по каждому
 *  отдельно, поэтому пункт — единица, а не абзац сплошного текста. */
function ChecksEditor({ checks, onChange }: { checks: string[]; onChange: (next: string[]) => void }) {
  return (
    <div className="space-y-1.5">
      {checks.map((check, index) => (
        <div key={index} className="flex items-start gap-1.5">
          <TextAreaField
            value={check}
            rows={1}
            onChange={(value) => onChange(checks.map((item, position) => (position === index ? value : item)))}
            placeholder="что именно модель обязана разобрать"
          />
          <Button
            variant="ghost"
            size="sm"
            className="mt-0.5 shrink-0"
            aria-label="Убрать пункт"
            onClick={() => onChange(checks.filter((_, position) => position !== index))}
            icon={<Trash2 size={13} strokeWidth={1.7} />}
          />
        </div>
      ))}
      <Button size="sm" variant="quiet" onClick={() => onChange([...checks, ''])} icon={<Plus size={13} strokeWidth={1.9} />}>
        Пункт проверки
      </Button>
    </div>
  )
}

/** Якоря: чем уровень выполнения отличается от соседнего. Пустые лучше
 *  придуманных — компилятор их и не заполняет, если в условии этого нет. */
function AnchorsEditor({
  anchors,
  onChange,
}: {
  anchors: Record<string, string>
  onChange: (next: Record<string, string>) => void
}) {
  const rows = Object.entries(anchors)

  const rename = (from: string, to: string) => {
    onChange(Object.fromEntries(rows.map(([key, value]) => (key === from ? [to, value] : [key, value]))))
  }

  return (
    <div className="space-y-1.5">
      {rows.map(([key, value]) => (
        <div key={key} className="flex items-start gap-1.5">
          <TextField
            value={key}
            mono
            className="w-16 shrink-0"
            onChange={(next) => rename(key, next)}
            placeholder="балл"
          />
          <TextAreaField
            value={value}
            rows={1}
            onChange={(next) => onChange({ ...anchors, [key]: next })}
            placeholder="за что ставится этот балл"
          />
          <Button
            variant="ghost"
            size="sm"
            className="mt-0.5 shrink-0"
            aria-label="Убрать якорь"
            onClick={() => onChange(Object.fromEntries(rows.filter(([item]) => item !== key)))}
            icon={<Trash2 size={13} strokeWidth={1.7} />}
          />
        </div>
      ))}
      <Button
        size="sm"
        variant="quiet"
        onClick={() => onChange({ ...anchors, [String(rows.length)]: '' })}
        icon={<Plus size={13} strokeWidth={1.9} />}
      >
        Якорь
      </Button>
    </div>
  )
}

export function CriterionEditor({
  criterion,
  source,
  duplicateId,
  first,
  last,
  defaultOpen,
  onChange,
  onMove,
  onRemove,
}: Props) {
  const [open, setOpen] = useState(defaultOpen)
  const checks = criterion.checks ?? []
  const anchors = criterion.anchors ?? {}

  return (
    <article className="border-b border-line-soft last:border-b-0">
      <div className="flex items-start gap-3 px-5 py-3.5">
        <button
          onClick={() => setOpen(!open)}
          className="mt-0.5 shrink-0 text-faint transition-colors hover:text-ink"
          aria-label={open ? 'Свернуть критерий' : 'Развернуть критерий'}
        >
          <ChevronDown size={15} strokeWidth={1.8} className={cn('transition-transform', open && 'rotate-180')} />
        </button>

        <div className="min-w-0 flex-1">
          <button onClick={() => setOpen(!open)} className="block w-full text-left">
            <span className="text-[14px] font-medium text-ink">
              {criterion.title || <span className="text-faint">Критерий без названия</span>}
            </span>
          </button>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <span className={cn('font-mono text-[11.5px]', duplicateId ? 'text-critical-ink' : 'text-faint')}>
              {criterion.id || '—'}
            </span>
            {duplicateId ? <Badge tone="critical">идентификатор повторяется</Badge> : null}
            {criterion.min_score_for_pass != null ? (
              <Badge tone="critical">обязательный минимум {criterion.min_score_for_pass}</Badge>
            ) : null}
            {criterion.auto_verifiable ? <Badge tone="neutral">проверяется автоматически</Badge> : null}
            {criterion.ai_sensitive ? <Badge tone="mark">важна самостоятельность</Badge> : null}
            {!criterion.evidence_required ? <Badge tone="neutral">без обязательной цитаты</Badge> : null}
          </div>
        </div>

        <span className="num shrink-0 pt-0.5 text-[13.5px] text-muted">
          до {criterion.max_score}
          {criterion.weight !== 1 ? ` × ${criterion.weight}` : ''}
        </span>

        <div className="flex shrink-0 items-center">
          <Button
            variant="ghost"
            size="sm"
            disabled={first}
            onClick={() => onMove(-1)}
            aria-label="Выше"
            icon={<ChevronUp size={14} strokeWidth={1.8} />}
          />
          <Button
            variant="ghost"
            size="sm"
            disabled={last}
            onClick={() => onMove(1)}
            aria-label="Ниже"
            icon={<ChevronDown size={14} strokeWidth={1.8} />}
          />
          <Button
            variant="ghost"
            size="sm"
            onClick={onRemove}
            aria-label="Удалить критерий"
            icon={<Trash2 size={14} strokeWidth={1.7} />}
          />
        </div>
      </div>

      {source && !open ? <div className="px-5 pb-3.5 pl-[38px]"><Source source={source} /></div> : null}

      {open ? (
        <div className="space-y-4 border-t border-line-soft bg-[#f8f9f6] px-5 py-4">
          {source ? <Source source={source} /> : null}

          <div className="grid gap-3 sm:grid-cols-[1fr_140px]">
            <Field label="Название">
              <TextField
                value={criterion.title}
                onChange={(title) => onChange({ title })}
                placeholder="Хендлеры и маршрутизация"
              />
            </Field>
            <Field label="Идентификатор" hint="на него ссылается вердикт">
              <TextField value={criterion.id} mono onChange={(id) => onChange({ id })} placeholder="c1" />
            </Field>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Максимум">
              <NumberField value={criterion.max_score} onChange={(value) => onChange({ max_score: value ?? 0 })} />
            </Field>
            <Field label="Вес" hint="сервер складывает балл × вес">
              <NumberField value={criterion.weight} onChange={(value) => onChange({ weight: value ?? 1 })} />
            </Field>
            <Field label="Обязательный минимум" hint="пусто — минимума нет">
              <NumberField
                value={criterion.min_score_for_pass ?? null}
                nullable
                placeholder="нет"
                onChange={(value) => onChange({ min_score_for_pass: value })}
              />
            </Field>
          </div>

          {criterion.min_score_for_pass != null ? (
            <p className="rounded-lg border border-[#f0d3d3] bg-critical-wash px-3 py-2 text-[12px] leading-[1.5] text-critical-ink">
              Ниже этого балла работа не засчитывается целиком, сколько бы ни было набрано на
              остальных критериях. Проверьте, что это правда написано в условии.
            </p>
          ) : null}

          <Field label="Описание" hint="что этот критерий вообще оценивает">
            <TextAreaField
              value={criterion.description ?? ''}
              onChange={(description) => onChange({ description })}
              placeholder="Чему посвящён критерий, если названия мало"
            />
          </Field>

          <Field
            label={`Проверочные пункты${checks.length ? ` · ${checks.length}` : ''}`}
            hint="модель отвечает по каждому отдельно — от этого разброс между прогонами резко падает"
          >
            <ChecksEditor checks={checks} onChange={(next) => onChange({ checks: next })} />
          </Field>

          <Field label="Якоря шкалы" hint="чем один балл отличается от соседнего; пустые лучше придуманных">
            <AnchorsEditor anchors={anchors} onChange={(next) => onChange({ anchors: next })} />
          </Field>

          <div className="grid gap-2.5 sm:grid-cols-3">
            <CheckboxField
              checked={criterion.evidence_required}
              onChange={(evidence_required) => onChange({ evidence_required })}
              label="Цитата обязательна"
              hint="вердикт без подтверждённой цитаты помечается спорным"
            />
            <CheckboxField
              checked={criterion.auto_verifiable}
              onChange={(auto_verifiable) => onChange({ auto_verifiable })}
              label="Проверяется автоматически"
              hint="Format Gate или тесты, а не модель"
            />
            <CheckboxField
              checked={criterion.ai_sensitive}
              onChange={(ai_sensitive) => onChange({ ai_sensitive })}
              label="Важна самостоятельность"
              hint="сигнал детектора здесь показывается первым"
            />
          </div>
        </div>
      ) : null}
    </article>
  )
}
