import type {
  Assignment,
  Course,
  Curator,
  Grade,
  GradeStatus,
  Stream,
  StreamStats,
  Student,
  StudentTotals,
} from '@/lib/types'
import { PROGRAMS, type Program, type ProgramTask } from './programs'
import { nameDealer, rng } from './seed'

/** Учебный год демо-данных. Дедлайны в условиях заданы днём и месяцем без
 *  года — привязываем их к году потока. */
const YEAR = 2026

export const COURSES: Course[] = PROGRAMS.map((program) => ({
  id: program.id,
  short: program.short,
  title: program.title,
  subtitle: program.subtitle,
  streamIds: [`${program.id}-a`, `${program.id}-b`],
}))

export const STREAMS: Stream[] = PROGRAMS.flatMap((program) => [
  {
    id: `${program.id}-a`,
    courseId: program.id,
    short: 'Поток 2',
    title: 'Поток 2, осень 2026',
    startsAt: `${YEAR}-09-01`,
    endsAt: `${YEAR}-12-15`,
  },
  {
    id: `${program.id}-b`,
    courseId: program.id,
    short: 'Поток 1',
    title: 'Поток 1, весна 2026',
    startsAt: `${YEAR}-02-10`,
    endsAt: `${YEAR}-05-25`,
  },
])

/** Срока в условии может не быть вовсе — тогда его назначает методист, и мы
 *  раскладываем задания по потоку равномерно. */
function deadlineFor(task: ProgramTask, index: number): string {
  if (task.deadline) return `${YEAR}-${task.deadline}T23:59:00+03:00`
  const start = new Date(`${YEAR}-09-01T00:00:00+03:00`)
  start.setDate(start.getDate() + 14 * (index + 1))
  return `${start.toISOString().slice(0, 10)}T21:00:00+03:00`
}

export const ASSIGNMENTS: Assignment[] = PROGRAMS.flatMap((program) =>
  program.tasks.map((task, index) => ({
    id: `${program.id}-${index + 1}`,
    courseId: program.id,
    code: task.code,
    title: task.title,
    maxScore: task.maxScore,
    passThreshold: task.passThreshold,
    step: task.step,
    channel: task.channel,
    reviewMinutes: task.reviewMinutes,
    declareAi: task.declareAi,
    deadlineAt: deadlineFor(task, index),
  })),
)

const CURATOR_SEED: Omit<Curator, 'courseIds' | 'streamIds' | 'committedMinutes'>[] = [
  { id: 'c-kruglov', name: 'Антон Круглов', initials: 'АК', email: 'a.kruglov@avito.ru', skills: ['go', 'бэкенд', 'архитектура'], capacityMinutes: 600, medianMinutesPerWork: 17, onboarding: false },
  { id: 'c-eremina', name: 'Мария Ерёмина', initials: 'МЕ', email: 'm.eremina@avito.ru', skills: ['go', 'тестирование', 'CI'], capacityMinutes: 480, medianMinutesPerWork: 21, onboarding: false },
  { id: 'c-bahtin', name: 'Данил Бахтин', initials: 'ДБ', email: 'd.bahtin@avito.ru', skills: ['системный дизайн', 'docker', 'postgres'], capacityMinutes: 360, medianMinutesPerWork: 26, onboarding: true },
  { id: 'c-shtein', name: 'Алиса Штейн', initials: 'АШ', email: 'a.shtein@avito.ru', skills: ['LLM', 'MLflow', 'оценка качества'], capacityMinutes: 540, medianMinutesPerWork: 42, onboarding: false },
  { id: 'c-tarasenko', name: 'Ева Тарасенко', initials: 'ЕТ', email: 'e.tarasenko@avito.ru', skills: ['ML', 'эксперименты', 'python'], capacityMinutes: 480, medianMinutesPerWork: 38, onboarding: false },
  { id: 'c-zaslavsky', name: 'Роман Заславский', initials: 'РЗ', email: 'r.zaslavsky@avito.ru', skills: ['продукт', 'метрики', 'юнит-экономика'], capacityMinutes: 420, medianMinutesPerWork: 33, onboarding: false },
  { id: 'c-prohorova', name: 'Дарья Прохорова', initials: 'ДП', email: 'd.prohorova@avito.ru', skills: ['аналитика', 'статистика', 'А/Б'], capacityMinutes: 420, medianMinutesPerWork: 29, onboarding: true },
  { id: 'c-nogovitsyn', name: 'Савелий Ноговицын', initials: 'СН', email: 's.nogovitsyn@avito.ru', skills: ['QA', 'тест-дизайн'], capacityMinutes: 300, medianMinutesPerWork: 24, onboarding: false },
  { id: 'c-mustafina', name: 'Регина Мустафина', initials: 'РМ', email: 'r.mustafina@avito.ru', skills: ['антифрод', 'риски', 'продукт'], capacityMinutes: 360, medianMinutesPerWork: 27, onboarding: false },
  { id: 'c-grinev', name: 'Лев Гринёв', initials: 'ЛГ', email: 'l.grinev@avito.ru', skills: ['GPU', 'инфраструктура'], capacityMinutes: 300, medianMinutesPerWork: 36, onboarding: false },
]

