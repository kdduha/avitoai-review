import type {
  Assignment,
  Course,
  Curator,
  Grade,
  GradeStatus,
  Stream,
  StreamStats,
  Student,
} from '@/lib/types'
import { nameDealer, rng } from './seed'

export const COURSES: Course[] = [
  {
    id: 'go',
    short: 'Микросервисы на Go',
    title: 'Разработка микросервисов на Go',
    subtitle: 'Три этапа: boilerplate, gRPC-слои, наблюдаемость',
    streamIds: ['go-12', 'go-11'],
  },
  {
    id: 'llm',
    short: 'LLM-инженерия',
    title: 'LLM-инженерия',
    subtitle: 'RAG, агенты, оценка качества',
    streamIds: ['llm-4'],
  },
  {
    id: 'ml',
    short: 'ML в продукте',
    title: 'ML в продукте',
    subtitle: 'От гипотезы до эксперимента в проде',
    streamIds: ['ml-7'],
  },
]

export const STREAMS: Stream[] = [
  { id: 'go-12', short: 'Поток 12', courseId: 'go', title: 'Поток 12, осень 2026', startsAt: '2026-08-25', endsAt: '2026-11-30' },
  { id: 'go-11', short: 'Поток 11', courseId: 'go', title: 'Поток 11, весна 2026', startsAt: '2026-02-10', endsAt: '2026-05-22' },
  { id: 'llm-4', short: 'Поток 4', courseId: 'llm', title: 'Поток 4, осень 2026', startsAt: '2026-09-01', endsAt: '2026-12-15' },
  { id: 'ml-7', short: 'Поток 7', courseId: 'ml', title: 'Поток 7, осень 2026', startsAt: '2026-08-18', endsAt: '2026-12-01' },
]

export const ASSIGNMENTS: Assignment[] = [
  { id: 'go-task1', courseId: 'go', code: 'ДЗ 1', title: 'Boilerplate и веб-сервер', maxScore: 10, deadlineAt: '2026-08-26T21:00:00+03:00' },
  { id: 'go-task2', courseId: 'go', code: 'ДЗ 2', title: 'Микросервисы: слои и gRPC', maxScore: 10, deadlineAt: '2026-09-02T21:00:00+03:00' },
  { id: 'go-task3', courseId: 'go', code: 'ДЗ 3', title: 'Наблюдаемость и деплой', maxScore: 10, deadlineAt: '2026-09-16T21:00:00+03:00' },
  { id: 'llm-task1', courseId: 'llm', code: 'ДЗ 1', title: 'Базовый RAG-контур', maxScore: 10, deadlineAt: '2026-09-08T21:00:00+03:00' },
  { id: 'llm-task2', courseId: 'llm', code: 'ДЗ 2', title: 'Оценка качества ответов', maxScore: 10, deadlineAt: '2026-09-22T21:00:00+03:00' },
  { id: 'ml-task1', courseId: 'ml', code: 'ДЗ 1', title: 'Дизайн эксперимента', maxScore: 10, deadlineAt: '2026-08-29T21:00:00+03:00' },
  { id: 'ml-task2', courseId: 'ml', code: 'ДЗ 2', title: 'Пайплайн и метрики', maxScore: 10, deadlineAt: '2026-09-12T21:00:00+03:00' },
]

export const CURATORS: Curator[] = [
  {
    id: 'c-kruglov', name: 'Антон Круглов', initials: 'АК', email: 'a.kruglov@avito.ru',
    skills: ['go', 'gRPC', 'наблюдаемость'], capacityMinutes: 600, committedMinutes: 415,
    medianMinutesPerWork: 17, onboarding: false, courseIds: ['go'], streamIds: ['go-12', 'go-11'],
  },
  {
    id: 'c-eremina', name: 'Мария Ерёмина', initials: 'МЕ', email: 'm.eremina@avito.ru',
    skills: ['go', 'тестирование', 'CI'], capacityMinutes: 480, committedMinutes: 300,
    medianMinutesPerWork: 21, onboarding: false, courseIds: ['go'], streamIds: ['go-12'],
  },
  {
    id: 'c-bahtin', name: 'Данил Бахтин', initials: 'ДБ', email: 'd.bahtin@avito.ru',
    skills: ['go', 'docker', 'postgres'], capacityMinutes: 360, committedMinutes: 335,
    medianMinutesPerWork: 26, onboarding: true, courseIds: ['go'], streamIds: ['go-12'],
  },
  {
    id: 'c-shtein', name: 'Алиса Штейн', initials: 'АШ', email: 'a.shtein@avito.ru',
    skills: ['LLM', 'RAG', 'оценка качества'], capacityMinutes: 540, committedMinutes: 190,
    medianMinutesPerWork: 42, onboarding: false, courseIds: ['llm'], streamIds: ['llm-4'],
  },
  {
    id: 'c-tarasenko', name: 'Ева Тарасенко', initials: 'ЕТ', email: 'e.tarasenko@avito.ru',
    skills: ['ML', 'эксперименты', 'python'], capacityMinutes: 480, committedMinutes: 265,
    medianMinutesPerWork: 38, onboarding: false, courseIds: ['ml'], streamIds: ['ml-7'],
  },
  {
    id: 'c-zaslavsky', name: 'Роман Заславский', initials: 'РЗ', email: 'r.zaslavsky@avito.ru',
    skills: ['go', 'LLM', 'архитектура'], capacityMinutes: 300, committedMinutes: 60,
    medianMinutesPerWork: 19, onboarding: false, courseIds: [], streamIds: [],
  },
  {
    id: 'c-prohorova', name: 'Дарья Прохорова', initials: 'ДП', email: 'd.prohorova@avito.ru',
    skills: ['ML', 'статистика'], capacityMinutes: 420, committedMinutes: 0,
    medianMinutesPerWork: 33, onboarding: true, courseIds: [], streamIds: [],
  },
]

