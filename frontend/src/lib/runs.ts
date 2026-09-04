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

export { DEMO_RUN_ID }
import { DEMO_SYSDESIGN_DETECT, DEMO_SYSDESIGN_ID, DEMO_SYSDESIGN_REVIEW } from '@/mocks/demoSysdesign'
import { DEMO_RUBRIC, DEMO_RUBRIC_SYSDESIGN } from '@/mocks/rubric'

const runs = new Map<string, Workspace>()

function demo(): Workspace {
  return { ...buildWorkspace(DEMO_RUN_ID, DEMO_REVIEW, DEMO_DETECT, DEMO_RUBRIC), live: false }
}

function demoSysdesign(): Workspace {
  return {
    ...buildWorkspace(DEMO_SYSDESIGN_ID, DEMO_SYSDESIGN_REVIEW, DEMO_SYSDESIGN_DETECT, DEMO_RUBRIC_SYSDESIGN),
    live: false,
  }
}

runs.set(DEMO_RUN_ID, demo())
runs.set(DEMO_SYSDESIGN_ID, demoSysdesign())

/** Демо-разбор есть только там, где есть рубрика: показывать разбор работы по
 *  Tech QA против рубрики по Go — хуже, чем не показывать ничего. */
const DEMO_BY_COURSE: Record<string, string> = {
  go: DEMO_RUN_ID,
  'system-design': DEMO_SYSDESIGN_ID,
}

/** Записанные ветки разговора — свои у каждого демо-прогона. */
const DEMO_THREADS: Record<string, { id: string; author: 'human' | 'ai'; text: string }[]> = {
  [DEMO_RUN_ID]: [
    { id: 'm1', author: 'human', text: 'Обоснуй балл по чистоте кода, посмотри ещё README.' },
    {
      id: 'm2',
      author: 'ai',
      text:
        'В README описано чтение .env, которого в коде нет: config.Load ходит только в os.Getenv. Плюс ошибка w.Write не обработана в обоих хендлерах. Оба замечания по одному критерию, поэтому 1 из 2 выглядит справедливо; поднимать не предлагаю.',
    },
  ],
  [DEMO_SYSDESIGN_ID]: [
    {
      id: 'm1',
      author: 'human',
      text: 'Работа встала ровно на пороге. Проверь, не занижен ли балл за модель данных.',
    },
    {
      id: 'm2',
      author: 'ai',
      text:
        'В разделе 5 названы три сущности и одна связь, полей и ключей нет, обоснования выбора тоже. Критерий требует описанную модель и её обоснование — по нему ноль обоснован. Ближе к границе другой критерий: контракты заданы без ошибочных ответов, и там стоит 0.5 из 0.5. Если поднимать, то честнее пересмотреть его, а не модель данных.',
    },
  ],
}

/** Демо-прогон, собранный против этой рубрики. */
const DEMO_BY_RUBRIC: Record<string, string> = {
  'go-task1': DEMO_RUN_ID,
  'sysdesign-lab1': DEMO_SYSDESIGN_ID,
}

export function demoRunForRubric(rubricId: string | undefined): string {
  return (rubricId && DEMO_BY_RUBRIC[rubricId]) ?? DEMO_RUN_ID
}

export function demoThread(runId: string) {
  return DEMO_THREADS[runId] ?? []
}

export function demoRunForCourse(courseId: string | undefined): string | null {
  return (courseId && DEMO_BY_COURSE[courseId]) ?? null
}

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
