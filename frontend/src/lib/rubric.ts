/** Рубрика на стороне редактора.
 *
 *  Здесь три вещи, которых нет в `backend.ts`: повтор серверных проверок,
 *  заготовки пустых сущностей и справочник видов проверок Format Gate.
 *
 *  Про повтор отдельно. Обычно считать на фронте то, что считает сервер, —
 *  ошибка: так появляется правдоподобное, но неверное число рядом с ответом
 *  сервера (ровно поэтому итог работы после правки балла показан
 *  предварительным, а не пересчитан). Здесь случай другой: это не подсчёт, а
 *  список поломок, и он нужен методисту в момент правки, а не после отказа.
 *  Правила скопированы из `backend/src/avito_reviewer/ai/rubric.py`
 *  (`validate_rubric`) вместе с формулировками — чтобы одна и та же поломка не
 *  называлась на экране и в ответе сервера по-разному. **Источник правды —
 *  сервер**: его 422 показывается как есть, даже если здесь проблем не нашлось.
 */

import type { Criterion, FormatCheck, LatePolicy, Rubric } from './backend'
import { plural } from './format'

/** Имя файла рубрики в каталоге — отсюда ограничение на идентификатор.
 *  Экспортируется ради теста, который сверяет его с серверным. */
export const ID_PATTERN = /^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$/

const round4 = (value: number): number => Math.round(value * 1e4) / 1e4

/** Число без хвостовых нулей — как `%g` в сообщениях сервера. */
export const g = (value: number): string => String(round4(value))

/** Максимум, который реально можно набрать. Вес 0 сервер читает как 1
 *  (`c.weight or 1.0`), и здесь должно быть так же, иначе экран объявит
 *  недостижимой шкалу, которую сервер примет. */
export function reachableMax(rubric: Rubric): number {
  return round4(
    (rubric.criteria ?? []).reduce((sum, c) => sum + c.max_score * (c.weight || 1), 0),
  )
}

/** Что не так с рубрикой. Пустой список — сервер должен её принять. */
export function rubricProblems(rubric: Rubric): string[] {
  const problems: string[] = []
  const criteria = rubric.criteria ?? []

  if (!ID_PATTERN.test(rubric.assignment_id)) {
    problems.push(
      `идентификатор '${rubric.assignment_id}' не годится для имени файла: ` +
        `латиница, цифры, точка, дефис и подчёркивание`,
    )
  }
  if (!criteria.length) problems.push('в рубрике нет ни одного критерия')

  const ids = criteria.map((criterion) => criterion.id)
  const duplicates = [...new Set(ids.filter((id) => ids.indexOf(id) !== ids.lastIndexOf(id)))].sort()
  if (duplicates.length) {
    problems.push('повторяющиеся идентификаторы критериев: ' + duplicates.join(', '))
  }

  if (rubric.scale.total_max <= 0) problems.push('максимальный балл должен быть больше нуля')
  if (rubric.scale.step < 0) problems.push('шаг шкалы не может быть отрицательным')

  const threshold = rubric.scale.pass_threshold
  if (threshold != null && threshold > rubric.scale.total_max) {
    problems.push(
      `порог зачёта ${g(threshold)} выше максимума ${g(rubric.scale.total_max)} — зачёт недостижим`,
    )
  }

  for (const criterion of criteria) {
    if (criterion.max_score <= 0) {
      problems.push(`${criterion.id}: максимум критерия должен быть больше нуля`)
    }
    const minimum = criterion.min_score_for_pass
    if (minimum != null && minimum > criterion.max_score) {
      problems.push(
        `${criterion.id}: обязательный минимум ${g(minimum)} выше максимума ` +
          `${g(criterion.max_score)} — критерий провален всегда`,
      )
    }
  }

  // Сумма может не совпадать с максимумом: у критериев бывают веса. А вот
  // недостижимый максимум — это уже поломка шкалы.
  const reachable = reachableMax(rubric)
  if (criteria.length && reachable < rubric.scale.total_max) {
    problems.push(
      `максимум ${g(rubric.scale.total_max)} недостижим: по всем критериям ` +
        `с весами набирается ${g(reachable)}`,
    )
  }
  return problems
}

