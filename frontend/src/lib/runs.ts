/** Прогоны проверки.
 *
 *  Бэкенд без состояния: `/review` принимает ссылку и отдаёт черновик, но
 *  никуда его не кладёт. Пока нет `submissions`, результат живёт здесь, в
 *  памяти вкладки. Отсюда же берётся демо-прогон — он в том же формате, что
 *  ответ сервера, и проходит через тот же адаптер.
 */

import { backend, type DetectResponse, type ReviewResponse, type Rubric } from './backend'
import { buildWorkspace, withScore, type Workspace } from './workspace'
import { DEMO_DETECT, DEMO_REVIEW, DEMO_RUN_ID } from '@/mocks/demoRun'

export { DEMO_RUN_ID }
import { DEMO_BACKEND_DETECT, DEMO_BACKEND_ID, DEMO_BACKEND_REVIEW } from '@/mocks/demoBackend'
import { DEMO_FRAUD_DETECT, DEMO_FRAUD_ID, DEMO_FRAUD_REVIEW } from '@/mocks/demoFraud'
import { DEMO_GO_WEAK_DETECT, DEMO_GO_WEAK_ID, DEMO_GO_WEAK_REVIEW } from '@/mocks/demoGoWeak'
import { DEMO_QA_DETECT, DEMO_QA_ID, DEMO_QA_REVIEW } from '@/mocks/demoQa'
import { DEMO_SYSDESIGN_DETECT, DEMO_SYSDESIGN_ID, DEMO_SYSDESIGN_REVIEW } from '@/mocks/demoSysdesign'
import {
  DEMO_RUBRIC,
  DEMO_RUBRIC_BACKEND,
  DEMO_RUBRIC_FRAUD,
  DEMO_RUBRIC_QA,
  DEMO_RUBRIC_SYSDESIGN,
} from '@/mocks/rubric'

const runs = new Map<string, Workspace>()

/** Записанный прогон в форме нынешнего ответа сервера.
 *
 *  Детектор переехал внутрь `ReviewResponse`, и демо обязано переехать вместе с
 *  ним: своя форма у записанных прогонов означала бы, что расхождение с
 *  сервером всплывёт только на живом ключе. Снимки лежат отдельными файлами
 *  (`/review` и `/detect` записывались по отдельности), поэтому отчёт
 *  подставляется здесь. */
function recorded(review: ReviewResponse, detect: DetectResponse): ReviewResponse {
  return { ...review, detection: detect.report }
}

/** Записанный прогон и его место в каталоге.
 *
 *  Раньше связь жила двумя отдельными объектами — курс → прогон и рубрика →
 *  прогон, — и это молча запрещало второй прогон по той же рубрике. Прогонов по
 *  `go-task1` теперь два: собранное методистом хорошее решение и настоящая
 *  слабая сдача. Поэтому связь стала списком, а обе карты выводятся из него:
 *  по ключу выигрывает первый подходящий прогон, остальные остаются доступны по
 *  прямой ссылке и через `demoRuns()`. */
export interface DemoRunInfo {
  id: string
  /** `Course.id` из `mocks/programs.ts`. */
  courseId: string
  /** `Rubric.assignment_id` — то, что лежит в `backend/rubrics/`. */
  rubricId: string
  title: string
  /** Одна строка о том, чего не показывает ни один другой прогон. */
  note: string
}

