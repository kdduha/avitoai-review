/** Сборка ведомости: `src/mocks/data/roster.ts`.
 *
 *  Запуск (нужен Node 22+ с раздеванием типов — скрипт импортирует .ts):
 *      node --experimental-strip-types scripts/build-roster.mjs
 *      node --experimental-strip-types scripts/build-roster.mjs --check
 *
 *  Зачем скрипт вообще есть. Раньше ведомость рождалась из `rng()` прямо на
 *  импорте `catalog.ts`: числа были воспроизводимы, но невидимы — чтобы
 *  узнать, что в ведомости, надо было исполнить генератор в голове. Теперь
 *  ведомость лежит файлом, который можно открыть, прочитать и поправить
 *  руками, а скрипт остаётся рядом и объясняет, откуда что взялось.
 *
 *  Что в ведомости настоящее:
 *  - девять строк из `workflow/фиксация результатов.png` — дословно, они
 *    лежат в потоке `qa-a` (см. `ANCHOR_STREAM_ID`);
 *  - формула итога и таблица оценок (`src/mocks/ledger.ts`) — выведены из этих
 *    девяти строк и воспроизводят их без промаха, что и проверяет `--check`;
 *  - размеры трёх групп (Tech QA 49, бизнес-модели 38, антифрод 22) — из
 *    счётчика Stepik.
 *
 *  Что достроено (и почему именно так):
 *  - `homework` — та же шкала, что у организаторов (девять ДЗ, максимум 90) и
 *    тот же диапазон, что у настоящих девяти строк: 35…68 со смещением к верху.
 *    Именно эта колонка задаёт уровень студента: `catalog.ts` берёт из неё
 *    долю `homework / 90` и по ней раздаёт баллы за конкретные задания, так
 *    что ячейки таблицы и ведомость говорят об одном и том же студенте одно и
 *    то же. Сумма ячеек при этом не равна `homework` — у наших программ от
 *    одного до пяти заданий против девяти у организаторов;
 *  - `attendance` — 1…12, как в настоящих строках, равномерно;
 *  - `engagement` — только 0, 10 и 20 в пропорции настоящих строк (6/2/1);
 *  - `exam` — 30 у семи из десяти (в настоящей ведомости 30 у всех девяти,
 *    это максимум), у остальных 24,5…29,5. Потолок, а не середина;
 *  - `consent` — пять настоящих написаний. Род согласия задаёт род имени
 *    студента в `catalog.ts`, а не наоборот;
 *  - `id` — шестизначные, в диапазоне настоящих (170000…360000), уникальные
 *    и отсортированные по возрастанию внутри потока, как в таблице.
 *
 *  Все «случайные» числа берутся из `rng(seed)` с сидом от имени потока:
 *  повторный запуск скрипта даёт побайтово тот же файл.
 */

