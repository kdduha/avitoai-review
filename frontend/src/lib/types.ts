/** Типы фронта повторяют контракты бэкенда:
 *  `backend/src/avito_reviewer/ai/review/schema.py`,
 *  `.../ai/detection/schema.py` и схему данных из архитектуры (раздел 10).
 *  Пока их наполняет мок-слой; бэкенд отдаёт те же поля в snake_case. */

export type Role = 'curator' | 'head'

export interface Student {
  id: string
  alias: string
  name: string
  courseId: string
  streamId: string
  curatorId: string | null
  githubHandle: string
}

export interface Curator {
  id: string
  name: string
  initials: string
  email: string
  skills: string[]
  capacityMinutes: number
  committedMinutes: number
  medianMinutesPerWork: number
  onboarding: boolean
  courseIds: string[]
  streamIds: string[]
}

export interface Assignment {
  id: string
  courseId: string
  code: string
  title: string
  maxScore: number
  /** Порог зачёта берётся из шкалы рубрики и у разных заданий разный. */
  passThreshold: number
  /** Шаг шкалы: баллы бывают дробными, и округлять надо по правилу задания. */
  step: number
  /** Канал сдачи: pull request, документ, таблица, ноутбук, доска. */
  channel: string
  /** Прогноз трудоёмкости разбора одной работы, минуты. */
  reviewMinutes: number
  /** В условии есть требование заявлять использование ИИ. */
  declareAi: boolean
  deadlineAt: string
}

/** Итоговая строка ведомости — так она устроена у организаторов. */
export interface StudentTotals {
  studentId: string
  /** Сумма за домашние работы. */
  homework: number
  attendance: number
  engagement: number
  exam: number
  /** итог = сумма × 0.5 + экзамен × 0.4 + вовлечённость / 10 */
  total: number
  /** Итог, отображённый на десятибалльную оценку. */
  mark: number
  submitted: number
}

export interface Stream {
  id: string
  courseId: string
  short: string
  title: string
  startsAt: string
  endsAt: string
}

export interface Course {
  id: string
  short: string
  title: string
  subtitle: string
  streamIds: string[]
}

export type GradeStatus = 'approved' | 'draft_ready' | 'in_review' | 'missing' | 'late'

export interface Grade {
  studentId: string
  assignmentId: string
  submissionId: string | null
  score: number | null
  aiScore: number | null
  status: GradeStatus
  aiFlag: number | null
  daysLate: number
}

export interface StreamStats {
  submitted: number
  expected: number
  approved: number
  awaitingReview: number
  overdue: number
  medianReviewMinutes: number
  /** «Проверка начинается после дедлайна и занимает не более N дней». */
  reviewWindowDays: number | null
  autoAcceptRate: number
  avgScore: number
  aiFlagged: number
  aiConfirmed: number
  scoreHistogram: { bucket: string; count: number }[]
  funnel: { stage: string; count: number }[]
  criterionAverages: { criterion: string; avg: number; max: number }[]
  reviewLoad: { curatorId: string; name: string; assigned: number; minutes: number; capacity: number }[]
  weekly: { week: string; submitted: number; approved: number }[]
}
