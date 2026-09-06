/** Прогоны проверки.
 *
 *  `/review` сохраняет `Submission` на бэкенде, но локальный кэш остаётся:
 *  `ReviewPage` держит рабочий вид (файлы, подсветку цитаты) и без бэкенда, а
 *  демо-прогоны живут только в нём. Живая правка балла и вердикта детектора
 *  уходит на сервер и уже оттуда обновляет кэш.
 *
 *  Ревью и детектор — один вызов (`with_detection`), не два: отдельный
 *  `/detect` тянул сдачу заново, и спаны могли описывать другую ревизию, чем
 *  цитаты черновика.
 */

import { backend, type Rubric } from './backend'
import {
  buildWorkspace,
  buildWorkspaceFromDetail,
  withDetectionReport,
  withPatchedDraft,
  withScore,
  type Workspace,
} from './workspace'
import { DEMO_DETECT, DEMO_REVIEW, DEMO_RUN_ID } from '@/mocks/demoRun'

export { DEMO_RUN_ID }
import { DEMO_BACKEND_DETECT, DEMO_BACKEND_ID, DEMO_BACKEND_REVIEW } from '@/mocks/demoBackend'
import { DEMO_SYSDESIGN_DETECT, DEMO_SYSDESIGN_ID, DEMO_SYSDESIGN_REVIEW } from '@/mocks/demoSysdesign'
import { DEMO_FRAUD_DETECT, DEMO_FRAUD_ID, DEMO_FRAUD_REVIEW } from '@/mocks/demoFraud'
import { DEMO_GO_WEAK_DETECT, DEMO_GO_WEAK_ID, DEMO_GO_WEAK_REVIEW } from '@/mocks/demoGoWeak'
import { DEMO_QA_DETECT, DEMO_QA_ID, DEMO_QA_REVIEW } from '@/mocks/demoQa'
import {
  DEMO_RUBRIC,
  DEMO_RUBRIC_BACKEND,
  DEMO_RUBRIC_FRAUD,
  DEMO_RUBRIC_QA,
  DEMO_RUBRIC_SYSDESIGN,
} from '@/mocks/rubric'

const runs = new Map<string, Workspace>()

// `submissionId: null` обязателен: `submission_id` в записанных ответах стоит
// только ради типа, и без null правка балла ушла бы PATCH'ем на несуществующую
// сдачу.
function demo(): Workspace {
  return { ...buildWorkspace(DEMO_RUN_ID, DEMO_REVIEW, DEMO_DETECT.report, DEMO_RUBRIC), live: false, submissionId: null }
}

function demoSysdesign(): Workspace {
  return {
    ...buildWorkspace(
      DEMO_SYSDESIGN_ID, DEMO_SYSDESIGN_REVIEW, DEMO_SYSDESIGN_DETECT.report, DEMO_RUBRIC_SYSDESIGN,
    ),
    live: false,
    submissionId: null,
  }
}

function demoBackend(): Workspace {
  return {
    ...buildWorkspace(DEMO_BACKEND_ID, DEMO_BACKEND_REVIEW, DEMO_BACKEND_DETECT.report, DEMO_RUBRIC_BACKEND),
    live: false,
    submissionId: null,
  }
}

/** Слабое решение по Go — та же рубрика, что у `demo`, но работа заметно хуже:
 *  на демо видно, что разбор различает уровни, а не хвалит всё подряд. */
function demoGoWeak(): Workspace {
  return {
    ...buildWorkspace(DEMO_GO_WEAK_ID, DEMO_GO_WEAK_REVIEW, DEMO_GO_WEAK_DETECT.report, DEMO_RUBRIC),
    live: false,
    submissionId: null,
  }
}

function demoQa(): Workspace {
  return {
    ...buildWorkspace(DEMO_QA_ID, DEMO_QA_REVIEW, DEMO_QA_DETECT.report, DEMO_RUBRIC_QA),
    live: false,
    submissionId: null,
  }
}

function demoFraud(): Workspace {
  return {
    ...buildWorkspace(DEMO_FRAUD_ID, DEMO_FRAUD_REVIEW, DEMO_FRAUD_DETECT.report, DEMO_RUBRIC_FRAUD),
    live: false,
    submissionId: null,
  }
}

runs.set(DEMO_RUN_ID, demo())
runs.set(DEMO_GO_WEAK_ID, demoGoWeak())
runs.set(DEMO_QA_ID, demoQa())
runs.set(DEMO_FRAUD_ID, demoFraud())
runs.set(DEMO_SYSDESIGN_ID, demoSysdesign())
runs.set(DEMO_BACKEND_ID, demoBackend())

/** Демо-разбор есть только там, где есть рубрика: показывать разбор работы по
 *  Tech QA против рубрики по Go — хуже, чем не показывать ничего. */