import { writeFileSync, mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { PROGRAMS } from '../src/mocks/programs.ts'
import { rng } from '../src/mocks/seed.ts'
import {
  ANCHOR_STREAM_ID,
  LEDGER_HOMEWORK_MAX,
  SHEET_EXPECTED,
  SHEET_ROWS,
  ledgerTotal,
  markFor,
} from '../src/mocks/ledger.ts'

const HERE = dirname(fileURLToPath(import.meta.url))
const OUT = resolve(HERE, '../src/mocks/data/roster.ts')

const ID_MIN = 170000
const ID_MAX = 360000

function seedOf(text) {
  let sum = 0
  for (const char of text) sum = (sum * 31 + char.charCodeAt(0)) >>> 0
  return sum
}

/** Сумма за ДЗ на шкале организаторов: 35…68 со смещением к верху, как в
 *  настоящих девяти строках — там 37,6…66 при среднем 57,2, и восемь строк из
 *  девяти лежат выше 53. Форма важна: таблица оценок сгущается на отрезке
 *  39…45 итога, то есть на 54…66 суммы, и от смещения зависит, будет ли в
 *  ведомости разброс оценок или сплошные пятёрки. */
function drawHomework(next) {
  const raw = 35 + Math.pow(next(), 0.35) * 33
  let value = Math.round(raw * 2) / 2
  /* В настоящей таблице половина значений круглые, половина — с десятыми
     (56,5 / 37,6 / 63,4): руками её ведёт человек, а не формула. */
  if (next() < 0.3) value = Math.round((value + (next() - 0.5) * 0.9) * 10) / 10
  return Math.min(LEDGER_HOMEWORK_MAX, Math.max(0, value))
}

function drawEngagement(next) {
  const roll = next()
  return roll < 0.62 ? 0 : roll < 0.88 ? 10 : 20
}

/** 30 — потолок: у всех девяти настоящих строк ровно он. */
function drawExam(next) {
  if (next() < 0.7) return 30
  return 30 - (1 + Math.floor(next() * 11)) * 0.5
}

const CONSENT_MALE = ['согласен', 'согласен', 'согласен', 'согласен', 'Согласен']
const CONSENT_FEMALE = ['согласна', 'согласна', 'согласна', 'Согласна', 'Согласна']

function drawConsent(next) {
  const roll = next()
  if (roll < 0.1) return 'Согл'
  const pool = roll < 0.55 ? CONSENT_MALE : CONSENT_FEMALE
  return pool[Math.floor(next() * pool.length)]
}

function buildStream(streamId, cohort, taken) {
  const next = rng(seedOf(streamId) * 7919)
  const anchors = streamId === ANCHOR_STREAM_ID ? SHEET_ROWS : []
  if (anchors.length > cohort) throw new Error(`поток ${streamId} меньше якорных строк`)

  const anchorById = new Map(anchors.map((row) => [Number(row.id), row]))
  for (const id of anchorById.keys()) taken.add(id)

  const ids = new Set(anchorById.keys())
  let guard = 0
  while (ids.size < cohort) {
    if ((guard += 1) > cohort * 1000) throw new Error(`не хватило id для ${streamId}`)
    const candidate = ID_MIN + Math.floor(next() * (ID_MAX - ID_MIN))
    if (taken.has(candidate)) continue
    taken.add(candidate)
    ids.add(candidate)
  }

  return [...ids]
    .sort((a, b) => a - b)
    .map((id) => {
      const anchor = anchorById.get(id)
      if (anchor) return { ...anchor, real: true }
      return {
        id: String(id),
        homework: drawHomework(next),
        attendance: 1 + Math.floor(next() * 12),
        engagement: drawEngagement(next),
        exam: drawExam(next),
        consent: drawConsent(next),
        real: false,
      }
    })
}

function renderRow({ real, ...row }) {
  const parts = [
    `id: '${row.id}'`,
    `homework: ${row.homework}`,
    `attendance: ${row.attendance}`,
    `engagement: ${row.engagement}`,
    `exam: ${row.exam}`,
  ]
  if (row.homeworkCount !== undefined) {
    parts.push(
      typeof row.homeworkCount === 'number'
        ? `homeworkCount: ${row.homeworkCount}`
        : `homeworkCount: '${row.homeworkCount}'`,
    )
  }
  parts.push(`consent: '${row.consent}'`)
  const tail = real ? ' // из ведомости организаторов, дословно' : ''
  return `    { ${parts.join(', ')} },${tail}`
}

function render(streams) {
  const head = `/** Ведомость потоков. ФАЙЛ СОБИРАЕТСЯ СКРИПТОМ — правки руками возможны, но
 *  следующий запуск \`node --experimental-strip-types scripts/build-roster.mjs\`
 *  их перезапишет. Что здесь настоящее, а что достроено — в шапке скрипта и в
 *  \`src/mocks/ledger.ts\`.
 *
 *  Девять строк потока '${ANCHOR_STREAM_ID}' помечены комментарием: это дословная
 *  выгрузка из \`workflow/фиксация результатов.png\`. Итог и оценку по ним не
 *  хранят — их считает \`catalog.ts\` по формуле организаторов, и они сходятся
 *  со скриншотом до сотых.
 *
 *  Строки внутри потока отсортированы по возрастанию id, как в таблице.
 */

export interface RosterRow {
  /** Обезличенный шестизначный id — он же \`Student.alias\`. */
  id: string
  /** «Итоговая сумма»: сумма за ДЗ на шкале организаторов (максимум 90). */
  homework: number
  /** «Посещаемость», 1…12. В формулу итога не входит. */
  attendance: number
  /** «Вовлеченность»: 0, 10 или 20. */
  engagement: number
  /** «Экзамен», максимум 30. */
  exam: number
  /** «Количество дз» — только там, где значение пришло из ведомости; иначе
   *  считается по сдачам. В одной настоящей строке вместо числа стоит «ю». */
  homeworkCount?: number | string
  /** «Согласие на оценку», свободный текст. */
  consent: string
}

export const ROSTER: Record<string, RosterRow[]> = {`

  const body = Object.entries(streams)
    .map(([streamId, rows]) => `  '${streamId}': [\n${rows.map(renderRow).join('\n')}\n  ],`)
    .join('\n')

  return `${head}\n${body}\n}\n`
}

/** Проверка: формула и таблица порогов обязаны воспроизвести девять настоящих
 *  строк. Заодно показываем, что давали прежние пороги в долях от максимума. */
function check() {
  const expected = new Map(SHEET_EXPECTED.map((row) => [row.id, row]))
  /* Прежнее правило: share = total / maxTotal, maxTotal = сумма максимумов ДЗ
     × 0.5 + 30 × 0.4 + 2; для курса организаторов это 90 × 0.5 + 12 + 2 = 59. */
  const maxTotal = LEDGER_HOMEWORK_MAX * 0.5 + 30 * 0.4 + 2
  const oldMark = (total) => {
    const share = total / maxTotal
    return share >= 0.9 ? 10 : share >= 0.83 ? 9 : share >= 0.76 ? 8 : share >= 0.68 ? 7 : share >= 0.6 ? 6 : share >= 0.5 ? 5 : 4
  }

  console.log('Девять настоящих строк ведомости против формулы и таблицы оценок:')
  console.log('   ID     сумма  экз  вовл |  итог (ожид)  | оценка (ожид) | прежнее правило')
  let bad = 0
  let oldBad = 0
  for (const row of SHEET_ROWS) {
    const want = expected.get(row.id)
    const total = ledgerTotal(row.homework, row.exam, row.engagement)
    const mark = markFor(total)
    const old = oldMark(total)
    const ok = total === want.total && mark === want.mark
    if (!ok) bad += 1
    if (old !== want.mark) oldBad += 1
    console.log(
      `  ${row.id}  ${String(row.homework).padStart(5)}  ${String(row.exam).padStart(3)}  ${String(row.engagement).padStart(4)} | ` +
        `${String(total).padStart(6)} (${String(want.total).padStart(6)}) | ` +
        `${String(mark).padStart(6)} (${String(want.mark).padStart(6)}) | ` +
        `${String(old).padStart(2)}${old === want.mark ? '  ' : ' ✗'} | ${ok ? 'ok' : 'РАСХОЖДЕНИЕ'}`,
    )
  }
  console.log(
    `\nИтог: новая таблица порогов ошиблась на ${bad} строках из ${SHEET_ROWS.length}; ` +
      `прежние пороги в долях — на ${oldBad}.`,
  )
  if (bad) process.exitCode = 1
  return bad === 0
}

function main() {
  const ok = check()
  if (!ok) {
    console.error('\nВедомость не собрана: формула не воспроизводит настоящие строки.')
    return
  }
  if (process.argv.includes('--check')) return

  const taken = new Set()
  const streams = {}
  for (const program of PROGRAMS) {
    for (const suffix of ['a', 'b']) {
      const streamId = `${program.id}-${suffix}`
      streams[streamId] = buildStream(streamId, program.cohort, taken)
    }
  }

  mkdirSync(dirname(OUT), { recursive: true })
  writeFileSync(OUT, render(streams), 'utf8')

  const rows = Object.values(streams).reduce((sum, list) => sum + list.length, 0)
  console.log(`\nСобрано: ${Object.keys(streams).length} потоков, ${rows} строк → ${OUT}`)
}

main()
