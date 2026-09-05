/** Ведомость: формула, шкала оценок и девять настоящих строк.
 *
 *  Источник — `workflow/фиксация результатов.png` из репозитория
 *  организаторов: скриншот той самой Google-таблицы, в которую ревьюер руками
 *  переносит результат. Колонки на скриншоте:
 *  ID | Итоговая сумма | Посещаемость | Вовлеченность | Количество дз |
 *  Экзамен | Итог | Оценка | Согласие на оценку.
 *
 *  Всё, что мы про эту ведомость знаем, проверено арифметикой на всех девяти
 *  строках и записано здесь:
 *
 *  1. `итог = сумма × 0.5 + экзамен × 0.4 + вовлечённость / 10`.
 *     Посещаемость в формулу не входит — это отдельная колонка.
 *  2. Вовлечённость принимает ровно три значения: 0, 10, 20.
 *  3. Экзамен у всех девяти — 30; это максимум, а не совпадение.
 *  4. Оценка выводится из итога по таблице абсолютных порогов (см. `MARK_TABLE`).
 *     Пороги в долях от максимума, которые стояли здесь раньше
 *     (0.9 → 10, 0.83 → 9, …), воспроизводят только четыре строки из девяти.
 *  5. В колонке «Количество дз» у одной строки стоит «ю» — настоящая опечатка
 *     из настоящей таблицы, поэтому тип колонки `number | string`.
 *  6. «Согласие на оценку» — свободный текст, а не форма: в девяти строках
 *     пять разных написаний.
 *
 *  Курс, с которого снята ведомость, состоял из девяти домашних работ, и
 *  «Итоговая сумма» ведётся на его шкале — отсюда `LEDGER_HOMEWORK_MAX`.
 */

export interface LedgerRow {
  /** Обезличенный id студента — так же, как в таблице организаторов. */
  id: string
  /** «Итоговая сумма» — сумма за домашние работы на шкале курса. */
  homework: number
  attendance: number
  /** 0, 10 или 20 — других значений в ведомости нет. */
  engagement: number
  /** Максимум 30. */
  exam: number
  /** «Количество дз». В одной настоящей строке вместо числа стоит «ю». */
  homeworkCount?: number | string
  /** «Согласие на оценку», свободный текст. */
  consent: string
}

/** Девять домашних работ по 10 баллов — шкала курса, с которого снята
 *  ведомость. К ней приводится «Итоговая сумма»: у наших программ заданий от
 *  одного до пяти, и если бы сумма считалась по ним, ни один студент не
 *  дотянулся бы до порога «≥ 45 → 10» из настоящей таблицы. */
export const LEDGER_HOMEWORK_MAX = 90

/** Максимум за экзамен: у всех девяти настоящих строк ровно 30. */
export const LEDGER_EXAM_MAX = 30

/** Формула организаторов. Округление до сотых — иначе не воспроизводится
 *  строка 171345 с итогом 41,25. */
export function ledgerTotal(homework: number, exam: number, engagement: number): number {
  return Math.round((homework * 0.5 + exam * 0.4 + engagement / 10) * 100) / 100
}

/** Таблица оценок, выведенная из девяти настоящих строк: она воспроизводит их
 *  все без единого промаха. Пороги абсолютные, а не в долях от максимума. */
export const MARK_TABLE: readonly (readonly [number, number])[] = [
  [45, 10],
  [43, 9],
  [42, 8],
  [41, 7],
  [39, 6],
  [30, 5],
]

export function markFor(total: number): number {
  for (const [threshold, mark] of MARK_TABLE) {
    if (total >= threshold) return mark
  }
  return 4
}

/** Девять строк ведомости организаторов, дословно. Они лежат в потоке
 *  `qa-a` (см. `scripts/build-roster.mjs`) и служат якорем: всё остальное в
 *  ведомости достроено вокруг них теми же распределениями. */
export const SHEET_ROWS: readonly LedgerRow[] = [
  { id: '171345', homework: 56.5, attendance: 7, engagement: 10, exam: 30, homeworkCount: 9, consent: 'согласен' },
  { id: '172283', homework: 60, attendance: 12, engagement: 20, exam: 30, homeworkCount: 9, consent: 'согласна' },
  { id: '181465', homework: 37.6, attendance: 6, engagement: 0, exam: 30, homeworkCount: 'ю', consent: 'Согласна' },
  { id: '183911', homework: 63.4, attendance: 4, engagement: 0, exam: 30, homeworkCount: 9, consent: 'согласен' },
  { id: '190948', homework: 64, attendance: 5, engagement: 0, exam: 30, homeworkCount: 9, consent: 'согласен' },
  { id: '249662', homework: 53.6, attendance: 7, engagement: 10, exam: 30, homeworkCount: 9, consent: 'Согл' },
  { id: '283814', homework: 66, attendance: 1, engagement: 0, exam: 30, homeworkCount: 9, consent: 'согласен' },
  { id: '313073', homework: 55, attendance: 3, engagement: 0, exam: 30, homeworkCount: 8, consent: 'Согласен' },
  { id: '351347', homework: 59, attendance: 11, engagement: 20, exam: 30, homeworkCount: 9, consent: 'согласен' },
]

/** Итог и оценка из скриншота — то, что должна воспроизвести формула и
 *  таблица порогов. Проверяется скриптом `scripts/build-roster.mjs --check`. */
export const SHEET_EXPECTED: readonly { id: string; total: number; mark: number }[] = [
  { id: '171345', total: 41.25, mark: 7 },
  { id: '172283', total: 44, mark: 9 },
  { id: '181465', total: 30.8, mark: 5 },
  { id: '183911', total: 43.7, mark: 9 },
  { id: '190948', total: 44, mark: 9 },
  { id: '249662', total: 39.8, mark: 6 },
  { id: '283814', total: 45, mark: 10 },
  { id: '313073', total: 39.5, mark: 6 },
  { id: '351347', total: 43.5, mark: 9 },
]

/** Поток, в котором лежат девять настоящих строк. */
export const ANCHOR_STREAM_ID = 'qa-a'