const DEMO_BY_COURSE: Record<string, string> = {
  go: DEMO_RUN_ID,
  'system-design': DEMO_SYSDESIGN_ID,
  backend: DEMO_BACKEND_ID,
  qa: DEMO_QA_ID,
  fraud: DEMO_FRAUD_ID,
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
  [DEMO_BACKEND_ID]: [
    {
      id: 'm1',
      author: 'human',
      text: 'После штрафа не хватает половины балла. Есть за что добавить?',
    },
    {
      id: 'm2',
      author: 'ai',
      text:
        'Ближайший кандидат — «Прохождение тестов»: там 0.5 из-за одного упавшего теста, где ожидание 400 разошлось с 422 от pydantic. Это ошибка в тесте, а не в сервисе. По букве рубрики градация 0.5 стоит верно; поднимать до 1 — уже решение ревьюера о том, считать ли расхождение существенным.',
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
  'backend-task1': DEMO_BACKEND_ID,
  'qa-task1': DEMO_QA_ID,
  'fraud-task1': DEMO_FRAUD_ID,
}

/** Записанный разбор именно этой рубрики — или `null`.
 *
 *  При промахе — `null`, а не разбор по Go: чужой разбор выглядит правдоподобно
 *  и неверен. Записанный разбор есть у пяти рубрик из пятнадцати. */
export function demoRunForRubric(rubricId: string | undefined): string | null {
  return (rubricId && DEMO_BY_RUBRIC[rubricId]) ?? null
}

export function demoThread(runId: string) {
  return DEMO_THREADS[runId] ?? []
}

export function demoRunForCourse(courseId: string | undefined): string | null {
  return (courseId && DEMO_BY_COURSE[courseId]) ?? null
}

export interface StartRunParams {
  link: string
  /** Ключ рубрики — нужен здесь и тогда, когда сервер выбирает её сам:
   *  адаптер строит рабочее место против снимка рубрики. */
  rubricId: string
  /** Задание потока. Задано — рубрику и срок берёт сервер, а не форма:
   *  срок принадлежит заданию, и ревьюер его не вводит. */
  assignmentId?: string
  deadlineAt?: string
  studentInternalId?: string
  studentName?: string
  withDetection: boolean
}

export interface StartRunResult {
  workspace: Workspace
}

export async function startRun(params: StartRunParams): Promise<StartRunResult> {
  const rubric: Rubric = await backend.rubric(params.rubricId)

  // С заданием рубрика и срок не передаются вовсе: сервер отвергает запрос,
  // где названо и задание, и рубрика, — это работа, оценённая не по той
  // рубрике, которую поток выдал.
  const review = await backend.review({
    link: params.link,
    source: 'github_pr' as const,
    student_internal_id: params.studentInternalId || null,
    student_name: params.studentName || null,
    condition_text: '',
    gate_facts: [],
    with_detection: params.withDetection,
    ...(params.assignmentId
      ? { assignment_id: params.assignmentId }
      : { rubric_id: params.rubricId, deadline_at: params.deadlineAt || null }),
  })

  const id = `run-${Date.now().toString(36)}`
  const workspace: Workspace = {
    ...buildWorkspace(id, review, review.detection ?? null, rubric),
    detectionError:
      params.withDetection && !review.detection
        ? 'Детектор не отработал — черновик ревью получен, сигнал ГенИИ недоступен'
        : null,
  }
  runs.set(id, workspace)

  return { workspace }
}

export function getRun(id: string): Workspace | undefined {
  return runs.get(id)
}

/** Открытие сдачи, которую эта вкладка сама не запускала — из очереди или по
 *  прямой ссылке `/review/{submission_id}`. `getRun` синхронно бьёт только по
 *  локальному кэшу; здесь — настоящий `GET /submissions/{id}`, и результат
 *  кладётся в тот же кэш, так что повторное открытие и правки идут по уже
 *  привычному пути (`setScore`/`approveRun`/`setSpanVerdict`). */
export async function loadSubmission(id: string): Promise<Workspace> {
  const cached = runs.get(id)
  if (cached) return cached
  const detail = await backend.submission(id)
  const workspace = buildWorkspaceFromDetail(detail)
  runs.set(id, workspace)
  return workspace
}

/** Правка балла. На живом прогоне (`submissionId` есть) уходит на сервер и
 *  возвращает пересчитанный им итог; для демо и офлайн-разбора считается
 *  локально и остаётся предварительной пометкой `edited`. */
export async function setScore(id: string, criterionId: string, score: number): Promise<Workspace | undefined> {
  const workspace = runs.get(id)
  if (!workspace) return undefined

  const next = workspace.submissionId
    ? withPatchedDraft(
        workspace,
        await backend.patchReview(workspace.submissionId, { patches: [{ criterion_id: criterionId, score }] }),
      )
    : withScore(workspace, criterionId, score)

  runs.set(id, next)
  return next
}

export async function setSpanVerdict(
  id: string,
  spanId: string,
  verdict: 'pending' | 'confirmed' | 'rejected',
): Promise<Workspace | undefined> {
  const workspace = runs.get(id)
  if (!workspace?.detection) return workspace

  let next: Workspace
  if (workspace.submissionId && verdict !== 'pending') {
    const detection = await backend.setDetectionVerdict(workspace.submissionId, spanId, { verdict })
    next = withDetectionReport(workspace, detection)
  } else {
    next = withDetectionReport(workspace, {
      ...workspace.detection,
      spans: (workspace.detection.spans ?? []).map((span) =>
        span.id === spanId ? { ...span, reviewer_verdict: verdict } : span,
      ),
    })
  }

  runs.set(id, next)
  return next
}

/** Утверждение черновика. На демо-прогоне утверждать нечего — без
 *  `submissionId` экран в этот путь не пускает.
 *
 *  Новый статус кладётся в кэш из ответа сервера: иначе `ReviewPage` при
 *  повторном открытии из очереди предлагает утвердить уже утверждённое. */
export async function approveRun(id: string): Promise<Workspace | undefined> {
  const workspace = runs.get(id)
  if (!workspace?.submissionId) return workspace

  const summary = await backend.approveReview(workspace.submissionId)
  const next: Workspace = { ...workspace, status: summary.status }
  runs.set(id, next)
  return next
}