const STREAM_SIZE: Record<string, number> = {
  'go-12': 26,
  'go-11': 22,
  'llm-4': 18,
  'ml-7': 20,
}

/** Номера студентов разведены по потокам, чтобы S-1043 из демо-ревью всегда
 *  оказывался в go-12 и ведомость сходилась с карточкой работы. */
const STREAM_NUMBER_BASE: Record<string, number> = {
  'go-12': 1030,
  'go-11': 1100,
  'llm-4': 2000,
  'ml-7': 3000,
}

/** Студент S-1043 из демо-ревью существует в потоке go-12 под своим номером. */
export const DEMO_STUDENT_ID = 'S-1043'
export const DEMO_SUBMISSION_ID = 'sub-go12-1043-task2'

function buildStudents(): Student[] {
  const out: Student[] = []
  for (const stream of STREAMS) {
    let counter = STREAM_NUMBER_BASE[stream.id]
    const next = rng(stream.id.length * 7919 + stream.id.charCodeAt(0) * 104729)
    const nextName = nameDealer(next)
    const curators = CURATORS.filter((c) => c.streamIds.includes(stream.id))
    for (let i = 0; i < STREAM_SIZE[stream.id]; i += 1) {
      counter += 1
      const alias = `S-${counter}`
      const name = nextName()
      out.push({
        id: alias,
        alias,
        name,
        courseId: stream.courseId,
        streamId: stream.id,
        curatorId: curators.length ? curators[i % curators.length].id : null,
        githubHandle: `student-${counter}`,
      })
    }
  }
  return out
}

export const STUDENTS: Student[] = buildStudents()

/** Шкала совпадает с рубрикой курса: 10 баллов, шаг 0.5, порог зачёта 6. */
export const MAX_SCORE = 10
export const PASS_THRESHOLD = 6
const STEP = 0.5

function toStep(value: number): number {
  return Math.round(value / STEP) * STEP
}

function gradeFor(next: () => number, base: number): { score: number; status: GradeStatus } {
  const roll = next()
  if (roll < 0.06) return { score: 0, status: 'missing' }
  const noise = (next() - 0.5) * 2.6
  const score = toStep(Math.max(2.5, Math.min(MAX_SCORE, base + noise)))
  if (roll < 0.16) return { score, status: 'draft_ready' }
  if (roll < 0.24) return { score, status: 'in_review' }
  if (roll < 0.32) return { score, status: 'late' }
  return { score, status: 'approved' }
}

function buildGrades(): Grade[] {
  const out: Grade[] = []
  for (const student of STUDENTS) {
    const next = rng(student.alias.charCodeAt(2) * 31 + Number(student.alias.slice(2)) * 7)
    const talent = 5.8 + next() * 3.4
    for (const assignment of ASSIGNMENTS.filter((a) => a.courseId === student.courseId)) {
      const drift = (ASSIGNMENTS.indexOf(assignment) % 3) * 0.2
      const { score, status } = gradeFor(next, talent + drift)
      const flagged = next() < 0.14
      out.push({
        studentId: student.id,
        assignmentId: assignment.id,
        submissionId: status === 'missing' ? null : `sub-${student.streamId}-${student.alias.slice(2)}-${assignment.id}`,
        score: status === 'missing' ? null : score,
        aiScore: status === 'missing' ? null : toStep(Math.max(2, Math.min(MAX_SCORE, score + (next() - 0.5) * 1.5))),
        status,
        aiFlag: flagged ? Math.round((0.5 + next() * 0.45) * 100) / 100 : null,
        daysLate: status === 'late' ? 1 + Math.floor(next() * 3) : 0,
      })
    }
  }
  return out
}

