/** Вид работы для трёх панелей.
 *
 *  Собирается из ответа бэкенда и рубрики, потому что ни один из них сам по
 *  себе не полон: вердикт знает балл, но не знает названия критерия и его
 *  максимума — это рубрика; текст файла может начинаться не с первой строки —
 *  это `first_line`. Сведение в одном месте избавляет компоненты от знания о
 *  том, кто где хранится.
 */

import type {
  ArtifactText,
  DetectionReport,
  Evidence,
  GateReport,
  ReviewResponse,
  Rubric,
} from './backend'

export interface WorkspaceFile {
  path: string
  lang: string | null
  text: string
  /** Номер каждой строки в полной версии файла.
   *
   *  У фрагмента из диффа номера идут с пропусками (1–4, затем 119–122), и
   *  нумеровать вьювером от первой строки нельзя: цитата на 120-ю строку
   *  уехала бы на четвёртую. */
  lineNumbers: number[]
  partial: boolean
  origin: string
  changedLines: string
  hasFindings: boolean
}

export interface WorkspaceVerdict {
  criterionId: string
  title: string
  maxScore: number
  /** Вес критерия: сервер складывает `score × weight`, и сумма на экране
   *  обязана считаться так же, иначе поднятие балла может её уронить. */
  weight: number
  /** Проверочные пункты из рубрики — то, что модель обязана была разобрать.
   *  Рядом с вердиктом они превращают «модель сказала 1 из 2» в проверяемое
   *  утверждение. */
  checks: string[]
  /** Провал по обязательному минимуму — незачёт по работе целиком, а не
   *  просто потерянные баллы. */
  minScoreForPass: number | null
  aiSensitive: boolean
  score: number
  confidence: number
  verdict: string
  evidence: Evidence[]
  studentFeedback: string
  improvementHint: string
  needsHumanAttention: boolean
  attentionReason: string
  edited: boolean
}

export interface Workspace {
  id: string
  live: boolean
  link: string
  prLabel: string
  assignmentTitle: string
  course: string
  studentLabel: string
  submittedAt: string | null
  deadlineAt: string | null
  files: WorkspaceFile[]
  verdicts: WorkspaceVerdict[]
  gate: GateReport | null
  rawScore: number
  score: number
  maxScore: number
  /** Шаг шкалы задания: правка балла ходит по нему, а не по единице. */
  scoreStep: number
  passed: boolean
  passExplanation: string
  lateExplanation: string
  needsHumanAttention: boolean
  attentionReasons: string[]
  /** Куратор правил баллы: итог на экране больше не тот, что посчитал сервер. */
  edited: boolean
  partialArtifacts: string[]
  evidenceCoverage: number
  tokensIn: number
  tokensOut: number
  costRub: number
  detection: DetectionReport | null
}

function prLabel(url: string): string {
  const match = url.match(/\/pull\/(\d+)/)
  return match ? `PR #${match[1]}` : 'Сдача'
}

function toFile(text: ArtifactText, marked: Set<string>): WorkspaceFile {
  return {
    path: text.path,
    lang: text.lang,
    text: text.text,
    lineNumbers:
      text.line_numbers?.length === text.text.split('\n').length
        ? text.line_numbers
        : text.text.split('\n').map((_, index) => (text.first_line || 1) + index),
    partial: text.partial,
    origin: text.origin,
    changedLines: text.changed_lines,
    hasFindings: marked.has(text.path),
  }
}

export function buildWorkspace(id: string, review: ReviewResponse, rubric: Rubric): Workspace {
  const criteria = new Map((rubric.criteria ?? []).map((criterion) => [criterion.id, criterion]))
  /* Детектор приезжает внутри ответа ревью: один ingest на оба разбора, и
     спаны описывают ту же ревизию, что и цитаты черновика. `null` значит
     «не просили» — сбой приходит отчётом с причиной, а не отсутствием отчёта. */
  const report = review.detection ?? null

  const marked = new Set<string>()
  for (const verdict of review.draft.verdicts ?? []) {
    for (const item of verdict.evidence ?? []) if (item.status === 'valid') marked.add(item.artifact)
  }
  for (const span of report?.spans ?? []) marked.add(span.artifact)

  const verdicts: WorkspaceVerdict[] = (review.draft.verdicts ?? []).map((verdict) => {
    const criterion = criteria.get(verdict.criterion_id)
    return {
      criterionId: verdict.criterion_id,
      title: criterion?.title ?? verdict.criterion_id,
      maxScore: criterion?.max_score ?? 0,
      weight: criterion?.weight || 1,
      checks: criterion?.checks ?? [],
      minScoreForPass: criterion?.min_score_for_pass ?? null,
      aiSensitive: criterion?.ai_sensitive ?? false,
      score: verdict.score,
      confidence: verdict.confidence ?? 0.5,
      verdict: verdict.verdict,
      evidence: verdict.evidence ?? [],
      studentFeedback: verdict.student_feedback ?? '',
      improvementHint: verdict.improvement_hint ?? '',
      needsHumanAttention: verdict.needs_human_attention ?? false,
      attentionReason: verdict.attention_reason ?? '',
      edited: false,
    }
  })

  const bundle = review.bundle

  return {
    id,
    live: true,
    link: bundle.origin_url,
    prLabel: prLabel(bundle.origin_url),
    assignmentTitle: review.draft.rubric_title || rubric.title,
    course: rubric.course,
    studentLabel: bundle.student_ref.internal_id,
    submittedAt: bundle.submitted_at,
    deadlineAt: bundle.deadline_at ?? null,
    files: review.files.map((text) => toFile(text, marked)),
    verdicts,
    gate: review.draft.gate ?? null,
    rawScore: review.draft.raw_score ?? 0,
    score: review.draft.score ?? 0,
    maxScore: review.draft.max_score ?? 0,
    scoreStep: rubric.scale?.step || 1,
    passed: review.draft.passed ?? false,
    passExplanation: review.draft.pass_explanation ?? '',
    lateExplanation: review.draft.late_explanation ?? '',
    needsHumanAttention: review.draft.needs_human_attention ?? false,
    attentionReasons: review.draft.attention_reasons ?? [],
    edited: false,
    partialArtifacts: review.draft.partial_artifacts ?? [],
    evidenceCoverage: review.draft.evidence_coverage ?? 0,
    tokensIn: (review.draft.tokens_in ?? 0) + (report?.tokens_in ?? 0),
    tokensOut: (review.draft.tokens_out ?? 0) + (report?.tokens_out ?? 0),
    costRub: (review.draft.cost_rub ?? 0) + (report?.cost_rub ?? 0),
    detection: report,
  }
}

/** Правка балла куратором.
 *
 *  Итог сознательно не пересчитывается: порядок операций у агрегатора не
 *  сводится к сумме — есть веса, шаг шкалы, обязательные минимумы и штраф за
 *  просрочку, причём два последних могут обнулить работу целиком. Досчитать
 *  это на фронте значит показать правдоподобное, но неверное число рядом с
 *  объяснением сервера, которое ему противоречит. Поэтому здесь только сумма
 *  по критериям и пометка `edited`: панель показывает её как предварительную и
 *  не выносит вердикт о зачёте, пока не появится `PATCH /review`.
 */
export function withScore(workspace: Workspace, criterionId: string, score: number): Workspace {
  const verdicts = workspace.verdicts.map((verdict) =>
    verdict.criterionId === criterionId ? { ...verdict, score, edited: true } : verdict,
  )

  return {
    ...workspace,
    verdicts,
    edited: true,
    rawScore: verdicts.reduce((sum, verdict) => sum + verdict.score * verdict.weight, 0),
  }
}
