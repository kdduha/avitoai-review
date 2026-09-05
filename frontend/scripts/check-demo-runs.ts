/** Проверка записанных прогонов: цитаты и criterion_id.
 *
 *  Ровно то, что до сих пор делалось глазами. Цитата, которой нет в тексте
 *  файла, не ломает сборку — она молча становится `wrong_location` и уезжает на
 *  экран полупрозрачной; `criterion_id`, которого нет в снимке рубрики,
 *  превращается в голый `c9` и «/ 0» в максимуме. Оба промаха видны только тому,
 *  кто открыл прогон и присмотрелся, — поэтому они проверяются здесь.
 *
 *  Запуск (esbuild уже стоит как зависимость vite, отдельного раннера не нужно):
 *
 *      npx esbuild --bundle --platform=node --format=esm \
 *        --alias:@=./src --outfile=/tmp/check-demo-runs.mjs \
 *        scripts/check-demo-runs.ts && node /tmp/check-demo-runs.mjs
 *
 *  Что проверяется по каждому прогону:
 *  1. `criterion_id` каждого вердикта существует в снимке рубрики;
 *  2. каждая цитата имеет статус `valid`, а её первая строка дословно совпадает
 *     со строкой файла после `trim()` — так же, как ищет `locator()`;
 *  3. `start_line` и `end_line` цитаты совпадают с `line_numbers` файла (у
 *     фрагментов из диффа нумерация идёт с пропусками, и арифметика от
 *     `first_line` там врёт);
 *  4. `line_numbers` длиной ровно в число строк текста, `first_line` и
 *     `last_line` сходятся с его концами;
 *  5. `evidence_coverage` совпадает с фактической долей подтверждённых вердиктов;
 *  6. спаны детектора и `locations` Format Gate ссылаются на существующие файлы
 *     и существующие строки.
 */
import type { DetectResponse, ReviewResponse, Rubric } from '@/lib/backend'
import { DEMO_DETECT, DEMO_REVIEW, DEMO_RUN_ID } from '@/mocks/demoRun'
import { DEMO_BACKEND_DETECT, DEMO_BACKEND_ID, DEMO_BACKEND_REVIEW } from '@/mocks/demoBackend'
import { DEMO_SYSDESIGN_DETECT, DEMO_SYSDESIGN_ID, DEMO_SYSDESIGN_REVIEW } from '@/mocks/demoSysdesign'
import { DEMO_QA_DETECT, DEMO_QA_ID, DEMO_QA_REVIEW } from '@/mocks/demoQa'
import { DEMO_FRAUD_DETECT, DEMO_FRAUD_ID, DEMO_FRAUD_REVIEW } from '@/mocks/demoFraud'
import { DEMO_GO_WEAK_DETECT, DEMO_GO_WEAK_ID, DEMO_GO_WEAK_REVIEW } from '@/mocks/demoGoWeak'
import {
  DEMO_RUBRIC,
  DEMO_RUBRIC_BACKEND,
  DEMO_RUBRIC_FRAUD,
  DEMO_RUBRIC_QA,
  DEMO_RUBRIC_SYSDESIGN,
} from '@/mocks/rubric'

type Case = { id: string; review: ReviewResponse; detect: DetectResponse; rubric: Rubric }

const CASES: Case[] = [
  { id: DEMO_RUN_ID, review: DEMO_REVIEW, detect: DEMO_DETECT, rubric: DEMO_RUBRIC },
  { id: DEMO_SYSDESIGN_ID, review: DEMO_SYSDESIGN_REVIEW, detect: DEMO_SYSDESIGN_DETECT, rubric: DEMO_RUBRIC_SYSDESIGN },
  { id: DEMO_BACKEND_ID, review: DEMO_BACKEND_REVIEW, detect: DEMO_BACKEND_DETECT, rubric: DEMO_RUBRIC_BACKEND },
  { id: DEMO_QA_ID, review: DEMO_QA_REVIEW, detect: DEMO_QA_DETECT, rubric: DEMO_RUBRIC_QA },
  { id: DEMO_FRAUD_ID, review: DEMO_FRAUD_REVIEW, detect: DEMO_FRAUD_DETECT, rubric: DEMO_RUBRIC_FRAUD },
  { id: DEMO_GO_WEAK_ID, review: DEMO_GO_WEAK_REVIEW, detect: DEMO_GO_WEAK_DETECT, rubric: DEMO_RUBRIC },
]

let failures = 0
const fail = (run: string, message: string) => {
  failures += 1
  console.log(`  ✗ [${run}] ${message}`)
}

