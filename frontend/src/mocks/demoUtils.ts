import type { DetectResponse, ReviewResponse } from '@/lib/backend'

export interface DemoFile {
  path: string
  lang: string
  firstLine: number
  partial: boolean
  origin: string
  changedLines: string
  text: string
  /** Номер каждой строки `text` в полной версии файла.
   *
   *  Только для текста, собранного из ханков диффа: там нумерация идёт с
   *  пропусками (20–30, затем 63–78), и счёт от `firstLine` увёл бы цитату на
   *  чужую строку. У целого файла поле опускается. */
  lineNumbers?: number[]
}

/** Номера строк файла в координатах его полной версии. */
function numbersOf(file: DemoFile): number[] {
  const lines = file.text.split('\n')
  if (file.lineNumbers?.length === lines.length) return file.lineNumbers
  return lines.map((_, index) => file.firstLine + index)
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
    const numbers = file ? numbersOf(file) : []
    const height = quote.split('\n').length

    return {
      artifact,
      start_line: found ? numbers[index] : null,
      end_line: found ? (numbers[index + height - 1] ?? numbers[index] + height - 1) : null,
      quote,
      status: found ? ('valid' as const) : ('wrong_location' as const),
      char_start: null,
      char_end: null,
      note: found ? '' : 'фрагмента нет в указанных строках',
    }
  }
}

export function toArtifacts(files: DemoFile[]): ReviewResponse['files'] {
  return files.map((file) => {
    const numbers = numbersOf(file)
    return {
      path: file.path,
      role: 'solution',
      lang: file.lang,
      partial: file.partial,
      origin: file.origin,
      first_line: numbers[0] ?? file.firstLine,
      last_line: numbers[numbers.length - 1] ?? file.firstLine,
      line_numbers: numbers,
      changed_lines: file.changedLines,
      text: file.text,
    }
  })
}

export type DemoRun = { review: ReviewResponse; detect: DetectResponse }
