/** Клиент бэкенда. Типы не пишутся руками — они сгенерированы из OpenAPI
 *  (`npm run gen:api`), поэтому расхождение с сервером ловится компилятором,
 *  а не на демо. */

import type { components } from './backend.d'

type S = components['schemas']

export type SubmissionBundle = S['SubmissionBundle']
export type ArtifactText = S['ArtifactTextOut']
export type ReviewDraft = S['ReviewDraft']
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
export type RubricSummary = S['RubricSummary']
export type CostSummary = S['CostSummary']
export type InitResponse = S['InitResponse']
export type ReviewResponse = S['ReviewResponse']
export type DetectResponse = S['DetectResponse']
export type ReviewRequest = S['ReviewRequest']
export type DetectRequest = S['DetectRequest']

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/api'

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message)
  }
}

/** Бэкенд отвечает `detail` строкой или списком ошибок валидации — и то, и
 *  другое должно доехать до экрана человеческим текстом, а не `[object Object]`. */
function readDetail(payload: unknown, status: number): string {
  if (typeof payload === 'string' && payload) return payload
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return detail
        .map((item) =>
          item && typeof item === 'object' && 'msg' in item ? String((item as { msg: unknown }).msg) : String(item),
        )
        .join('; ')
    }
  }
  return `Бэкенд ответил ${status}`
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { 'content-type': 'application/json', ...init?.headers },
    })
  } catch {
    throw new ApiError(0, 'Бэкенд недоступен. Поднимите его на :8000 и повторите.')
  }

  const payload = await response.json().catch(() => null)
  if (!response.ok) throw new ApiError(response.status, readDetail(payload, response.status))
  return payload as T
}

export const backend = {
  init: () => request<InitResponse>('/init'),
  rubrics: () => request<RubricSummary[]>('/rubrics'),
  rubric: (assignmentId: string) => request<Rubric>(`/rubrics/${encodeURIComponent(assignmentId)}`),
  cost: () => request<CostSummary>('/cost'),

  review: (body: ReviewRequest) =>
    request<ReviewResponse>('/review', { method: 'POST', body: JSON.stringify(body) }),

  detect: (body: DetectRequest) =>
    request<DetectResponse>('/detect', { method: 'POST', body: JSON.stringify(body) }),
}
