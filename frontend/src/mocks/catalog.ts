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
import { ROSTER, type RosterRow } from './data/roster'
import { LEDGER_HOMEWORK_MAX, ledgerTotal, markFor } from './ledger'
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

/** Дедлайн ставится только там, где он назван в условии. Раньше задания без
 *  срока раскладывались «по 14 дней от 1 сентября» — это была выдумка: в
 *  data_analysis, data_science, GO, системном дизайне и Tech QA сроков в
 *  материалах нет вовсе, их назначает методист при запуске потока. */
function deadlineFor(task: ProgramTask): string | null {
  return task.deadline ? `${YEAR}-${task.deadline}T23:59:00+03:00` : null
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
    deadlineAt: deadlineFor(task),
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

/** Кто какие программы ведёт. Все id здесь — из `PROGRAMS`, и это условие
 *  приходилось восстанавливать дважды. Сначала половина карты ссылалась на
 *  курсы, которых в каталоге не было; потом каталог сократился до пяти
 *  направлений — тех, у которых есть записанный разбор, — и четверо
 *  назначенных на ушедшие курсы снова остались бы без потоков с нулевой
 *  загрузкой. `KNOWN_COURSES` ниже такие ссылки молча отфильтровывает,
 *  поэтому дефект и не падает, а просто выглядит как незанятые люди.
 *
 *  Переназначены по навыкам из карточек `backend/reviewers/`: у Штейн
 *  «оценка качества» и Тарасенко «эксперименты» ближе всего к Tech QA,
 *  у Заславского «метрики» и Прохоровой «А/Б» — к антифроду, где разбирают
 *  карту рисков. Лев Гринёв оставлен без назначений намеренно —
 *  руководителю есть кого распределять. */
const ASSIGNED: Record<string, string[]> = {
  'c-kruglov': ['go', 'backend'],
  'c-eremina': ['go', 'backend'],
  'c-bahtin': ['system-design', 'go'],
  'c-shtein': ['qa', 'backend'],
  'c-tarasenko': ['qa', 'system-design'],
  'c-zaslavsky': ['fraud', 'qa'],
  'c-prohorova': ['fraud', 'system-design'],
  'c-nogovitsyn': ['qa', 'fraud'],
  'c-mustafina': ['fraud', 'backend'],
  'c-grinev': [],
}

const KNOWN_COURSES = new Set(PROGRAMS.map((program) => program.id))

export const CURATORS: Curator[] = CURATOR_SEED.map((curator) => {
  const courseIds = (ASSIGNED[curator.id] ?? []).filter((courseId) => KNOWN_COURSES.has(courseId))
  const streamIds = courseIds.flatMap((courseId) => [`${courseId}-a`, `${courseId}-b`])
  return { ...curator, courseIds, streamIds, committedMinutes: 0 }
})

/** Род имени задаёт колонка «Согласие на оценку» из ведомости: «согласна» —
 *  женское, «согласен» — мужское, «Согл» не говорит ничего и раздаётся по
 *  очереди. Так подпись в ведомости и имя в таблице не спорят друг с другом. */
function genderOf(consent: string, index: number): 'm' | 'f' {
  const word = consent.toLowerCase()
  if (word.startsWith('согласна')) return 'f'
  if (word.startsWith('согласен')) return 'm'
  return index % 2 === 0 ? 'f' : 'm'
}

function buildStudents(): Student[] {
  const out: Student[] = []
  for (const stream of STREAMS) {
    const seed = [...stream.id].reduce((sum, char) => sum + char.charCodeAt(0), 0)
    const nextName = nameDealer(rng(seed * 7919))
    const curators = CURATORS.filter((item) => item.streamIds.includes(stream.id))

    /* Идентификаторы обезличены так же, как в настоящей ведомости
       организаторов: шестизначное число вместо имени и почты. Берём их из
       ведомости, а не выдумываем на месте. */
    const roster = ROSTER[stream.id] ?? []
    roster.forEach((row, i) => {
      out.push({
        id: row.id,
        alias: row.id,
        name: nextName(genderOf(row.consent, i)),
        courseId: stream.courseId,
        streamId: stream.id,
        curatorId: curators.length ? curators[i % curators.length].id : null,
        githubHandle: `student-${row.id}`,
      })
    })
  }
  return out
}

export const STUDENTS: Student[] = buildStudents()

const ROSTER_BY_STUDENT = new Map<string, { streamId: string; row: RosterRow }>(
  Object.entries(ROSTER).flatMap(([streamId, rows]) =>
    rows.map((row) => [row.id, { streamId, row }] as const),
  ),
)

function toStep(value: number, step: number): number {
  return Math.round(value / step) * step
}

/** Правила из условий: досдача в течение grace-окна стоит балл за день,
 *  позже работа оценивается в ноль. Такое правило названо только у
 *  продуктовых направлений — там же, где есть и сам дедлайн; у остальных
 *  просрочки нет, потому что нет и срока. */
function gradeFor(
  next: () => number,
  level: number,
  assignment: Assignment,
  program: Program,
): { score: number; status: GradeStatus; daysLate: number } {
  const roll = next()
  if (roll < 0.05) return { score: 0, status: 'missing', daysLate: 0 }

  const noise = (next() - 0.5) * 0.26
  const fraction = Math.max(0.25, Math.min(1, level + noise))
  const earned = toStep(fraction * assignment.maxScore, assignment.step)

  if (roll < 0.15) return { score: earned, status: 'draft_ready', daysLate: 0 }
  if (roll < 0.22) return { score: earned, status: 'in_review', daysLate: 0 }

  const graceDays = assignment.deadlineAt ? program.graceDays : null
  if (graceDays !== null && roll < 0.32) {
    const daysLate = 1 + Math.floor(next() * (graceDays + 1))
    if (daysLate > graceDays) return { score: 0, status: 'late', daysLate }
    const penalty = (program.penaltyPerDay ?? 0) * daysLate
    return { score: Math.max(0, earned - penalty), status: 'late', daysLate }
  }

  return { score: earned, status: 'approved', daysLate: 0 }
}

function buildGrades(): Grade[] {
  const out: Grade[] = []
  for (const student of STUDENTS) {
    const program = PROGRAMS.find((item) => item.id === student.courseId)!
    const next = rng(Number(student.alias) % 100000)

    /* Уровень студента задаёт ведомость, а не отдельный генератор: доля от
       суммы за ДЗ становится ожидаемой долей от максимума задания. Поэтому
       ячейка таблицы и строка ведомости говорят про одного студента одно и то
       же — хотя сложить ячейки в «Итоговую сумму» нельзя, шкалы разные. */
    const homework = ROSTER_BY_STUDENT.get(student.id)?.row.homework ?? 0
    const level = Math.max(0.3, Math.min(0.95, homework / LEDGER_HOMEWORK_MAX))

    for (const assignment of ASSIGNMENTS.filter((item) => item.courseId === student.courseId)) {
      const { score, status, daysLate } = gradeFor(next, level, assignment, program)
      /* Часть черновиков ревьюер утверждает как есть — по этим строкам потом
         считается «принято без правок»; доля утверждений без правки —
         ОЦЕНКА, а не измерение. */
      const acceptedAsIs = next() < 0.46
      /* Если ревьюер правит балл, он двигает его на шаг-другой шкалы: правка
         «на 0,07 балла» на шкале с шагом 1 — это не правка. */
      const drift = (next() < 0.5 ? -1 : 1) * assignment.step * (next() < 0.7 ? 1 : 2)
      out.push({
        studentId: student.id,
        assignmentId: assignment.id,
        submissionId: status === 'missing' ? null : `sub-${student.streamId}-${student.alias}-${assignment.id}`,
        score: status === 'missing' ? null : score,
        aiScore:
          status === 'missing'
            ? null
            : acceptedAsIs
              ? score
              : Math.max(0, Math.min(assignment.maxScore, toStep(score + drift, assignment.step))),
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

/** Ведомость потока.
 *
 *  Строки лежат готовыми в `data/roster.ts`: id, сумма за ДЗ, посещаемость,
 *  вовлечённость, экзамен, количество ДЗ и согласие на оценку. Итог и оценка
 *  здесь не хранятся, а считаются — формулой организаторов
 *  (`итог = сумма × 0.5 + экзамен × 0.4 + вовлечённость / 10`) и таблицей
 *  абсолютных порогов из `ledger.ts`. На девяти настоящих строках потока
 *  `qa-a` результат сходится со скриншотом ведомости до сотых; проверяется
 *  `node --experimental-strip-types scripts/build-roster.mjs --check`.
 *
 *  «Количество дз» берётся из ведомости там, где оно оттуда пришло (включая
 *  строку с настоящей опечаткой «ю»), иначе считается по сдачам потока. */
export function totalsForStream(streamId: string): StudentTotals[] {
  const rows = ROSTER[streamId] ?? []
  if (!rows.length) return []

  const grades = gradesForStream(streamId)
  const submittedBy = new Map<string, number>()
  for (const grade of grades) {
    if (grade.status === 'missing') continue
    submittedBy.set(grade.studentId, (submittedBy.get(grade.studentId) ?? 0) + 1)
  }

  return rows.map((row) => {
    const submitted = submittedBy.get(row.id) ?? 0
    const total = ledgerTotal(row.homework, row.exam, row.engagement)
    return {
      studentId: row.id,
      homework: row.homework,
      attendance: row.attendance,
      engagement: row.engagement,
      exam: row.exam,
      total,
      mark: markFor(total),
      homeworkCount: row.homeworkCount ?? submitted,
      consent: row.consent,
      submitted,
    }
  })
}

/** Раскладывает целое по весам без потери суммы (метод наибольших остатков):
 *  ряд остаётся оценкой формы, но его сумма — настоящая. */
function spread(total: number, weights: number[]): number[] {
  const sum = weights.reduce((acc, weight) => acc + weight, 0) || 1
  const exact = weights.map((weight) => (total * weight) / sum)
  const out = exact.map(Math.floor)
  let rest = total - out.reduce((acc, value) => acc + value, 0)
  const order = exact
    .map((value, index) => ({ index, rest: value - Math.floor(value) }))
    .sort((a, b) => b.rest - a.rest)
  for (const item of order) {
    if (rest <= 0) break
    out[item.index] += 1
    rest -= 1
  }
  return out
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
  const draftReady = grades.filter((grade) => grade.status === 'draft_ready').length
  const awaitingReview = grades.filter(
    (grade) => grade.status === 'draft_ready' || grade.status === 'in_review',
  ).length
  const overdue = grades.filter((grade) => grade.status === 'late').length
  const scored = grades.filter((grade) => grade.status === 'approved' || grade.status === 'late').length

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

  /* Раньше здесь был «средний балл по критериям»: число `55 + random × 35`
     под подписью с кодом задания. Ни числа, ни подписи не соответствовали
     заголовку панели. Считаем то, что действительно есть в данных, — среднюю
     долю от максимума по каждому заданию; по критериям такой статистики у нас
     нет и взяться ей неоткуда: критерии живут в рубрике и в разборе одной
     работы, а не в ведомости потока. */
  const assignmentAverages = assignments.map((assignment) => {
    const own = graded.filter((grade) => grade.assignmentId === assignment.id)
    const sum = own.reduce((acc, grade) => acc + (grade.score ?? 0), 0)
    const avg = own.length && assignment.maxScore
      ? Math.round((sum / own.length / assignment.maxScore) * 1000) / 10
      : 0
    return { assignment: assignment.code, title: assignment.title, avg, max: 100 }
  })

  const streamCurators = CURATORS.filter((item) => item.streamIds.includes(streamId))
  const minutesPerWork = assignments.length
    ? assignments.reduce((sum, item) => sum + item.reviewMinutes, 0) / assignments.length
    : 20

  /* ОЦЕНКА: очередь делится между ревьюерами поровну — настоящего назначения
     на конкретную сдачу у нас нет. Минуты считаются по медиане ревьюера, и
     она тоже оценочная (`CURATOR_SEED`). Зато сумма по ревьюерам равна
     настоящему числу работ, ждущих проверки прямо сейчас: недельная ёмкость
     меряется текущей очередью, а не всеми сдачами за курс. */
  const perCurator = spread(awaitingReview, streamCurators.map(() => 1))
  const reviewLoad = streamCurators.map((curator, index) => ({
    curatorId: curator.id,
    name: curator.name,
    assigned: perCurator[index] ?? 0,
    minutes: Math.round((perCurator[index] ?? 0) * curator.medianMinutesPerWork),
    capacity: curator.capacityMinutes,
  }))

  /* ОЦЕНКА формы, но не объёма: дат сдачи в данных нет, поэтому недели
     раскладываются волной «проверка начинается после дедлайна» — зато сумма
     по неделям равна настоящему числу сдач и утверждений. */
  const wave = [0.12, 0.34, 0.22, 0.1, 0.22]
  const weeklySubmitted = spread(submitted, wave)
  const weeklyApproved = spread(approved, wave)
  const weekly = ['нед. 1', 'нед. 2', 'нед. 3', 'нед. 4', 'нед. 5'].map((week, index) => ({
    week,
    submitted: weeklySubmitted[index],
    approved: weeklyApproved[index],
  }))

  const aiFlagged = grades.filter((grade) => grade.aiFlag !== null).length
  /* Ревьюер подтверждает сильный сигнал и отклоняет слабый — ПРАВИЛО, а не
     измерение: настоящих вердиктов по спанам в каталоге нет, они живут в
     прогоне. Раньше здесь стояло «42% от помеченных» без всякого основания. */
  const aiConfirmed = grades.filter((grade) => (grade.aiFlag ?? 0) >= 0.72).length

  /* «Принято без правок» теперь считается: это утверждённые работы, у
     которых балл ревьюера совпал с предложением модели. */
  const approvedGrades = grades.filter((grade) => grade.status === 'approved')
  const untouched = approvedGrades.filter((grade) => grade.aiScore === grade.score).length
  const autoAcceptRate = approvedGrades.length
    ? Math.round((untouched / approvedGrades.length) * 100) / 100
    : 0

  return {
    submitted,
    expected,
    approved,
    awaitingReview,
    overdue,
    /* ОЦЕНКА: `reviewMinutes` — прогноз трудоёмкости из `programs.ts`, а не
       замер по настоящим проверкам. */
    medianReviewMinutes: Math.round(minutesPerWork),
    autoAcceptRate,
    avgScore,
    aiFlagged,
    aiConfirmed,
    reviewWindowDays: program.reviewWindowDays,
    scoreHistogram,
    /* Шаги считаются по статусам, а не по коэффициентам: черновик собирается
       для каждой сдачи, дальше работа уходит к ревьюеру и получает оценку. */
    funnel: [
      { stage: 'Сдано', count: submitted },
      { stage: 'Черновик готов', count: submitted },
      { stage: 'Взял ревьюер', count: submitted - draftReady },
      { stage: 'Оценка выставлена', count: scored },
    ],
    assignmentAverages,
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
