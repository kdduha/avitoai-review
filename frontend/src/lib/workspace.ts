/** Вид работы для трёх панелей.
 *
 *  Собирается из ответов бэкенда, потому что ни один из них сам по себе не
 *  полон: вердикт знает балл, но не знает названия критерия и его максимума —
 *  это рубрика; текст файла может начинаться не с первой строки — это
 *  `first_line`; спаны детектора живут в отдельном ответе. Сведение в одном
 *  месте избавляет компоненты от знания о том, кто где хранится.
 */

import type {
  ArtifactText,
  CriterionVerdict,
  DetectionReport,
  Evidence,
  GateReport,
  ReviewDraft,
  ReviewResponse,
  Rubric,
  SubmissionBundle,
  SubmissionDetail,
  SubmissionStatus,
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
  /** `null` для демо-прогонов и для офлайн-разбора — им нечего PATCH'ить. */
  submissionId: string | null
  /** Сразу после `/review` всегда `draft_ready` — открытая из очереди сдача
   *  может прийти уже `approved`, и панель должна знать это до первого клика,
   *  а не узнавать из 409 на `POST .../review/approve`. */
  status: SubmissionStatus
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
  /** Детектор запускался, но не отработал. */
  detectionError: string | null
  partialArtifacts: string[]
  evidenceCoverage: number
  tokensIn: number
  tokensOut: number
  costRub: number
  detection: DetectionReport | null
}

export function prLabel(url: string): string {
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

function mapVerdicts(verdicts: CriterionVerdict[] | undefined, rubric: Rubric): WorkspaceVerdict[] {
  const criteria = new Map((rubric.criteria ?? []).map((criterion) => [criterion.id, criterion]))
  return (verdicts ?? []).map((verdict) => {
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
}

function assemble(
  id: string,
  submissionId: string | null,
  status: SubmissionStatus,
  bundle: SubmissionBundle,
  files: ArtifactText[],
  draft: ReviewDraft,
  detection: DetectionReport | null,
  rubric: Rubric,
): Workspace {
  const marked = new Set<string>()
  for (const verdict of draft.verdicts ?? []) {
    for (const item of verdict.evidence ?? []) if (item.status === 'valid') marked.add(item.artifact)
  }
  for (const span of detection?.spans ?? []) marked.add(span.artifact)

  return {
    id,
    submissionId,
    status,
    live: true,
    link: bundle.origin_url,
    prLabel: prLabel(bundle.origin_url),
    assignmentTitle: draft.rubric_title || rubric.title,
    course: rubric.course,
    studentLabel: bundle.student_ref.internal_id,
    submittedAt: bundle.submitted_at,
    deadlineAt: bundle.deadline_at ?? null,
    files: files.map((text) => toFile(text, marked)),
    verdicts: mapVerdicts(draft.verdicts, rubric),
    gate: draft.gate ?? null,
    rawScore: draft.raw_score ?? 0,
    score: draft.score ?? 0,
    maxScore: draft.max_score ?? 0,
    scoreStep: rubric.scale?.step || 1,
    passed: draft.passed ?? false,
    passExplanation: draft.pass_explanation ?? '',
    lateExplanation: draft.late_explanation ?? '',
    needsHumanAttention: draft.needs_human_attention ?? false,
    attentionReasons: draft.attention_reasons ?? [],
    edited: false,
    detectionError: null,
    partialArtifacts: draft.partial_artifacts ?? [],
    evidenceCoverage: draft.evidence_coverage ?? 0,
    tokensIn: (draft.tokens_in ?? 0) + (detection?.tokens_in ?? 0),
    tokensOut: (draft.tokens_out ?? 0) + (detection?.tokens_out ?? 0),
    costRub: (draft.cost_rub ?? 0) + (detection?.cost_rub ?? 0),
    detection,
  }
}

export function buildWorkspace(
  id: string,
  review: ReviewResponse,
  detection: DetectionReport | null,
  rubric: Rubric,
): Workspace {
  return assemble(id, review.submission_id ?? null, 'draft_ready', review.bundle, review.files, review.draft, detection, rubric)
}

/** Открытие сдачи из очереди/списка — `GET /submissions/{id}` вместо ответа
 *  `/review`, которого для неё никто не звал в этой вкладке. Рубрику берём из
 *  `detail.rubric` (снимок на момент разбора), а не из каталога: если методист
 *  успел поправить JSON, старые сдачи не должны молча пересчитаться по другим
 *  весам. */
export function buildWorkspaceFromDetail(detail: SubmissionDetail): Workspace {
  return assemble(
    detail.id, detail.id, detail.status, detail.bundle, detail.files, detail.draft, detail.detection, detail.rubric,
  )
}

/** Правка балла без сервера — только для демо- и офлайн-прогонов
 *  (`submissionId === null`, PATCH'ить нечего).
 *
 *  Итог здесь не пересчитывается по-настоящему: порядок операций у
 *  агрегатора не сводится к сумме — есть веса, шаг шкалы, обязательные
 *  минимумы и штраф за просрочку, причём два последних могут обнулить работу
 *  целиком. Досчитать это на фронте значит показать правдоподобное, но
 *  неверное число рядом с объяснением сервера, которое ему противоречит.
 *  Поэтому здесь только сумма по критериям и пометка `edited` — панель
 *  показывает её как предварительную. Живой прогон использует
 *  `withPatchedDraft`: тот берёт пересчитанный итог с сервера.
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

/** Правка балла на живом прогоне: сервер уже пересчитал итог
 *  (`PATCH /submissions/{id}/review`) — здесь только слияние его ответа с уже
 *  собранным видом. Рубрика не нужна: название, максимум, вес, проверочные
 *  пункты и обязательный минимум критерия патч не меняет, обновляются только
 *  счёт, вердикт и вытекающие из них поля — их и берём из ответа сервера. */
export function withPatchedDraft(workspace: Workspace, draft: ReviewDraft): Workspace {
  const byId = new Map((draft.verdicts ?? []).map((verdict) => [verdict.criterion_id, verdict]))

  return {
    ...workspace,
    verdicts: workspace.verdicts.map((verdict) => {
      const patched = byId.get(verdict.criterionId)
      if (!patched) return verdict
      return {
        ...verdict,
        score: patched.score,
        confidence: patched.confidence ?? verdict.confidence,
        verdict: patched.verdict,
        studentFeedback: patched.student_feedback ?? verdict.studentFeedback,
        improvementHint: patched.improvement_hint ?? verdict.improvementHint,
        needsHumanAttention: patched.needs_human_attention ?? false,
        attentionReason: patched.attention_reason ?? '',
        edited: false,
      }
    }),
    rawScore: draft.raw_score ?? 0,
    score: draft.score ?? 0,
    passed: draft.passed ?? false,
    passExplanation: draft.pass_explanation ?? '',
    lateExplanation: draft.late_explanation ?? '',
    needsHumanAttention: draft.needs_human_attention ?? false,
    attentionReasons: draft.attention_reasons ?? [],
    edited: false,
  }
}

/** Вердикт ревьюера по спану ГенИИ, пришедший с сервера (advisory — на балл
 *  не влияет, только помечает спан подтверждённым/отклонённым). */
export function withDetectionReport(workspace: Workspace, detection: DetectionReport): Workspace {
  return { ...workspace, detection }
}