/** Замечания, которые сервер пропускает, а человек потом расхлёбывает.
 *
 *  Держатся отдельно от `rubricProblems` намеренно: те повторяют правила
 *  сервера и потому блокируют отправку, а эти — вопрос вкуса, и решать его
 *  методисту. Смешать их значило бы либо запретить то, что сервер разрешает,
 *  либо утопить настоящую поломку среди придирок. */
export function rubricAdvisories(rubric: Rubric): string[] {
  const notes: string[] = []

  if (!rubric.title.trim()) {
    notes.push('у рубрики нет названия — в каталоге и в выборе рубрики она будет пустой строкой')
  }
  if (!rubric.course.trim()) {
    notes.push('не назван курс — рубрика ляжет в каталог без принадлежности')
  }

  const untitled = (rubric.criteria ?? []).filter((c) => !c.title.trim()).map((c) => c.id)
  if (untitled.length) {
    notes.push(
      `критерии без названия (${untitled.join(', ')}) — в черновике оценки они останутся без заголовка`,
    )
  }
  return notes
}

/** Поля, которых может не быть в ответе, редактору нужны всегда: иначе каждое
 *  обращение к `criteria` или `params` тащит за собой проверку на `undefined`. */
export function normalizeRubric(rubric: Rubric): Rubric {
  return {
    ...rubric,
    stage: rubric.stage ?? null,
    source_note: rubric.source_note ?? '',
    scale: { ...rubric.scale, pass_threshold: rubric.scale.pass_threshold ?? null },
    late_policy: rubric.late_policy ?? { grace_days: 0, penalty_per_grace_day: 0, after_grace: 'zero' },
    format_gate: (rubric.format_gate ?? []).map((check) => ({
      ...check,
      note: check.note ?? '',
      params: { ...(check.params ?? {}) },
    })),
    criteria: (rubric.criteria ?? []).map((criterion) => ({
      ...criterion,
      description: criterion.description ?? '',
      checks: [...(criterion.checks ?? [])],
      anchors: { ...(criterion.anchors ?? {}) },
    })),
  }
}

export function blankRubric(): Rubric {
  return normalizeRubric({
    assignment_id: '',
    title: '',
    course: '',
    stage: null,
    source_note: '',
    ai_policy: 'declare_required',
    scale: { total_max: 10, pass_threshold: null, step: 1 },
    late_policy: { grace_days: 0, penalty_per_grace_day: 0, after_grace: 'zero' },
    format_gate: [],
    criteria: [],
  })
}

/** Свободный `c1`, `c2`, … — идентификаторы критериев обязаны быть уникальны. */
export function nextCriterionId(rubric: Rubric): string {
  const taken = new Set((rubric.criteria ?? []).map((criterion) => criterion.id))
  for (let index = 1; ; index += 1) {
    const candidate = `c${index}`
    if (!taken.has(candidate)) return candidate
  }
}

export function blankCriterion(rubric: Rubric): Criterion {
  return {
    id: nextCriterionId(rubric),
    title: '',
    max_score: 1,
    min_score_for_pass: null,
    weight: 1,
    description: '',
    checks: [],
    anchors: {},
    evidence_required: true,
    auto_verifiable: false,
    ai_sensitive: false,
  }
}

export function blankCheck(): FormatCheck {
  return { check: 'required_paths', level: 'warning', params: { paths: [] }, note: '' }
}

/* ------------------------------------------------------------------------ */

export type ParamKind = 'text' | 'number' | 'list'

export interface ParamField {
  key: string
  label: string
  kind: ParamKind
  hint?: string
}

export interface GateKind {
  check: string
  label: string
  /** Гейт умеет исполнять эту проверку. Остальные не исчезают — уходят
   *  ревьюеру как `inconclusive`, и методист должен знать об этом до того, как
   *  положит проверку в рубрику, а не после первой сдачи. */
  executed: boolean
  hint: string
  params: ParamField[]
}