const ALL_GRADES = buildGrades()

/** Демо-работа должна совпадать с тем, что показывает Review Workspace. */
const demoGrade = ALL_GRADES.find(
  (g) => g.studentId === DEMO_STUDENT_ID && g.assignmentId === 'go-task2',
)
if (demoGrade) {
  demoGrade.submissionId = DEMO_SUBMISSION_ID
  demoGrade.score = 8
  demoGrade.aiScore = 8
  demoGrade.status = 'draft_ready'
  demoGrade.aiFlag = 0.68
  demoGrade.daysLate = 0
}

export const GRADES: Grade[] = ALL_GRADES

export function gradesForStream(streamId: string): Grade[] {
  const ids = new Set(STUDENTS.filter((s) => s.streamId === streamId).map((s) => s.id))
  return GRADES.filter((g) => ids.has(g.studentId))
}

export function statsForStream(streamId: string): StreamStats | null {
  const stream = STREAMS.find((item) => item.id === streamId)
  if (!stream) return null
  const students = STUDENTS.filter((s) => s.streamId === streamId)
  const assignments = ASSIGNMENTS.filter((a) => a.courseId === stream.courseId)
  const grades = gradesForStream(streamId)
  const graded = grades.filter((g) => g.score !== null)

  const expected = students.length * assignments.length
  const submitted = graded.length
  const approved = grades.filter((g) => g.status === 'approved').length
  const awaitingReview = grades.filter((g) => g.status === 'draft_ready' || g.status === 'in_review').length
  const overdue = grades.filter((g) => g.status === 'late').length

  const avgScore = graded.length
    ? Math.round((graded.reduce((sum, g) => sum + (g.score ?? 0), 0) / graded.length) * 10) / 10
    : 0

  const buckets = ['до 4', '4–5,5', '5,5–7', '7–8,5', '8,5–10']
  const scoreHistogram = buckets.map((bucket) => ({ bucket, count: 0 }))
  for (const g of graded) {
    const value = g.score ?? 0
    const index = value < 4 ? 0 : value < 5.5 ? 1 : value < 7 ? 2 : value < 8.5 ? 3 : 4
    scoreHistogram[index].count += 1
  }

  const next = rng(streamId.length * 6151 + submitted)
  const criteria = stream.courseId === 'go'
    ? ['Структура проекта', 'Веб-сервер и .env', 'Тестовые эндпоинты', 'Завершение по сигналу', 'Чистота кода']
    : ['Постановка', 'Реализация', 'Метрики', 'Анализ', 'Оформление']

  const criterionAverages = criteria.map((criterion) => ({
    criterion,
    avg: Math.round((5.5 + next() * 3.5) * 10) / 10,
    max: MAX_SCORE,
  }))

  const streamCurators = CURATORS.filter((c) => c.streamIds.includes(streamId))
  const reviewLoad = streamCurators.map((c, index) => {
    const assigned = Math.round(submitted / Math.max(1, streamCurators.length)) - index * 2
    return {
      curatorId: c.id,
      name: c.name,
      assigned: Math.max(1, assigned),
      minutes: Math.max(30, assigned * c.medianMinutesPerWork),
      capacity: c.capacityMinutes,
    }
  })

  const weekly = ['нед. 1', 'нед. 2', 'нед. 3', 'нед. 4', 'нед. 5'].map((week, index) => {
    const base = Math.round(students.length * (0.5 + next() * 0.45))
    return { week, submitted: base, approved: Math.max(0, base - 2 - index) }
  })

  const aiFlagged = grades.filter((g) => g.aiFlag !== null).length

  return {
    submitted,
    expected,
    approved,
    awaitingReview,
    overdue,
    medianReviewMinutes: Math.round(12 + next() * 9),
    autoAcceptRate: Math.round((0.38 + next() * 0.24) * 100) / 100,
    avgScore,
    aiFlagged,
    aiConfirmed: Math.round(aiFlagged * 0.42),
    scoreHistogram,
    funnel: [
      { stage: 'Сдано', count: submitted },
      { stage: 'Черновик готов', count: Math.round(submitted * 0.94) },
      { stage: 'На проверке', count: awaitingReview },
      { stage: 'Утверждено', count: approved },
    ],
    criterionAverages,
    reviewLoad,
    weekly,
  }
}