const DEMO_RUNS: DemoRunInfo[] = [
  {
    id: DEMO_RUN_ID,
    courseId: 'go',
    rubricId: 'go-task1',
    title: 'Go — boilerplate сервиса, хорошее решение',
    note: '8 из 10, зачёт; необъявленный ИИ в README',
  },
  {
    id: DEMO_SYSDESIGN_ID,
    courseId: 'system-design',
    rubricId: 'sysdesign-lab1',
    title: 'Системный дизайн — архитектурное описание',
    note: '4 из 6 — ровно порог зачёта',
  },
  {
    id: DEMO_BACKEND_ID,
    courseId: 'backend',
    rubricId: 'backend-task1',
    title: 'Backend — обработчик predict и тесты',
    note: '6.5 сырых → 5.5 после штрафа за просрочку',
  },
  {
    id: DEMO_QA_ID,
    courseId: 'qa',
    rubricId: 'qa-task1',
    title: 'Tech QA — таблица тест-кейсов',
    note: 'шкала на 20 баллов, порога зачёта нет, весь Format Gate без ответа',
  },
  {
    id: DEMO_FRAUD_ID,
    courseId: 'fraud',
    rubricId: 'fraud-task1',
    title: 'Фрод — карта рисков продукта',
    note: 'необъявленный ИИ: сигнал есть, декларации нет; работа доступна не целиком',
  },
  {
    id: DEMO_GO_WEAK_ID,
    courseId: 'go',
    rubricId: 'go-task1',
    title: 'Go — настоящее слабое решение',
    note: '7 из 10 при пороге 6 — и всё равно незачёт по обязательному минимуму',
  },
]

runs.set(DEMO_RUN_ID, {
  ...buildWorkspace(DEMO_RUN_ID, recorded(DEMO_REVIEW, DEMO_DETECT), DEMO_RUBRIC),
  live: false,
})
runs.set(DEMO_SYSDESIGN_ID, {
  ...buildWorkspace(
    DEMO_SYSDESIGN_ID,
    recorded(DEMO_SYSDESIGN_REVIEW, DEMO_SYSDESIGN_DETECT),
    DEMO_RUBRIC_SYSDESIGN,
  ),
  live: false,
})
runs.set(DEMO_BACKEND_ID, {
  ...buildWorkspace(
    DEMO_BACKEND_ID,
    recorded(DEMO_BACKEND_REVIEW, DEMO_BACKEND_DETECT),
    DEMO_RUBRIC_BACKEND,
  ),
  live: false,
})
runs.set(DEMO_QA_ID, {
  ...buildWorkspace(DEMO_QA_ID, recorded(DEMO_QA_REVIEW, DEMO_QA_DETECT), DEMO_RUBRIC_QA),
  live: false,
})
runs.set(DEMO_FRAUD_ID, {
  ...buildWorkspace(DEMO_FRAUD_ID, recorded(DEMO_FRAUD_REVIEW, DEMO_FRAUD_DETECT), DEMO_RUBRIC_FRAUD),
  live: false,
})
runs.set(DEMO_GO_WEAK_ID, {
  ...buildWorkspace(
    DEMO_GO_WEAK_ID,
    recorded(DEMO_GO_WEAK_REVIEW, DEMO_GO_WEAK_DETECT),
    DEMO_RUBRIC,
  ),
  live: false,
})

/** Первый прогон, подходящий по ключу. `Object.fromEntries` оставляет
 *  последнее совпадение, поэтому список разворачивается: выигрывает тот, кто
 *  записан раньше. */
function firstBy(key: (run: DemoRunInfo) => string): Record<string, string> {
  return Object.fromEntries([...DEMO_RUNS].reverse().map((run) => [key(run), run.id]))
}

/** Демо-разбор есть только там, где есть рубрика: показывать разбор работы по
 *  Tech QA против рубрики по Go — хуже, чем не показывать ничего. Курс, до
 *  которого прогон не записан, обязан отсутствовать в карте: `null` из
 *  `demoRunForCourse` — единственный признак «разбора нет». */