const PATTERN_FIELD: ParamField = {
  key: 'pattern',
  label: 'Регулярное выражение',
  kind: 'text',
  hint: 'синтаксис Python `re`',
}
const IN_FIELD: ParamField = {
  key: 'in',
  label: 'Только в файлах с расширением',
  kind: 'list',
  hint: 'по одному в строке, например .py',
}

/** Виды проверок, которые понимает `ai/gate.py`. Список закрытый, но не
 *  запретительный: свой `check` завести можно, он просто уйдёт человеку. */
export const GATE_KINDS: GateKind[] = [
  {
    check: 'required_paths',
    label: 'Требуемые пути',
    executed: true,
    hint: 'работа обязана содержать эти файлы или каталоги',
    params: [{ key: 'paths', label: 'Пути', kind: 'list', hint: 'по одному в строке' }],
  },
  {
    check: 'forbidden_paths',
    label: 'Запрещённые пути',
    executed: true,
    hint: 'этих файлов в работе быть не должно — например закоммиченный .env',
    params: [{ key: 'paths', label: 'Пути', kind: 'list', hint: 'по одному в строке' }],
  },
  {
    check: 'code_contains',
    label: 'В работе есть',
    executed: true,
    hint: 'дословное требование условия, которое видно по тексту работы',
    params: [PATTERN_FIELD, { key: 'expected', label: 'То же словами', kind: 'text' }, IN_FIELD],
  },
  {
    check: 'code_absent',
    label: 'В работе не должно быть',
    executed: true,
    hint: 'обратная проверка: совпадение означает провал',
    params: [PATTERN_FIELD, IN_FIELD],
  },
  {
    check: 'token_budget',
    label: 'Объём работы',
    executed: true,
    hint: 'ограничение объёма из условия: страниц в git нет, поэтому считаем токены',
    params: [{ key: 'max_tokens', label: 'Потолок в токенах', kind: 'number' }],
  },
  {
    check: 'revision_history_visible',
    label: 'Видна история изменений',
    executed: false,
    hint: 'требование условия для сдачи через Google Docs; в git-канале не исполняется',
    params: [],
  },
  {
    check: 'font',
    label: 'Шрифт и кегль',
    executed: false,
    hint: 'живёт в .docx и Google Docs, а не в репозитории',
    params: [
      { key: 'family', label: 'Гарнитура', kind: 'text' },
      { key: 'size_pt', label: 'Кегль', kind: 'number' },
    ],
  },
]

export const gateKind = (check: string): GateKind | undefined =>
  GATE_KINDS.find((kind) => kind.check === check)

/* ------------------------------------------------------------------------ */

/** Правило просрочки записано в рубрике числами; человеку нужно предложение.
 *  Живёт здесь, а не на экране рубрик, потому что редактор показывает ту же
 *  фразу предпросмотром: два перевода одного правила разошлись бы. */
export function lateInWords(policy: LatePolicy | undefined): string {
  if (!policy) return 'штраф за просрочку не задан'
  const grace = policy.grace_days ?? 0
  const penalty = policy.penalty_per_grace_day ?? 0
  if (!grace && !penalty) return 'штрафа за просрочку нет'

  const head = grace
    ? `досдача в течение ${grace} ${plural(grace, 'дня', 'дней', 'дней')} — минус ${penalty} ${plural(penalty, 'балл', 'балла', 'баллов')} за день`
    : `минус ${penalty} за каждый день просрочки`
  return head + (policy.after_grace === 'zero' ? ', позже — 0 баллов' : ', дальше штраф растёт')
}

/** У части проверок методист пишет `label`, у части — нет; голое число из
 *  `params` в списке нечитаемо, поэтому у каждого вида проверки есть своя
 *  формулировка. */
export function checkLabel(check: FormatCheck): string {
  const params = (check.params ?? {}) as Record<string, unknown>
  if (typeof params.label === 'string' && params.label) return params.label

  switch (check.check) {
    case 'token_budget':
      return `Объём работы — не больше ${params.max_tokens} токенов`
    case 'required_paths':
      return `Требуемые пути: ${[params.paths].flat().join(', ')}`
    case 'code_absent':
      return `В работе не должно быть: ${params.pattern}`
    default:
      return typeof params.expected === 'string' ? params.expected : check.check
  }
}
