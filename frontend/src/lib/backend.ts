/** Клиент бэкенда. Типы не пишутся руками — они сгенерированы из OpenAPI
 *  (`npm run gen:api`), поэтому расхождение с сервером ловится компилятором,
 *  а не на демо. */

import type { components } from './backend.d'

type S = components['schemas']

export type SubmissionBundle = S['SubmissionBundle']
export type ArtifactText = S['ArtifactTextOut']
export type ReviewDraft = S['ReviewDraft']
export type ReviewSummary = S['ReviewSummary']
export type CriterionVerdict = S['CriterionVerdict']
export type Evidence = S['Evidence']
export type GateReport = S['GateReport']
export type CheckOutcome = S['CheckOutcome']
export type DetectionReport = S['DetectionReport']
export type DetectionSpan = S['Span']
export type SignalResult = S['SignalResult']
export type SignalKind = S['SignalKind']
export type Rubric = S['Rubric']
export type Criterion = S['Criterion']
export type FormatCheck = S['FormatCheck']
export type LatePolicy = S['LatePolicy']
export type RubricSummary = S['RubricSummary']
export type CostSummary = S['CostSummary']
export type RubricDraft = S['RubricDraft']
export type CompileRubricRequest = S['CompileRubricRequest']
export type ConfirmRubricRequest = S['ConfirmRubricRequest']
export type ConfirmRubricResponse = S['ConfirmRubricResponse']
export type InitResponse = S['InitResponse']
export type ReviewResponse = S['ReviewResponse']
export type DetectResponse = S['DetectResponse']
export type ReviewRequest = S['ReviewRequest']
export type CourseOut = S['CourseOut']
export type StreamStats = S['StreamStats']
export type AssignmentStats = S['AssignmentStats']
export type StreamReviewerRow = S['StreamReviewerRow']
export type DistributeResult = S['DistributeResult']
export type StudentAssignment = S['StudentAssignment']
export type StudentSubmission = S['StudentSubmission']
export type StudentVerdict = S['StudentVerdict']
export type StudentSubmitRequest = S['StudentSubmitRequest']
export type StreamOut = S['StreamOut']
export type AssignmentOut = S['AssignmentOut']
export type AssignmentIn = S['AssignmentIn']
export type AssignmentPatch = S['AssignmentPatch']
export type CourseIn = S['CourseIn']
export type StreamIn = S['StreamIn']
export type CoursePatch = S['CoursePatch']
export type StreamPatch = S['StreamPatch']
export type StreamStudentRow = S['StreamStudentRow']
export type UserOut = S['UserOut']
export type CreateUserRequest = S['CreateUserRequest']
export type UpdateUserRequest = S['UpdateUserRequest']
export type DetectRequest = S['DetectRequest']
export type CompileRubricResponse = S['CompileRubricResponse']
export type CriterionSource = S['CriterionSource']
export type Scale = S['Scale']

export type LoginRequest = S['LoginRequest']
export type TokenResponse = S['TokenResponse']
export type MeResponse = S['MeResponse']
export type SubmissionSummary = S['SubmissionSummary']
export type SubmissionDetail = S['SubmissionDetail']
export type SubmissionStatus = S['SubmissionStatus']
export type CriterionPatch = S['CriterionPatch']
export type ReviewPatchRequest = S['ReviewPatchRequest']
export type DetectionVerdictRequest = S['DetectionVerdictRequest']
export type ReassignRequest = S['ReassignRequest']
export type RerunResponse = S['RerunResponse']
export type ChatMessage = S['ChatMessageOut']
export type ChatRequest = S['ChatRequest']

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/api'

/** Токен переживает перезагрузку вкладки: работа ревьюера — это часы в одной
 *  очереди, и F5 не повод спрашивать пароль заново. `localStorage`, а не
 *  `sessionStorage`: очередь открывают в нескольких вкладках сразу и
 *  возвращаются к ней назавтра, а `sessionStorage` теряется на каждой новой
 *  вкладке. Риск устаревшего токена (перезапуск бэкенда пересевает учётки, и
 *  прежний `sub` уже не найдётся) закрыт разбором 401 ниже: сессия сбрасывается
 *  и человек попадает на экран входа, а не на «бэкенд не отвечает». */
