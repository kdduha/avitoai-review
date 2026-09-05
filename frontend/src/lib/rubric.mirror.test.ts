/** Сторож против тихого расхождения с сервером.
 *
 *  `lib/rubric.ts` повторяет `validate_rubric` из
 *  `backend/src/avito_reviewer/ai/rubric.py` — это осознанное дублирование:
 *  список поломок нужен методисту во время правки, а не после отказа сервера.
 *  Плата за него — риск, что правило поменяют на сервере, а здесь забудут.
 *
 *  Тест не проверяет смысл, он ловит движение: изменилось число правил или
 *  формулировка — тест падает и заставляет прочитать оба файла. Смысл
 *  проверяет `rubric.test.ts`.
 */

import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { ID_PATTERN } from './rubric'

const here = dirname(fileURLToPath(import.meta.url))
const PY = readFileSync(join(here, '../../../backend/src/avito_reviewer/ai/rubric.py'), 'utf-8')
const TS = readFileSync(join(here, 'rubric.ts'), 'utf-8')

/** Тело `validate_rubric` — от заголовка до следующего определения верхнего уровня. */
function validateRubricBody(source: string): string {
  const start = source.indexOf('def validate_rubric(')
  expect(start, 'в rubric.py не нашлась validate_rubric — файл переименовали?').toBeGreaterThan(-1)
  const rest = source.slice(start)
  const end = rest.slice(1).search(/\n(?:def |class |@)/)
  return end === -1 ? rest : rest.slice(0, end + 1)
}

const BODY = validateRubricBody(PY)
const hasCyrillic = (text: string) => /[а-яё]/i.test(text)

describe('зеркало validate_rubric', () => {
  it('число правил не изменилось', () => {
    const rules = BODY.match(/problems\.append\(/g)?.length ?? 0
    expect(
      rules,
      'на сервере изменилось число проверок рубрики — приведите rubricProblems в соответствие',
    ).toBe(9)
  })

  /** Формулировки сервера, разбитые по подстановкам f-строк. Пользователь
   *  видит их и на экране, и в ответе сервера — расходиться они не должны. */
  const fragments = [
    ...new Set(
      [...BODY.replace(/"""[\s\S]*?"""/g, '').matchAll(/f?"([^"\n]*)"/g)]
        .map((match) => match[1])
        .filter(hasCyrillic)
        .flatMap((literal) => literal.split(/\{[^}]*\}/))
        .map((piece) => piece.trim())
        .filter((piece) => piece.length >= 10),
    ),
  ]

  it('фрагменты формулировок вообще нашлись', () => {
    expect(fragments.length).toBeGreaterThan(8)
  })

  it.each(fragments)('формулировка сервера «%s» есть в зеркале', (fragment) => {
    expect(TS).toContain(fragment)
  })

  it('ограничение на идентификатор совпадает с серверным', () => {
    const server = PY.match(/ID_PATTERN\s*=\s*re\.compile\(r"([^"]+)"\)/)?.[1]
    expect(server, 'ID_PATTERN на сервере не нашёлся').toBeTruthy()
    expect(ID_PATTERN.source).toBe(server)
  })
})
