/** Учебные программы Авито — по материалам организаторов.
 *
 *  Источник: репозиторий ai-talent-hub-avito/homework_examples. Названия
 *  заданий, шкалы, дедлайны и каналы сдачи взяты из условий, а не придуманы:
 *  на одной программе баллов в условии нет вовсе (Go — шкалу задаёт методист),
 *  на другой их 20 (Tech QA), у третьей две лабы на 6 и 10 баллов.
 *
 *  Размеры групп там, где они видны в Stepik («верно решили N учащихся»),
 *  проставлены настоящие: 22 у фрода, 38 у бизнес-моделей, 49 у Tech QA.
 */

export type Channel = 'github_pr' | 'github_commit' | 'doc' | 'sheet' | 'notebook' | 'board'

export const CHANNEL_LABEL: Record<Channel, string> = {
  github_pr: 'pull request',
  github_commit: 'ссылка на коммит',
  doc: 'документ',
  sheet: 'таблица',
  notebook: 'ноутбук',
  board: 'доска',
}

export interface ProgramTask {
  code: string
  title: string
  maxScore: number
  /** Порог зачёта, если он назван в условии. */
  passThreshold: number
  step: number
  /** Дедлайн из условия в виде «ММ-ДД». Там, где срока в условии нет, — null. */
  deadline: string | null
  channel: Channel
  /** Оценка трудоёмкости разбора одной работы, минуты. */
  reviewMinutes: number
  /** «Если вы использовали ИИ — укажите это в работе». */
  declareAi: boolean
}

export interface Program {
  id: string
  short: string
  title: string
  subtitle: string
  /** Сколько человек в потоке. Где видно из Stepik — настоящее число. */
  cohort: number
  /** Досдача: сколько дней и почём. По условиям продуктовых программ —
   *  один день со штрафом в балл, дальше ноль. */
  graceDays: number
  penaltyPerDay: number
  /** «Проверка начинается после окончания дедлайна и занимает не более N дней». */
  reviewWindowDays: number | null
  tasks: ProgramTask[]
}

