const DATE = new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: '2-digit' })
const DATE_TIME = new Intl.DateTimeFormat('ru-RU', {
  day: '2-digit',
  month: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
})

export const formatDate = (iso: string): string => DATE.format(new Date(iso))
export const formatDateTime = (iso: string): string => DATE_TIME.format(new Date(iso))

export function timeLeft(from: string, to: string): string {
  const minutes = Math.round((new Date(to).getTime() - new Date(from).getTime()) / 60000)
  if (minutes < 0) return `просрочено на ${formatDuration(-minutes)}`
  return `за ${formatDuration(minutes)} до дедлайна`
}

export function formatDuration(minutes: number): string {
  const days = Math.floor(minutes / 1440)
  const hours = Math.floor((minutes % 1440) / 60)
  const rest = minutes % 60
  if (days) return `${days} д ${hours} ч`
  if (hours) return `${hours} ч ${rest ? `${rest} мин` : ''}`.trim()
  return `${rest} мин`
}

export function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return one
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few
  return many
}

export const percent = (value: number): string => `${Math.round(value * 100)}%`