/** Кто какие программы ведёт. Часть ревьюеров намеренно оставлена без
 *  назначений — руководителю есть кого распределять. */
const ASSIGNED: Record<string, string[]> = {
  'c-kruglov': ['go', 'backend'],
  'c-eremina': ['go', 'backend'],
  'c-bahtin': ['system-design', 'go'],
  'c-shtein': ['llm', 'mlsd'],
  'c-tarasenko': ['mlsd', 'gpu'],
  'c-zaslavsky': ['product', 'business-models'],
  'c-prohorova': ['analytics', 'product'],
  'c-nogovitsyn': ['qa', 'analytics'],
  'c-mustafina': ['fraud', 'business-models'],
  'c-grinev': [],
}

export const CURATORS: Curator[] = CURATOR_SEED.map((curator) => {
  const courseIds = ASSIGNED[curator.id] ?? []
  const streamIds = courseIds.flatMap((courseId) => [`${courseId}-a`, `${courseId}-b`])
  return { ...curator, courseIds, streamIds, committedMinutes: 0 }
})

function buildStudents(): Student[] {
  const out: Student[] = []
  for (const stream of STREAMS) {
    const program = PROGRAMS.find((item) => item.id === stream.courseId)!
    const seed = [...stream.id].reduce((sum, char) => sum + char.charCodeAt(0), 0)
    const next = rng(seed * 7919)
    const nextName = nameDealer(next)
    const curators = CURATORS.filter((item) => item.streamIds.includes(stream.id))

    /* Идентификаторы обезличены так же, как в настоящей ведомости
       организаторов: шестизначное число вместо имени и почты. */
    for (let i = 0; i < program.cohort; i += 1) {
      const alias = String(100000 + Math.floor(next() * 899999))
      out.push({
        id: alias,
        alias,
        name: nextName(),
        courseId: stream.courseId,
        streamId: stream.id,
        curatorId: curators.length ? curators[i % curators.length].id : null,
        githubHandle: `student-${alias}`,
      })
    }
  }
  return out
}

export const STUDENTS: Student[] = buildStudents()

function toStep(value: number, step: number): number {
  return Math.round(value / step) * step
}

/** Правила из условий: досдача в течение grace-окна стоит балл за день,
 *  позже работа оценивается в ноль. Штраф считается от набранного. */