for (const item of CASES) {
  const files = new Map(item.review.files.map((file) => [file.path, file]))
  const ids = new Set((item.rubric.criteria ?? []).map((criterion) => criterion.id))
  let quotes = 0
  let verdicts = 0

  for (const file of item.review.files) {
    const lines = file.text.split('\n')
    if (file.line_numbers.length !== lines.length) {
      fail(item.id, `${file.path}: line_numbers ${file.line_numbers.length} ≠ строк ${lines.length}`)
    }
    if (file.first_line !== file.line_numbers[0]) fail(item.id, `${file.path}: first_line ≠ line_numbers[0]`)
    if (file.last_line !== file.line_numbers[file.line_numbers.length - 1]) {
      fail(item.id, `${file.path}: last_line ≠ последнему line_numbers`)
    }
  }

  for (const verdict of item.review.draft.verdicts ?? []) {
    verdicts += 1
    if (!ids.has(verdict.criterion_id)) {
      fail(item.id, `вердикт ссылается на ${verdict.criterion_id}, которого нет в рубрике ${item.rubric.assignment_id}`)
    }
    for (const evidence of verdict.evidence ?? []) {
      quotes += 1
      const file = files.get(evidence.artifact)
      if (!file) {
        fail(item.id, `${verdict.criterion_id}: файла ${evidence.artifact} нет среди files`)
        continue
      }
      if (evidence.status !== 'valid') {
        fail(item.id, `${verdict.criterion_id}: статус ${evidence.status} у цитаты «${evidence.quote.slice(0, 60)}…»`)
        continue
      }
      const lines = file.text.split('\n')
      const needle = evidence.quote.split('\n')[0].trim()
      if (!needle) {
        fail(item.id, `${verdict.criterion_id}: пустая цитата`)
        continue
      }
      const index = lines.findIndex((line) => line.trim() === needle)
      if (index === -1) {
        fail(item.id, `${verdict.criterion_id}: строки «${needle.slice(0, 60)}…» нет в ${evidence.artifact}`)
        continue
      }
      if (evidence.start_line !== file.line_numbers[index]) {
        fail(item.id, `${verdict.criterion_id}: start_line ${evidence.start_line} ≠ ${file.line_numbers[index]} (${evidence.artifact})`)
      }
      const height = evidence.quote.split('\n').length
      const expectedEnd = file.line_numbers[index + height - 1] ?? file.line_numbers[index] + height - 1
      if (evidence.end_line !== expectedEnd) {
        fail(item.id, `${verdict.criterion_id}: end_line ${evidence.end_line} ≠ ${expectedEnd} (${evidence.artifact})`)
      }
    }
  }

  /* Обязательные минимумы: провал по критерию с `min_score_for_pass` даёт
     незачёт независимо от суммы — `ai/review/aggregate.py::_decide` при
     непустом `failed_minimums` даже не смотрит на порог. Прогон, где балл
     ниже минимума соседствует с `passed: true`, расходится с сервером, и
     заметить это глазами почти невозможно: сумма при этом сходится. Именно
     так и стоял `demo-sysdesign` — 4 из 6 при пороге 4 и `passed: true`,
     хотя c5 набрал 0.5 при обязательном минимуме 1. */
  const minimums = new Map(
    (item.rubric.criteria ?? [])
      .filter((criterion) => criterion.min_score_for_pass != null)
      .map((criterion) => [criterion.id, criterion]),
  )
  const failedMinimums = (item.review.draft.verdicts ?? []).filter((verdict) => {
    const criterion = minimums.get(verdict.criterion_id)
    return criterion != null && verdict.score < (criterion.min_score_for_pass as number)
  })
  /* `failed_criteria` сюда не относится: на бэкенде это «модель не вернула
     вердикт по критерию» (`review/service.py`), а не «балл ниже минимума».
     Критерий с разобранным вердиктом там появиться не должен. */
  if (failedMinimums.length && item.review.draft.passed) {
    fail(
      item.id,
      `passed: true, хотя не набран обязательный минимум: ` +
        failedMinimums
          .map((verdict) => `${verdict.criterion_id} ${verdict.score} < ${minimums.get(verdict.criterion_id)!.min_score_for_pass}`)
          .join('; '),
    )
  }

  const covered = (item.review.draft.verdicts ?? []).filter((verdict) =>
    (verdict.evidence ?? []).some((evidence) => evidence.status === 'valid'),
  ).length
  const coverage = verdicts ? covered / verdicts : 0
  if (Math.abs(coverage - (item.review.draft.evidence_coverage ?? 0)) > 0.001) {
    fail(item.id, `evidence_coverage ${item.review.draft.evidence_coverage} ≠ фактических ${coverage.toFixed(3)}`)
  }

  for (const span of item.detect.report.spans ?? []) {
    const file = files.get(span.artifact)
    if (!file) {
      fail(item.id, `спан ${span.id}: файла ${span.artifact} нет среди files`)
      continue
    }
    for (const line of [span.start_line, span.end_line]) {
      if (line != null && !file.line_numbers.includes(line)) {
        fail(item.id, `спан ${span.id}: строки ${line} нет в line_numbers ${span.artifact}`)
      }
    }
  }

  for (const outcome of item.review.draft.gate?.outcomes ?? []) {
    for (const location of outcome.locations ?? []) {
      const match = /^(.*):(\d+)$/.exec(location)
      if (!match) continue
      const file = files.get(match[1])
      if (!file) {
        fail(item.id, `гейт «${outcome.label}»: файла ${match[1]} нет среди files`)
        continue
      }
      if (!file.line_numbers.includes(Number(match[2]))) {
        fail(item.id, `гейт «${outcome.label}»: строки ${match[2]} нет в ${match[1]}`)
      }
    }
  }

  console.log(
    `${item.id.padEnd(14)} рубрика ${String(item.rubric.assignment_id).padEnd(14)} ` +
      `вердиктов ${String(verdicts).padStart(2)}  цитат ${String(quotes).padStart(2)}  ` +
      `файлов ${String(item.review.files.length).padStart(2)}  спанов ${String((item.detect.report.spans ?? []).length).padStart(2)}`,
  )
}

console.log(failures ? `\nПРОВАЛЕНО: ${failures}` : '\nВсе цитаты valid, все criterion_id на месте.')
process.exit(failures ? 1 : 0)