export const PROGRAMS: Program[] = [
  {
    id: 'go',
    short: 'Разработка на Go',
    title: 'Разработка сервиса на Go',
    subtitle: 'Три этапа одной работы: boilerplate, база и CRUD, слои и интерфейсы',
    cohort: 26,
    graceDays: 1,
    penaltyPerDay: 1,
    reviewWindowDays: 7,
    tasks: [
      { code: 'Этап 1', title: 'Создание boilerplate сервиса, поднятие веб-сервера', maxScore: 10, passThreshold: 6, step: 0.5, deadline: null, channel: 'github_pr', reviewMinutes: 18, declareAi: false },
      { code: 'Этап 2', title: 'Подключение базы данных и CRUD API', maxScore: 10, passThreshold: 6, step: 0.5, deadline: null, channel: 'github_pr', reviewMinutes: 25, declareAi: false },
      { code: 'Этап 3', title: 'Архитектура, зависимости и интерфейсы', maxScore: 10, passThreshold: 6, step: 0.5, deadline: null, channel: 'github_pr', reviewMinutes: 22, declareAi: false },
    ],
  },
  {
    id: 'system-design',
    short: 'Системный дизайн',
    title: 'Системный дизайн',
    subtitle: 'Две лабораторные на разных шкалах: 6 баллов и 10',
    cohort: 24,
    graceDays: 1,
    penaltyPerDay: 1,
    reviewWindowDays: 7,
    tasks: [
      { code: 'Лаба 1', title: 'Декомпозиция, интерфейсы и контракты, диаграммы C4', maxScore: 6, passThreshold: 4, step: 0.5, deadline: null, channel: 'doc', reviewMinutes: 30, declareAi: false },
      { code: 'Лаба 2', title: 'Масштабирование, отказоустойчивость, SLI и SLO', maxScore: 10, passThreshold: 6, step: 0.5, deadline: null, channel: 'doc', reviewMinutes: 35, declareAi: false },
    ],
  },
  {
    id: 'analytics',
    short: 'Аналитика данных',
    title: 'Аналитика данных',
    subtitle: 'Два блока: метрики и продуктовые кейсы',
    cohort: 31,
    graceDays: 1,
    penaltyPerDay: 1,
    reviewWindowDays: 7,
    tasks: [
      { code: 'ДЗ 1', title: 'Разбор воронки и метрик нового продукта', maxScore: 10, passThreshold: 6, step: 1, deadline: null, channel: 'doc', reviewMinutes: 25, declareAi: false },
      { code: 'ДЗ 2', title: 'Целевые, прокси и контр-метрики новой фичи', maxScore: 10, passThreshold: 6, step: 1, deadline: null, channel: 'doc', reviewMinutes: 20, declareAi: false },
      { code: 'ДЗ 3', title: 'Кейс: падение ROMI во вторичном жилье', maxScore: 10, passThreshold: 6, step: 1, deadline: null, channel: 'board', reviewMinutes: 45, declareAi: false },
      { code: 'ДЗ 4', title: 'Кейс: take-rate вертикали Авто', maxScore: 10, passThreshold: 6, step: 1, deadline: null, channel: 'board', reviewMinutes: 45, declareAi: false },
      { code: 'ДЗ 5', title: 'Кейс: запуск конкурентной аналитики', maxScore: 10, passThreshold: 6, step: 1, deadline: null, channel: 'board', reviewMinutes: 50, declareAi: false },
    ],
  },
  {
    id: 'mlsd',
    short: 'Трекинг экспериментов',
    title: 'МЛСД: трекинг экспериментов',
    subtitle: 'MLflow, двадцать прогонов и воспроизводимость лучшего',
    cohort: 19,
    graceDays: 1,
    penaltyPerDay: 1,
    reviewWindowDays: 7,
    tasks: [
      { code: 'ДЗ 1', title: 'Серия экспериментов с логированием в MLflow', maxScore: 10, passThreshold: 6, step: 1, deadline: null, channel: 'notebook', reviewMinutes: 55, declareAi: false },
    ],
  },
  {
    id: 'gpu',
    short: 'GPU и распредвычисления',
    title: 'GPU и распределённые вычисления',
    subtitle: 'Расчётный кейс: экономика ML-платформы на Kubernetes',
    cohort: 17,
    graceDays: 1,
    penaltyPerDay: 1,
    reviewWindowDays: 7,
    tasks: [
      { code: 'Кейс', title: 'Эволюция ML-платформы: стоимость, эффективность, окупаемость', maxScore: 10, passThreshold: 6, step: 1, deadline: null, channel: 'doc', reviewMinutes: 40, declareAi: false },
    ],
  },
  {
    id: 'llm',
    short: 'LLM',
    title: 'LLM-инженерия',
    subtitle: 'Мини-претрейн: чем ниже итоговый loss, тем выше балл',
    cohort: 21,
    graceDays: 3,
    penaltyPerDay: 1,
    reviewWindowDays: 7,
    tasks: [
      { code: 'ДЗ 1', title: 'Pretrain: датасет, обучение и исследовательский отчёт', maxScore: 10, passThreshold: 6, step: 1, deadline: '10-20', channel: 'github_pr', reviewMinutes: 50, declareAi: false },
    ],
  },
  {
    id: 'backend',
    short: 'Основы backend',
    title: 'Основы backend-разработки',
    subtitle: 'FastAPI-сервис модерации объявлений и тесты к нему',
    cohort: 28,
    graceDays: 1,
    penaltyPerDay: 1,
    reviewWindowDays: 7,
    tasks: [
      { code: 'ДЗ 1', title: 'Основы веб-разработки: обработчик predict и тесты', maxScore: 10, passThreshold: 6, step: 0.5, deadline: null, channel: 'github_commit', reviewMinutes: 15, declareAi: false },
    ],
  },
  {
    id: 'product',
    short: 'Продуктовый менеджмент',
    title: 'Продуктовый менеджмент',
    subtitle: 'От анализа внешней среды до критериев успеха пилота',
    cohort: 34,
    graceDays: 1,
    penaltyPerDay: 1,
    reviewWindowDays: 7,
    tasks: [
      { code: 'ДЗ 1', title: 'Анализ внешней среды продукта', maxScore: 10, passThreshold: 6, step: 0.5, deadline: '02-21', channel: 'doc', reviewMinutes: 40, declareAi: true },
      { code: 'ДЗ 2', title: 'Дизайн А/Б-теста', maxScore: 10, passThreshold: 6, step: 0.5, deadline: '10-21', channel: 'doc', reviewMinutes: 25, declareAi: false },
      { code: 'ДЗ 3', title: 'План и проведение количественного исследования', maxScore: 10, passThreshold: 6, step: 0.5, deadline: '10-23', channel: 'doc', reviewMinutes: 45, declareAi: false },
      { code: 'ДЗ 4', title: 'Оценка затрат на реализацию: PnL до EBITDA', maxScore: 10, passThreshold: 6, step: 0.5, deadline: '05-24', channel: 'sheet', reviewMinutes: 50, declareAi: true },
      { code: 'ДЗ 5', title: 'Проверка гипотез, метрики и критерии успеха', maxScore: 10, passThreshold: 6, step: 0.5, deadline: '10-14', channel: 'doc', reviewMinutes: 35, declareAi: false },
    ],
  },
  {
    id: 'business-models',
    short: 'Бизнес-модели',
    title: 'Продуктовые бизнес-модели',
    subtitle: 'Трекшн-модель и расчёт baseline на пять лет',
    cohort: 38,
    graceDays: 1,
    penaltyPerDay: 1,
    reviewWindowDays: 7,
    tasks: [
      { code: 'ДЗ 1', title: 'Расчёт baseline', maxScore: 10, passThreshold: 6, step: 0.5, deadline: '02-19', channel: 'sheet', reviewMinutes: 40, declareAi: true },
    ],
  },
  {
    id: 'fraud',
    short: 'Борьба с мошенничеством',
    title: 'Технологии борьбы с мошенничеством',
    subtitle: 'Карта рисков продукта и ROI митигации',
    cohort: 22,
    graceDays: 1,
    penaltyPerDay: 1,
    reviewWindowDays: 7,
    tasks: [
      { code: 'ДЗ 1', title: 'Карта рисков продукта', maxScore: 10, passThreshold: 6, step: 0.5, deadline: '02-09', channel: 'doc', reviewMinutes: 30, declareAi: true },
    ],
  },
  {
    id: 'qa',
    short: 'Tech QA',
    title: 'Tech QA',
    subtitle: 'Анализ требований и тест-документация, шкала на 20 баллов',
    cohort: 49,
    graceDays: 1,
    penaltyPerDay: 1,
    reviewWindowDays: null,
    tasks: [
      { code: 'ДЗ 1', title: 'Анализ требований и создание тест-документации', maxScore: 20, passThreshold: 12, step: 0.5, deadline: null, channel: 'sheet', reviewMinutes: 35, declareAi: false },
    ],
  },
]