const TOKEN_KEY = 'avito-reviewer:token'

function storedToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

let authToken: string | null = storedToken()

export function setAuthToken(token: string | null): void {
  authToken = token
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* Приватный режим без доступа к хранилищу: токен доживёт до перезагрузки. */
  }
}

export function hasAuthToken(): boolean {
  return authToken !== null
}

/** Единственная реакция на 401 на весь фронт: протухший или чужой токен
 *  сбрасывает сессию там, где она живёт (`app/session.tsx`), а не оставляет
 *  экран гадать, почему данные не пришли. */
let unauthorizedHandler: (() => void) | null = null

export function onUnauthorized(handler: () => void): void {
  unauthorizedHandler = handler
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    /** Список поломок целиком: `POST /rubrics` отвечает на 422 не одной строкой,
     *  а перечнем того, что в рубрике не считается. Склеенный в предложение, он
     *  читается хуже списка, поэтому доезжает до экрана обеими формами. */
    readonly problems: string[] = [],
  ) {
    super(message)
  }
}

/** Бэкенд отвечает `detail` строкой или списком ошибок валидации — и то, и
 *  другое должно доехать до экрана человеческим текстом, а не `[object Object]`. */
function readDetail(payload: unknown, status: number): { message: string; problems: string[] } {
  if (typeof payload === 'string' && payload) return { message: payload, problems: [] }
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail: unknown }).detail
    if (typeof detail === 'string') return { message: detail, problems: [] }
    if (Array.isArray(detail)) {
      const problems = detail.map((item) =>
        item && typeof item === 'object' && 'msg' in item ? String((item as { msg: unknown }).msg) : String(item),
      )
      return { message: problems.join('; '), problems }
    }
  }
  return { message: `Бэкенд ответил ${status}`, problems: [] }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: {
        'content-type': 'application/json',
        ...(authToken ? { authorization: `Bearer ${authToken}` } : {}),
        ...init?.headers,
      },
    })
  } catch {
    throw new ApiError(0, 'Бэкенд недоступен. Поднимите его на :8000 и повторите.')
  }

  const payload = await response.json().catch(() => null)
  if (!response.ok) throw failure(payload, response.status, path)
  return payload as T
}

/** 401 на `/auth/login` — это «неверный логин или пароль», а не протухшая
 *  сессия: сбрасывать там нечего, и уводить с экрана входа некуда. */
function failure(payload: unknown, status: number, path: string): ApiError {
  if (status === 401 && path !== '/auth/login') {
    setAuthToken(null)
    unauthorizedHandler?.()
  }
  const { message, problems } = readDetail(payload, status)
  return new ApiError(status, message, problems)
}