const DEMO_BY_COURSE: Record<string, string> = firstBy((run) => run.courseId)

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
        'Ближайший кандидат — «Прохождение тестов»: там 0.5 из-за одного упавшего теста, где ожидание 400 разошлось с 422 от pydantic. Это ошибка в тесте, а не в сервисе. По букве рубрики градация 0.5 стоит верно; поднимать до 1 — уже решение куратора о том, считать ли расхождение существенным.',
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
  [DEMO_QA_ID]: [
    {
      id: 'm1',
      author: 'human',
      text: 'Гейт весь в вопросительных знаках. Формат-то нарушен или нет?',
    },
    {
      id: 'm2',
      author: 'ai',
      text:
        'Нарушен, но сказал об этом не гейт. Обработчиков test_case_count, required_columns, column_empty и sharing_access в коде нет, поэтому все четыре блокирующих правила вернулись без ответа. По самой таблице: столбец «Статус» заполнен — Pass, Failed и девятнадцать To Do, — хотя условие требует оставить его пустым, а столбца «Предусловия» в шапке нет вовсе. Оба факта в вердикте по c5, там стоит 0 из 2. Количество при этом ровно 21 и ровно по три на функционал — это как раз в порядке.',
    },
  ],
  [DEMO_FRAUD_ID]: [
    {
      id: 'm1',
      author: 'human',
      text: 'На чём держится вывод про необъявленный ИИ, если два сигнала из четырёх молчат?',
    },
    {
      id: 'm2',
      author: 'ai',
      text:
        'На стилометрии (0.74) и модели-судье (0.69); форензика и перплексия недоступны, их вес перераспределён между этими двумя. Спаны показывают, за что именно: раздел рисков — двадцать три строки одной формы «N. Название. Описание. Тип риска: …», приоритизация — три блока, совпадающих по строению до знака. Против этого работает опечатка «размещение ставкию» в середине самого ровного абзаца: текст правился человеком. Декларации в работе нет, а условие её требует, — отсюда mismatch. Балла это не меняет: сигнал рекомендательный, и часть работы лежит во внешней таблице, которую разбор не видел.',
    },
  ],
  [DEMO_GO_WEAK_ID]: [
    {
      id: 'm1',
      author: 'human',
      text: 'Семь баллов при пороге шесть — почему тогда незачёт?',
    },
    {
      id: 'm2',
      author: 'ai',
      text:
        'Из-за обязательного минимума по c4: там 0.5 при минимуме 1, и такой провал даёт незачёт независимо от суммы. Балл стоит не за формулировку в логе, а за то, что штатная остановка считается ошибкой: ListenAndServe возвращает http.ErrServerClosed, код сравнивает её с context.Canceled и уходит в log.Fatalf — процесс умирает через os.Exit(1) раньше Shutdown, и ни один defer не отрабатывает. Поднимать до 1 я бы не стал: критерий требует завершения через Shutdown, а его в этом сценарии не происходит.',
    },
  ],
}

/** Демо-прогон, собранный против этой рубрики. */
const DEMO_BY_RUBRIC: Record<string, string> = firstBy((run) => run.rubricId)

/** Все записанные прогоны в порядке регистрации — включая те, что проиграли
 *  ключ в картах выше и доступны только по прямой ссылке. */
export function demoRuns(): DemoRunInfo[] {
  return DEMO_RUNS
}

/** Записанный разбор против **этой** рубрики, иначе `null`.
 *
 *  Подставлять чужой прогон нельзя: разбор сервиса на Go рядом с выбранной
 *  рубрикой по LLM выглядит правдоподобно и потому особенно врёт. Пока рубрик
 *  было три и прогонов три, эта ветка не срабатывала; теперь записанный разбор
 *  есть у пяти рубрик из тринадцати. */
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
  rubricId: string
  deadlineAt?: string
  studentInternalId?: string
  studentName?: string
  withDetection: boolean
}

/** Один вызов на оба разбора.
 *
 *  Раньше `/review` и `/detect` тянули pull request каждый сам: двойной расход
 *  лимита GitHub и, если студент пушнул между вызовами, спаны детектора
 *  описывали другую ревизию, чем цитаты черновика. `with_detection` делает это
 *  одним прогоном на общих `bundle` и `texts`.
 *
 *  Сбой детектора здесь больше не ловится: он не роняет ревью на сервере и
 *  приходит отчётом с причиной в `limitations`. Отсутствие отчёта означает
 *  ровно одно — его не просили. */
export async function startRun(params: StartRunParams): Promise<Workspace> {
  const rubric: Rubric = await backend.rubric(params.rubricId)

  const review = await backend.review({
    link: params.link,
    source: 'github_pr',
    deadline_at: params.deadlineAt || null,
    student_internal_id: params.studentInternalId || null,
    student_name: params.studentName || null,
    rubric_id: params.rubricId,
    condition_text: '',
    gate_facts: [],
    with_detection: params.withDetection,
  })

  const id = `run-${Date.now().toString(36)}`
  const workspace = buildWorkspace(id, review, rubric)
  runs.set(id, workspace)

  return workspace
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
