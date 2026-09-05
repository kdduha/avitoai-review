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
  /** Порог зачёта. В материалах он назван только у системного дизайна
   *  (4 из 6 и 6 из 10) — у остальных заданий его нет, и это null, а не 60%
   *  от максимума: проставить порог за методиста мы не можем. */
  passThreshold: number | null
  /** Шаг шкалы: баллы бывают дробными, и округлять надо по правилу задания.
   *  0.5 назван только у системного дизайна и у основ backend. */
  step: number
  /** Канал сдачи: pull request, коммит, папка в репозитории, Markdown в git,
   *  Google Документ, Google Таблица, ноутбук с MLflow, доска. */
  channel: string
  /** Прогноз трудоёмкости разбора одной работы, минуты. */
  reviewMinutes: number
  /** В условии есть требование заявлять использование ИИ. */
  declareAi: boolean
  /** Срок из условия. null — срока в материалах нет, его назначает методист. */
  deadlineAt: string | null
}

/** Итоговая строка ведомости — так она устроена у организаторов. */
export interface StudentTotals {
  studentId: string
  /** «Итоговая сумма»: сумма за домашние работы на шкале ведомости. */
  homework: number
  attendance: number
  /** «Вовлеченность»: 0, 10 или 20 — других значений в ведомости нет. */
  engagement: number
  exam: number
  /** итог = сумма × 0.5 + экзамен × 0.4 + вовлечённость / 10 */
  total: number
  /** Итог, отображённый на десятибалльную оценку. */
  mark: number
  /** «Количество дз» из ведомости. В одной настоящей строке вместо числа
   *  стоит «ю» — опечатка живой таблицы, поэтому тип с строкой. */
  homeworkCount: number | string
  /** «Согласие на оценку» — свободный текст: «согласен», «Согл», «Согласна». */
  consent: string
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
  /** Средняя доля от максимума по каждому заданию, проценты. По критериям
   *  такой статистики у потока нет: критерии живут в рубрике и в разборе
   *  одной работы. */
  assignmentAverages: { assignment: string; title: string; avg: number; max: number }[]
  reviewLoad: { curatorId: string; name: string; assigned: number; minutes: number; capacity: number }[]
  weekly: { week: string; submitted: number; approved: number }[]
}
