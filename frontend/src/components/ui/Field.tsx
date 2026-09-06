import { useEffect, useRef, useState, type ReactNode, type TextareaHTMLAttributes } from 'react'
import { cn } from '@/lib/cn'

export const inputClass =
  'h-9 w-full rounded-lg border border-line bg-raised px-3 text-[13.5px] text-ink outline-none ' +
  'placeholder:text-faint focus:border-accent-line'

export function Field({
  label,
  hint,
  children,
  className,
}: {
  label: ReactNode
  hint?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <label className={cn('block', className)}>
      <span className="text-[12.5px] font-medium text-ink">{label}</span>
      {hint ? <span className="mt-0.5 block text-[12px] leading-[1.45] text-faint">{hint}</span> : null}
      <span className="mt-1.5 block">{children}</span>
    </label>
  )
}

export function TextField({
  value,
  onChange,
  placeholder,
  mono,
  className,
}: {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  mono?: boolean
  className?: string
}) {
  return (
    <input
      value={value}
      onChange={(event) => onChange(event.target.value)}
      placeholder={placeholder}
      className={cn(inputClass, mono && 'font-mono text-[12.5px]', className)}
    />
  )
}

/** Число, которое печатают руками.
 *
 *  Пока поле в фокусе, текст принадлежит пользователю: «0.» и «-» — законные
 *  промежуточные состояния, а `Number('0.')` даёт 0 и стирает точку из-под
 *  курсора. Наружу уходит только разобранное, на выходе текст приводится к
 *  значению.
 */
export function NumberField({
  value,
  onChange,
  nullable = false,
  placeholder,
  className,
}: {
  value: number | null
  onChange: (value: number | null) => void
  nullable?: boolean
  placeholder?: string
  className?: string
}) {
  const show = (input: number | null) => (input === null ? '' : String(input))
  const [text, setText] = useState(() => show(value))
  const focused = useRef(false)

  useEffect(() => {
    if (!focused.current) setText(show(value))
  }, [value])

  return (
    <input
      inputMode="decimal"
      value={text}
      placeholder={placeholder}
      onFocus={() => {
        focused.current = true
      }}
      onBlur={() => {
        focused.current = false
        setText(show(value))
      }}
      onChange={(event) => {
        const next = event.target.value
        setText(next)
        const trimmed = next.trim().replace(',', '.')
        if (!trimmed) {
          if (nullable) onChange(null)
          return
        }
        const parsed = Number(trimmed)
        if (Number.isFinite(parsed)) onChange(parsed)
      }}
      className={cn(inputClass, 'num', className)}
    />
  )
}

export function TextAreaField({
  value,
  onChange,
  rows = 3,
  mono,
  className,
  ...rest
}: {
  value: string
  onChange: (value: string) => void
  rows?: number
  mono?: boolean
} & Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, 'value' | 'onChange' | 'rows'>) {
  return (
    <textarea
      value={value}
      rows={rows}
      onChange={(event) => onChange(event.target.value)}
      className={cn(
        'w-full resize-y rounded-lg border border-line bg-raised px-3 py-2 text-[13.5px] leading-[1.55]',
        'text-ink outline-none placeholder:text-faint focus:border-accent-line',
        mono && 'font-mono text-[12.5px]',
        className,
      )}
      {...rest}
    />
  )
}

export function SelectField<T extends string>({
  value,
  onChange,
  options,
  className,
}: {
  value: T
  onChange: (value: T) => void
  options: { value: T; label: string }[]
  className?: string
}) {
  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value as T)}
      className={cn(inputClass, 'appearance-none', className)}
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  )
}

export function CheckboxField({
  checked,
  onChange,
  label,
  hint,
}: {
  checked: boolean
  onChange: (checked: boolean) => void
  label: string
  hint?: string
}) {
  return (
    <label className="flex cursor-pointer items-start gap-2.5">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="mt-0.5 size-4 shrink-0 accent-[#1c5cab]"
      />
      <span className="min-w-0">
        <span className="block text-[13px] text-ink">{label}</span>
        {hint ? <span className="block text-[12px] leading-[1.45] text-faint">{hint}</span> : null}
      </span>
    </label>
  )
}