export const backend = {
  init: () => request<InitResponse>('/init'),
  rubrics: () => request<RubricSummary[]>('/rubrics'),
  rubric: (assignmentId: string) => request<Rubric>(`/rubrics/${encodeURIComponent(assignmentId)}`),
  cost: () => request<CostSummary>('/cost'),

  /* Учебный каталог: курс → поток → задание. Задание — это рубрика, выданная
     потоку в срок; читать может ревьюер, менять — методист. */
  courses: () => request<CourseOut[]>('/courses'),

  /* Кабинет студента. Балл приезжает только у утверждённых работ: до этого
     оценки нет — её ставит человек, а не модель. */
  /* Статистика считается по строкам submissions, а не генератором. */
  streamStats: (streamId: string) =>
    request<StreamStats>(`/stats/streams/${encodeURIComponent(streamId)}`),
  streamReviewers: (streamId: string) =>
    request<StreamReviewerRow[]>(`/streams/${encodeURIComponent(streamId)}/reviewers`),
  assignReviewers: (streamId: string, usernames: string[]) =>
    request<StreamReviewerRow[]>(`/streams/${encodeURIComponent(streamId)}/reviewers`, {
      method: 'POST',
      body: JSON.stringify({ usernames }),
    }),
  unassignReviewer: (streamId: string, username: string) =>
    request<void>(
      `/streams/${encodeURIComponent(streamId)}/reviewers/${encodeURIComponent(username)}`,
      { method: 'DELETE' },
    ),
  distributeStream: (streamId: string) =>
    request<DistributeResult>(`/streams/${encodeURIComponent(streamId)}/distribute`, {
      method: 'POST',
    }),
  users: () => request<UserOut[]>('/users'),

  myAssignments: () => request<StudentAssignment[]>('/me/assignments'),
  mySubmissions: () => request<StudentSubmission[]>('/me/submissions'),
  submitWork: (body: StudentSubmitRequest) =>
    request<StudentSubmission>('/me/submissions', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  createCourse: (body: CourseIn) =>
    request<CourseOut>('/courses', { method: 'POST', body: JSON.stringify(body) }),
  streams: (courseId?: string) =>
    request<StreamOut[]>(`/streams${courseId ? `?course_id=${encodeURIComponent(courseId)}` : ''}`),
  createStream: (body: StreamIn) =>
    request<StreamOut>('/streams', { method: 'POST', body: JSON.stringify(body) }),
  assignments: (streamId?: string) =>
    request<AssignmentOut[]>(
      `/assignments${streamId ? `?stream_id=${encodeURIComponent(streamId)}` : ''}`,
    ),
  createAssignment: (body: AssignmentIn) =>
    request<AssignmentOut>('/assignments', { method: 'POST', body: JSON.stringify(body) }),
  patchAssignment: (id: string, body: AssignmentPatch) =>
    request<AssignmentOut>(`/assignments/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteAssignment: (id: string) =>
    request<void>(`/assignments/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  demoLogin: () => request<TokenResponse>('/auth/demo', { method: 'POST' }),
  login: (body: LoginRequest) =>
    request<TokenResponse>('/auth/login', { method: 'POST', body: JSON.stringify(body) }),
  me: () => request<MeResponse>('/me'),

  /** Условие задания → черновик рубрики. Утверждает методист, поэтому ответ
   *  несёт не только критерии, но и оговорки с открытыми вопросами —
   *  `grounded_share` рядом с ним показывает, какая доля критериев
   *  подтверждена дословной цитатой из условия, а не пересказана. */
  compileRubric: (body: CompileRubricRequest) =>
    request<CompileRubricResponse>('/rubrics/compile', { method: 'POST', body: JSON.stringify(body) }),

  /** Подтверждение методистом: черновик становится рубрикой потока. */
  confirmRubric: (body: ConfirmRubricRequest) =>
    request<ConfirmRubricResponse>('/rubrics', { method: 'POST', body: JSON.stringify(body) }),

  review: (body: ReviewRequest) =>
    request<ReviewResponse>('/review', { method: 'POST', body: JSON.stringify(body) }),

  detect: (body: DetectRequest) =>
    request<DetectResponse>('/detect', { method: 'POST', body: JSON.stringify(body) }),

  myQueue: (all?: boolean) => request<SubmissionSummary[]>(`/me/queue${all ? '?all=true' : ''}`),
  submission: (id: string) => request<SubmissionDetail>(`/submissions/${encodeURIComponent(id)}`),

  /** Правка баллов/вердиктов ревьюером — пересчитывает итог на сервере и
   *  пишет `review_revisions` с авторством; локально его не досчитать
   *  (веса, шаг шкалы, обязательные минимумы, штраф за срок). */
  patchReview: (submissionId: string, body: ReviewPatchRequest) =>
    request<ReviewDraft>(`/submissions/${encodeURIComponent(submissionId)}/review`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),

  approveReview: (submissionId: string) =>
    request<SubmissionSummary>(`/submissions/${encodeURIComponent(submissionId)}/review/approve`, {
      method: 'POST',
    }),

  rerunReview: (submissionId: string) =>
    request<RerunResponse>(`/submissions/${encodeURIComponent(submissionId)}/review/rerun`, {
      method: 'POST',
    }),

  setDetectionVerdict: (submissionId: string, spanId: string, body: DetectionVerdictRequest) =>
    request<DetectionReport>(
      `/submissions/${encodeURIComponent(submissionId)}/ai-detection/${encodeURIComponent(spanId)}/verdict`,
      { method: 'POST', body: JSON.stringify(body) },
    ),

  reassign: (submissionId: string, body: ReassignRequest) =>
    request<SubmissionSummary>(`/submissions/${encodeURIComponent(submissionId)}/reassign`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  chatHistory: (submissionId: string) =>
    request<ChatMessage[]>(`/submissions/${encodeURIComponent(submissionId)}/chat`),

  /** Один ход чата — SSE-эндпоинт, но не токен за токеном: сервер считает весь
   *  ход (возможные вызовы тулов плюс финальный ответ), сохраняет каждый шаг
   *  и только потом отдаёт их последовательностью `data:`-событий. `onStep`
   *  вызывается по мере разбора каждого события — раньше, чем ответ целиком
   *  дочитан, но не раньше, чем модель его посчитала. */
  sendChat: async (submissionId: string, message: string, onStep: (step: ChatMessage) => void): Promise<void> => {
    let response: Response
    try {
      response = await fetch(`${BASE}/submissions/${encodeURIComponent(submissionId)}/chat`, {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          ...(authToken ? { authorization: `Bearer ${authToken}` } : {}),
        },
        body: JSON.stringify({ message } satisfies ChatRequest),
      })
    } catch {
      throw new ApiError(0, 'Бэкенд недоступен. Поднимите его на :8000 и повторите.')
    }

    if (!response.ok) {
      const payload = await response.json().catch(() => null)
      throw failure(payload, response.status, `/submissions/${submissionId}/chat`)
    }
    if (!response.body) return

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) return
      buffer += decoder.decode(value, { stream: true })

      let boundary = buffer.indexOf('\n\n')
      while (boundary !== -1) {
        const block = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        for (const line of block.split('\n')) {
          if (line.startsWith('data: ') && line !== 'data: {}') {
            onStep(JSON.parse(line.slice('data: '.length)) as ChatMessage)
          }
        }
        boundary = buffer.indexOf('\n\n')
      }
    }
  },

  /* Админка: аккаунты и учебный каталог. */
  createUser: (body: CreateUserRequest) =>
    request<UserOut>('/users', { method: 'POST', body: JSON.stringify(body) }),
  patchUser: (id: string, body: UpdateUserRequest) =>
    request<UserOut>(`/users/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteUser: (id: string) => request<void>(`/users/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  patchCourse: (id: string, body: CoursePatch) =>
    request<CourseOut>(`/courses/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteCourse: (id: string) =>
    request<void>(`/courses/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  patchStream: (id: string, body: StreamPatch) =>
    request<StreamOut>(`/streams/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteStream: (id: string) =>
    request<void>(`/streams/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  streamStudents: (streamId: string) =>
    request<StreamStudentRow[]>(`/streams/${encodeURIComponent(streamId)}/students`),
  enrollStudents: (streamId: string, usernames: string[]) =>
    request<{ enrolled: number; already: number }>(
      `/streams/${encodeURIComponent(streamId)}/students`,
      { method: 'POST', body: JSON.stringify({ usernames }) },
    ),
  unenrollStudent: (streamId: string, username: string) =>
    request<void>(
      `/streams/${encodeURIComponent(streamId)}/students/${encodeURIComponent(username)}`,
      { method: 'DELETE' },
    ),
}
