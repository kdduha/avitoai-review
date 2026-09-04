import type { DetectResponse, ReviewResponse } from '@/lib/backend'

export interface DemoFile {
  path: string
  lang: string
  firstLine: number
  partial: boolean
  origin: string
  changedLines: string
  text: string
}

/** Цитаты ищутся по тексту файла, а не проставляются руками: так демо ведёт
 *  себя как настоящий валидатор — если фрагмента нет, это видно сразу. */
export function locator(files: DemoFile[]) {
  return (artifact: string, quote: string) => {
    const file = files.find((item) => item.path === artifact)
    const lines = file?.text.split('\n') ?? []
    const needle = quote.split('\n')[0].trim()
    const index = lines.findIndex((line) => line.trim() === needle)
    const found = file && index !== -1

    return {
      artifact,
      start_line: found ? index + file.firstLine : null,
      end_line: found ? index + file.firstLine + quote.split('\n').length - 1 : null,
      quote,
      status: found ? ('valid' as const) : ('wrong_location' as const),
      char_start: null,
      char_end: null,
      note: found ? '' : 'фрагмента нет в указанных строках',
    }
  }
}

export function toArtifacts(files: DemoFile[]): ReviewResponse['files'] {
  return files.map((file) => ({
    path: file.path,
    role: 'solution',
    lang: file.lang,
    partial: file.partial,
    origin: file.origin,
    first_line: file.firstLine,
    last_line: file.firstLine + file.text.split('\n').length - 1,
    line_numbers: file.text.split('\n').map((_, index) => file.firstLine + index),
    changed_lines: file.changedLines,
    text: file.text,
  }))
}

export type DemoRun = { review: ReviewResponse; detect: DetectResponse }
