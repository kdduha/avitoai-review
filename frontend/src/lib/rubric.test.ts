/** Зеркало серверных проверок рубрики.
 *
 *  Проверяется не то, что функция работает, а что она работает **так же, как
 *  `validate_rubric` на сервере**: иначе редактор пропустит рубрику, которую
 *  сервер отвергнет, или заблокирует кнопку на ровном месте. Формулировки
 *  поломок сверяются дословно.
 */

import { readdirSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import type { Criterion, Rubric } from './backend'
import {
  blankRubric,
  normalizeRubric,
  reachableMax,
  rubricAdvisories,
  rubricProblems,
} from './rubric'

const RUBRICS_DIR = join(dirname(fileURLToPath(import.meta.url)), '../../../backend/rubrics')

function criterion(patch: Partial<Criterion> = {}): Criterion {
  return {
    id: 'c1',
    title: 'Критерий',
    max_score: 1,
    min_score_for_pass: null,
    weight: 1,
    description: '',
    checks: [],
    anchors: {},
    evidence_required: true,
    auto_verifiable: false,
    ai_sensitive: false,
    ...patch,
  }
}

function rubric(patch: Partial<Rubric> = {}): Rubric {
  return normalizeRubric({
    ...blankRubric(),
    assignment_id: 'demo-task1',
    title: 'Демо',
    course: 'Демо-курс',
    scale: { total_max: 1, pass_threshold: null, step: 1 },
    criteria: [criterion()],
    ...patch,
  })
}

describe('rubricProblems — рубрики каталога', () => {
  const files = readdirSync(RUBRICS_DIR).filter((name) => name.endsWith('.json'))

  it('каталог не пуст — иначе тест ничего не проверяет', () => {
    expect(files.length).toBeGreaterThan(0)
  })

  /* Эти рубрики сервер принял и по ним проверяются работы. Если зеркало
     находит в них поломку — сломано зеркало, а не рубрика. */
  it.each(files)('%s принимается зеркалом', (name) => {
    const loaded = JSON.parse(readFileSync(join(RUBRICS_DIR, name), 'utf-8')) as Rubric
    expect(rubricProblems(normalizeRubric(loaded))).toEqual([])
  })
})

describe('rubricProblems — правила сервера', () => {
  it('чистая рубрика не даёт поломок', () => {
    expect(rubricProblems(rubric())).toEqual([])
  })

  it('идентификатор не годится для имени файла', () => {
    expect(rubricProblems(rubric({ assignment_id: 'го/таск 1' }))).toContain(
      "идентификатор 'го/таск 1' не годится для имени файла: " +
        'латиница, цифры, точка, дефис и подчёркивание',
    )
  })

  it('идентификатор длиннее 64 символов не проходит', () => {
    expect(rubricProblems(rubric({ assignment_id: 'a'.repeat(65) }))).toHaveLength(1)
    expect(rubricProblems(rubric({ assignment_id: 'a'.repeat(64) }))).toEqual([])
  })

  it('рубрика без критериев', () => {
    const problems = rubricProblems(rubric({ criteria: [], scale: { total_max: 1, pass_threshold: null, step: 1 } }))
    expect(problems).toContain('в рубрике нет ни одного критерия')
  })

  it('повторяющиеся идентификаторы критериев перечисляются по разу', () => {
    const problems = rubricProblems(
      rubric({
        scale: { total_max: 3, pass_threshold: null, step: 1 },
        criteria: [criterion({ id: 'c1' }), criterion({ id: 'c1' }), criterion({ id: 'c1' })],
      }),
    )
    expect(problems).toContain('повторяющиеся идентификаторы критериев: c1')
  })

  it('максимум шкалы должен быть больше нуля', () => {
    expect(rubricProblems(rubric({ scale: { total_max: 0, pass_threshold: null, step: 1 } }))).toContain(
      'максимальный балл должен быть больше нуля',
    )
  })

  it('шаг шкалы не может быть отрицательным, но ноль допустим', () => {
    expect(rubricProblems(rubric({ scale: { total_max: 1, pass_threshold: null, step: -1 } }))).toContain(
      'шаг шкалы не может быть отрицательным',
    )
    expect(rubricProblems(rubric({ scale: { total_max: 1, pass_threshold: null, step: 0 } }))).toEqual([])
  })

  it('порог зачёта выше максимума — зачёт недостижим', () => {
    const problems = rubricProblems(rubric({ scale: { total_max: 1, pass_threshold: 1.5, step: 0.5 } }))
    expect(problems).toContain('порог зачёта 1.5 выше максимума 1 — зачёт недостижим')
  })

  it('порог, равный максимуму, допустим — работа может встать ровно на пороге', () => {
    expect(rubricProblems(rubric({ scale: { total_max: 1, pass_threshold: 1, step: 0.5 } }))).toEqual([])
  })

  it('максимум критерия должен быть больше нуля', () => {
    const problems = rubricProblems(
      rubric({
        scale: { total_max: 1, pass_threshold: null, step: 1 },
        criteria: [criterion({ id: 'c9', max_score: 0 })],
      }),
    )
    expect(problems).toContain('c9: максимум критерия должен быть больше нуля')
  })

  it('обязательный минимум выше максимума критерия — критерий провален всегда', () => {
    const problems = rubricProblems(
      rubric({
        scale: { total_max: 2, pass_threshold: null, step: 0.5 },
        criteria: [criterion({ id: 'c3', max_score: 2, min_score_for_pass: 2.5 })],
      }),
    )
    expect(problems).toContain(
      'c3: обязательный минимум 2.5 выше максимума 2 — критерий провален всегда',
    )
  })

  it('минимум, равный максимуму, допустим', () => {
    expect(
      rubricProblems(
        rubric({
          scale: { total_max: 2, pass_threshold: null, step: 0.5 },
          criteria: [criterion({ max_score: 2, min_score_for_pass: 2 })],
        }),
      ),
    ).toEqual([])
  })

  it('недостижимый максимум шкалы', () => {
    const problems = rubricProblems(
      rubric({
        scale: { total_max: 10, pass_threshold: null, step: 1 },
        criteria: [criterion({ max_score: 3 })],
      }),
    )
    expect(problems).toContain(
      'максимум 10 недостижим: по всем критериям с весами набирается 3',
    )
  })

  it('перебор по критериям недостижимым не считается — веса это разрешают', () => {
    expect(
      rubricProblems(
        rubric({
          scale: { total_max: 5, pass_threshold: null, step: 1 },
          criteria: [criterion({ max_score: 8 })],
        }),
      ),
    ).toEqual([])
  })
})

describe('reachableMax', () => {
  it('складывает балл × вес', () => {
    const value = reachableMax(
      rubric({
        scale: { total_max: 1, pass_threshold: null, step: 1 },
        criteria: [criterion({ id: 'c1', max_score: 2, weight: 1.5 }), criterion({ id: 'c2', max_score: 1 })],
      }),
    )
    expect(value).toBe(4)
  })

  /* Сервер читает вес как `c.weight or 1.0`, то есть ноль превращается в
     единицу. Иначе экран объявит недостижимой шкалу, которую сервер примет. */
  it('нулевой вес читается как единица — как на сервере', () => {
    const value = reachableMax(
      rubric({
        scale: { total_max: 1, pass_threshold: null, step: 1 },
        criteria: [criterion({ max_score: 3, weight: 0 })],
      }),
    )
    expect(value).toBe(3)
  })

  it('дробные веса округляются до четвёртого знака, как на сервере', () => {
    const value = reachableMax(
      rubric({
        scale: { total_max: 1, pass_threshold: null, step: 1 },
        criteria: [criterion({ max_score: 0.1, weight: 0.2 })],
      }),
    )
    expect(value).toBe(0.02)
  })
})

describe('rubricAdvisories', () => {
  it('замечания не пересекаются с поломками', () => {
    const value = rubric({ title: '', course: '' })
    expect(rubricProblems(value)).toEqual([])
    expect(rubricAdvisories(value)).toHaveLength(2)
  })

  it('критерий без названия попадает в замечания по идентификатору', () => {
    const notes = rubricAdvisories(
      rubric({
        scale: { total_max: 1, pass_threshold: null, step: 1 },
        criteria: [criterion({ id: 'c7', title: '  ' })],
      }),
    )
    expect(notes.some((note) => note.includes('c7'))).toBe(true)
  })

  it('заполненная рубрика замечаний не собирает', () => {
    expect(rubricAdvisories(rubric())).toEqual([])
  })
})