function gradeFor(
  next: () => number,
  talent: number,
  assignment: Assignment,
  program: Program,
): { score: number; status: GradeStatus; daysLate: number } {
  const roll = next()
  if (roll < 0.05) return { score: 0, status: 'missing', daysLate: 0 }

  const noise = (next() - 0.5) * 0.26
  const fraction = Math.max(0.25, Math.min(1, talent + noise))
  const earned = toStep(fraction * assignment.maxScore, assignment.step)

  if (roll < 0.15) return { score: earned, status: 'draft_ready', daysLate: 0 }
  if (roll < 0.22) return { score: earned, status: 'in_review', daysLate: 0 }

  if (roll < 0.32) {
    const daysLate = 1 + Math.floor(next() * (program.graceDays + 1))
    if (daysLate > program.graceDays) return { score: 0, status: 'late', daysLate }
    const penalty = program.penaltyPerDay * daysLate
    return { score: Math.max(0, earned - penalty), status: 'late', daysLate }
  }

  return { score: earned, status: 'approved', daysLate: 0 }
}

function buildGrades(): Grade[] {
  const out: Grade[] = []
  for (const student of STUDENTS) {
    const program = PROGRAMS.find((item) => item.id === student.courseId)!
    const next = rng(Number(student.alias) % 100000)
    const talent = 0.55 + next() * 0.4

    for (const assignment of ASSIGNMENTS.filter((item) => item.courseId === student.courseId)) {
      const { score, status, daysLate } = gradeFor(next, talent, assignment, program)
      out.push({
        studentId: student.id,
        assignmentId: assignment.id,
        submissionId: status === 'missing' ? null : `sub-${student.streamId}-${student.alias}-${assignment.id}`,
        score: status === 'missing' ? null : score,
        aiScore:
          status === 'missing'
            ? null
            : toStep(
                Math.max(0, Math.min(assignment.maxScore, score + (next() - 0.5) * assignment.maxScore * 0.15)),
                assignment.step,
              ),
        status,
        aiFlag: next() < 0.12 ? Math.round((0.5 + next() * 0.45) * 100) / 100 : null,
        daysLate,
      })
    }
  }
  return out
}

export const GRADES: Grade[] = buildGrades()

export function gradesForStream(streamId: string): Grade[] {
  const ids = new Set(STUDENTS.filter((student) => student.streamId === streamId).map((s) => s.id))
  return GRADES.filter((grade) => ids.has(grade.studentId))
}

/** Итоговая строка ведомости считается по формуле организаторов:
 *  итог = сумма за ДЗ × 0.5 + экзамен × 0.4 + вовлечённость / 10,
 *  дальше итог отображается на десятибалльную оценку. */
export function totalsForStream(streamId: string): StudentTotals[] {
  const stream = STREAMS.find((item) => item.id === streamId)
  if (!stream) return []

  const students = STUDENTS.filter((student) => student.streamId === streamId)
  const grades = gradesForStream(streamId)
  const homeworkMax = ASSIGNMENTS.filter((item) => item.courseId === stream.courseId).reduce(
    (sum, item) => sum + item.maxScore,
    0,
  )
  const maxTotal = homeworkMax * 0.5 + 30 * 0.4 + 2

  return students.map((student) => {
    const next = rng(Number(student.alias) * 31)
    const own = grades.filter((grade) => grade.studentId === student.id)
    const homework = own.reduce((sum, grade) => sum + (grade.score ?? 0), 0)
    const attendance = 1 + Math.floor(next() * 12)
    const engagement = [0, 10, 20][Math.floor(next() * 3)]
    const exam = Math.round((18 + next() * 12) * 10) / 10
    const total = Math.round((homework * 0.5 + exam * 0.4 + engagement / 10) * 10) / 10

    const share = maxTotal ? total / maxTotal : 0
    const mark =
      share >= 0.9 ? 10 : share >= 0.83 ? 9 : share >= 0.76 ? 8 : share >= 0.68 ? 7 : share >= 0.6 ? 6 : share >= 0.5 ? 5 : 4

    return {
      studentId: student.id,
      homework: Math.round(homework * 10) / 10,
      attendance,
      engagement,
      exam,
      total,
      mark,
      submitted: own.filter((grade) => grade.status !== 'missing').length,
    }
  })
}

