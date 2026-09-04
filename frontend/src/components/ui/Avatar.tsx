import { cn } from '@/lib/cn'

const TINTS = ['#e7eefb', '#fdeee7', '#e6f6ef', '#fbf2e0', '#fbeaf1', '#eceafa']
const INKS = ['#1c5cab', '#a44a20', '#0f7150', '#8a5a00', '#a63e68', '#3a2e85']

function slot(seed: string): number {
  let sum = 0
  for (const char of seed) sum += char.charCodeAt(0)
  return sum % TINTS.length
}

export function Avatar({ name, size = 26, className }: { name: string; size?: number; className?: string }) {
  const index = slot(name)
  const short = name
    .split(' ')
    .slice(0, 2)
    .map((part) => part[0])
    .join('')

  return (
    <span
      className={cn('inline-flex shrink-0 items-center justify-center rounded-full font-semibold', className)}
      style={{
        width: size,
        height: size,
        background: TINTS[index],
        color: INKS[index],
        fontSize: Math.round(size * 0.42),
      }}
      aria-hidden
    >
      {short}
    </span>
  )
}
