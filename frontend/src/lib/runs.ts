/** Прогоны проверки.
 *
 *  Бэкенд без состояния: `/review` принимает ссылку и отдаёт черновик, но
 *  никуда его не кладёт. Пока нет `submissions`, результат живёт здесь, в
 *  памяти вкладки. Отсюда же берётся демо-прогон — он в том же формате, что
 *  ответ сервера, и проходит через тот же адаптер.
 */

import { ApiError, backend, type DetectResponse, type Rubric } from './backend'
import { buildWorkspace, withScore, type Workspace } from './workspace'
import { DEMO_DETECT, DEMO_REVIEW, DEMO_RUN_ID } from '@/mocks/demoRun'
import { DEMO_RUBRIC } from '@/mocks/rubric'

const runs = new Map<string, Workspace>()

function demo(): Workspace {
  const workspace = buildWorkspace(DEMO_RUN_ID, DEMO_REVIEW, DEMO_DETECT, DEMO_RUBRIC)
  return { ...workspace, live: false }
}

runs.set(DEMO_RUN_ID, demo())

export interface StartRunParams {
  link: string
  rubricId: string
  deadlineAt?: string
  studentInternalId?: string
  studentName?: string
  withDetection: boolean
}

export interface StartRunResult {
  workspace: Workspace
  /** Детектор запускается отдельным вызовом и падать вместе с ревью не должен. */
  detectionError: string | null
}

export async function startRun(params: StartRunParams): Promise<StartRunResult> {
  const rubric: Rubric = await backend.rubric(params.rubricId)

  const common = {
    link: params.link,
    source: 'github_pr' as const,
    deadline_at: params.deadlineAt || null,
    student_internal_id: params.studentInternalId || null,
    student_name: params.studentName || null,
  }

  const reviewPromise = backend.review({
    ...common,
    rubric_id: params.rubricId,
    condition_text: '',
    gate_facts: [],
  })
  const detectPromise: Promise<DetectResponse | null> = params.withDetection
    ? backend.detect({ ...common, rubric_id: params.rubricId })
    : Promise.resolve(null)

  const [review, detection] = await Promise.all([
    reviewPromise,
    detectPromise.catch((error: unknown) => error),
  ])

  const detectionFailed = detection instanceof Error
  const detectResponse = detectionFailed ? null : (detection as DetectResponse | null)

  const detectionError = detectionFailed
    ? detection instanceof ApiError
      ? detection.message
      : 'Детектор не отработал'
    : null

  const id = `run-${Date.now().toString(36)}`
  const workspace = { ...buildWorkspace(id, review, detectResponse, rubric), detectionError }
  runs.set(id, workspace)

  return { workspace, detectionError }
}

export function getRun(id: string): Workspace | undefined {
  return runs.get(id)
}

export function setScore(id: string, criterionId: string, score: number): Workspace | undefined {
  const workspace = runs.get(id)
  if (!workspace) return undefined
  const next = withScore(workspace, criterionId, score)
  runs.set(id, next)
  return next
}

export function setSpanVerdict(
  id: string,
  spanId: string,
  verdict: 'pending' | 'confirmed' | 'rejected',
): Workspace | undefined {
  const workspace = runs.get(id)
  if (!workspace?.detection) return workspace
  const next: Workspace = {
    ...workspace,
    detection: {
      ...workspace.detection,
      spans: (workspace.detection.spans ?? []).map((span) =>
        span.id === spanId ? { ...span, reviewer_verdict: verdict } : span,
      ),
    },
  }
  runs.set(id, next)
  return next
}