export function statsForStream(streamId: string): StreamStats | null {
  const stream = STREAMS.find((item) => item.id === streamId)
  if (!stream) return null

  const program = PROGRAMS.find((item) => item.id === stream.courseId)!
  const students = STUDENTS.filter((item) => item.streamId === streamId)
  const assignments = ASSIGNMENTS.filter((item) => item.courseId === stream.courseId)
  const grades = gradesForStream(streamId)
  const graded = grades.filter((grade) => grade.score !== null)

  const expected = students.length * assignments.length
  const submitted = graded.length
  const approved = grades.filter((grade) => grade.status === 'approved').length
  const awaitingReview = grades.filter(
    (grade) => grade.status === 'draft_ready' || grade.status === 'in_review',
  ).length
  const overdue = grades.filter((grade) => grade.status === 'late').length

  const avgScore = graded.length
    ? Math.round((graded.reduce((sum, grade) => sum + (grade.score ?? 0), 0) / graded.length) * 10) / 10
    : 0

  /* Шкалы у заданий разные — от 6 баллов до 20, поэтому распределение
     строится по доле от максимума. */
  const maxOf = new Map(assignments.map((item) => [item.id, item.maxScore]))
  const buckets = ['до 40%', '40–55%', '55–70%', '70–85%', '85–100%']
  const scoreHistogram = buckets.map((bucket) => ({ bucket, count: 0 }))
  for (const grade of graded) {
    const max = maxOf.get(grade.assignmentId) ?? 0
    if (!max) continue
    const share = (grade.score ?? 0) / max
    const index = share < 0.4 ? 0 : share < 0.55 ? 1 : share < 0.7 ? 2 : share < 0.85 ? 3 : 4
    scoreHistogram[index].count += 1
  }

  const next = rng(students.length * 6151 + submitted)
  const criterionAverages = assignments.slice(0, 6).map((assignment) => ({
    criterion: `${assignment.code}`,
    avg: Math.round((55 + next() * 35) * 10) / 10,
    max: 100,
  }))

  const streamCurators = CURATORS.filter((item) => item.streamIds.includes(streamId))
  const minutesPerWork = assignments.length
    ? assignments.reduce((sum, item) => sum + item.reviewMinutes, 0) / assignments.length
    : 20

  const reviewLoad = streamCurators.map((curator, index) => {
    const assigned = Math.max(1, Math.round(submitted / Math.max(1, streamCurators.length)) - index * 2)
    return {
      curatorId: curator.id,
      name: curator.name,
      assigned,
      minutes: Math.round(assigned * minutesPerWork),
      capacity: curator.capacityMinutes,
    }
  })

  /* Проверка идёт волной: она начинается после дедлайна и укладывается в
     семь дней, поэтому по неделям виден всплеск, а не ровный поток. */
  const weekly = ['нед. 1', 'нед. 2', 'нед. 3', 'нед. 4', 'нед. 5'].map((week, index) => {
    const wave = [0.2, 0.9, 0.5, 0.3, 0.8][index]
    const sent = Math.round(students.length * wave)
    return { week, submitted: sent, approved: Math.max(0, Math.round(sent * 0.72) - index) }
  })

  const aiFlagged = grades.filter((grade) => grade.aiFlag !== null).length

  return {
    submitted,
    expected,
    approved,
    awaitingReview,
    overdue,
    medianReviewMinutes: Math.round(minutesPerWork),
    autoAcceptRate: Math.round((0.38 + next() * 0.24) * 100) / 100,
    avgScore,
    aiFlagged,
    aiConfirmed: Math.round(aiFlagged * 0.42),
    reviewWindowDays: program.reviewWindowDays,
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

/* Загрузка ревьюеров складывается из того, что им реально назначено. */
for (const curator of CURATORS) {
  curator.committedMinutes = curator.streamIds.reduce((sum, streamId) => {
    const load = statsForStream(streamId)?.reviewLoad.find((row) => row.curatorId === curator.id)
    return sum + (load?.minutes ?? 0)
  }, 0)
}
