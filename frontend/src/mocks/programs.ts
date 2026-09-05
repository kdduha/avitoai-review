/** Учебные программы Авито — по материалам организаторов.
 *
 *  Источник: репозиторий ai-talent-hub-avito/homework_examples. Названия
 *  заданий, нумерация, шкалы, каналы сдачи, дедлайны и правила досдачи взяты
 *  из условий, а не придуманы.
 *
 *  Здесь все одиннадцать направлений репозитория. Директорий в нём девять, но
 *  `data_science/` — это четыре разных курса (MLSD, LLM, основы backend, GPU),
 *  поэтому курсов одиннадцать. Домашних работ в репозитории двадцать, а
 *  заданий здесь двадцать два: единственная работа по Go состоит из трёх
 *  этапов, которые сдаются и проверяются по отдельности.
 *
 *  Чего в материалах нет — того нет и здесь:
 *  - порог зачёта назван только у системного дизайна (4 из 6 и 6 из 10),
 *    у остальных `passThreshold: null`;
 *  - дробный шаг назван только у системного дизайна и у основ backend
 *    («0.5 балла — тесты запускаются, но не все проходят»), у остальных шаг 1;
 *  - дедлайны и правила досдачи есть только у продуктовых направлений
 *    (`product`, `business-models`, `fraud`), у остальных `deadline: null` и
 *    `graceDays: null` — срок назначает методист;
 *  - блок «Работа с ИИ-инструментами» есть ровно у четырёх заданий:
 *    product ДЗ №1 и ДЗ №4, product_fraud, product_business_models.
 *
 *  Оценочные (не взятые из материалов) величины ровно две, и обе помечены
 *  ниже по месту: `reviewMinutes` — прогноз трудоёмкости разбора, и `cohort`
 *  там, где размер группы нигде не назван. Настоящие размеры групп известны
 *  для трёх курсов из счётчика Stepik «верно решили N учащихся»: Tech QA — 49,
 *  продуктовые бизнес-модели — 38, антифрод — 22.
 */

export type Channel =
  | 'github_pr'
  | 'github_commit'
  | 'github_folder'
  | 'git_markdown'
  | 'notebook_mlflow'
  | 'doc'
  | 'gdoc'
  | 'gsheet'
  | 'board'
  | 'unspecified'

export const CHANNEL_LABEL: Record<Channel, string> = {
  github_pr: 'pull request в GitHub',
  github_commit: 'ссылка на коммит',
  github_folder: 'ссылка на папку в репозитории',
  git_markdown: 'единый Markdown в git-репозитории',
  notebook_mlflow: 'ноутбук и ссылка на MLflow-эксперимент',
  doc: 'единый документ: PDF, DOCX или Markdown',
  gdoc: 'Google Документ с доступом на редактирование',
  gsheet: 'Google Таблица с доступом на редактирование',
  board: 'Boardmix-доска или Google Документ',
  unspecified: 'канал в условии не назван',
}

export interface ProgramTask {
  /** Настоящий номер задания. У `product` нумерация директорий репозитория с
   *  ней не совпадает («Пример ДЗ 1» — это ДЗ №5), здесь стоят настоящие. */
  code: string
  title: string
  maxScore: number
  /** Порог зачёта — только там, где он назван в условии. Иначе null. */
  passThreshold: number | null
  /** Шаг шкалы. 0.5 — только системный дизайн и основы backend. */
  step: number
  /** Дедлайн из условия в виде «ММ-ДД». Там, где срока в условии нет, — null:
   *  срок назначает методист, и выдумывать его за него мы не будем. */
  deadline: string | null
  channel: Channel
  /** ОЦЕНКА: прогноз трудоёмкости разбора одной работы, минуты. В материалах
   *  таких чисел нет, есть только «ориентировочное время выполнения». */
  reviewMinutes: number
  /** В условии есть блок «Работа с ИИ-инструментами»: «Если вы использовали
   *  ИИ — укажите это в работе и опишите, как именно». */
  declareAi: boolean
}

export interface Program {
  id: string
  short: string
  title: string
  subtitle: string
  /** Каталог организаторов: имя директории в homework_examples. */
  sourceDir: string
  /** Сколько человек в потоке. */
  cohort: number
  /** true — число из Stepik («верно решили N учащихся»); false — ОЦЕНКА. */
  cohortIsReal: boolean
  /** Досдача: сколько дней и почём. Правило названо только у продуктовых
   *  направлений — «досдать в течение 1 дня со штрафом –1 балл, позже 0».
   *  Где правила нет — null, и просрочка не штрафуется. */
  graceDays: number | null
  penaltyPerDay: number | null
  /** «Проверка начинается после окончания дедлайна и занимает не более N
   *  дней». Тоже только у продуктовых. */
  reviewWindowDays: number | null
  /** У продуктовых бизнес-моделей в условии — «не более 7 рабочих дней». */
  reviewWindowInBusinessDays?: boolean
  tasks: ProgramTask[]
}

export const PROGRAMS: Program[] = [
  {
    id: 'backend',
    short: 'Основы backend',
    title: 'Основы backend-разработки',
    subtitle: 'FastAPI-сервис модерации объявлений и тесты к нему',
    sourceDir: 'data_science',
    cohort: 28,
    cohortIsReal: false,
    graceDays: null,
    penaltyPerDay: null,
    reviewWindowDays: null,
    tasks: [
      /* Шаг 0.5 — из критерия 6: «0.5 балла — тесты запускаются, но не все проходят». */
      { code: 'ДЗ 1', title: 'Основы веб-разработки: обработчик predict и тесты', maxScore: 10, passThreshold: null, step: 0.5, deadline: null, channel: 'github_commit', reviewMinutes: 15, declareAi: false },
    ],
  },
  {
    id: 'go',
    short: 'Разработка на Go',
    title: 'Разработка сервиса на Go',
    subtitle: 'Три этапа одной работы: boilerplate, база и CRUD, слои и интерфейсы',
    sourceDir: 'GO',
    cohort: 26,
    cohortIsReal: false,
    graceDays: null,
    penaltyPerDay: null,
    reviewWindowDays: null,
    tasks: [
      /* В task1–task3.md нет ни шкалы, ни критериев, ни порога: ревью в GO
         текстовое, списком рекомендаций в комментарии к PR. Максимум 10 взят
         из рубрики `backend/rubrics/go-task1.json`, порога нет. */
      { code: 'Этап 1', title: 'Создание boilerplate сервиса, поднятие веб-сервера', maxScore: 10, passThreshold: null, step: 1, deadline: null, channel: 'github_pr', reviewMinutes: 18, declareAi: false },
      { code: 'Этап 2', title: 'Подключение базы данных и CRUD API', maxScore: 10, passThreshold: null, step: 1, deadline: null, channel: 'github_pr', reviewMinutes: 25, declareAi: false },
      { code: 'Этап 3', title: 'Архитектура, зависимости и интерфейсы', maxScore: 10, passThreshold: null, step: 1, deadline: null, channel: 'github_pr', reviewMinutes: 22, declareAi: false },
    ],
  },
  {
    id: 'fraud',
    short: 'Антифрод',
    title: 'Технологии борьбы с мошенничеством',
    subtitle: 'Карта рисков по этапам CJM, матрица «вероятность × влияние», ROI митигации',
    sourceDir: 'product_fraud',
    cohort: 22,
    cohortIsReal: true,
    graceDays: 1,
    penaltyPerDay: 1,
    reviewWindowDays: 7,
    tasks: [
      { code: 'ДЗ №1', title: 'Карта рисков продукта', maxScore: 10, passThreshold: null, step: 1, deadline: '02-09', channel: 'gdoc', reviewMinutes: 30, declareAi: true },
    ],
  },
  {
    id: 'system-design',
    short: 'Системный дизайн',
    title: 'Системный дизайн',
    subtitle: 'Две лабораторные на разных шкалах: 6 баллов с зачётом от 4 и 10 с зачётом от 6',
    sourceDir: 'system_design',
    cohort: 24,
    cohortIsReal: false,
    graceDays: null,
    penaltyPerDay: null,
    reviewWindowDays: null,
    tasks: [
      /* Единственное направление, где порог зачёта назван в условии: в таблице
         критериев есть колонка «Мин. балл», её сумма и есть порог. */
      { code: 'Лаба 1', title: 'Декомпозиция, интерфейсы и контракты, диаграммы C4', maxScore: 6, passThreshold: 4, step: 0.5, deadline: null, channel: 'doc', reviewMinutes: 30, declareAi: false },
      { code: 'Лаба 2', title: 'Масштабирование, отказоустойчивость, SLI и SLO', maxScore: 10, passThreshold: 6, step: 0.5, deadline: null, channel: 'git_markdown', reviewMinutes: 35, declareAi: false },
    ],
  },
  {
    id: 'qa',
    short: 'Tech QA',
    title: 'Tech QA',
    subtitle: 'Анализ требований и тест-документация: ровно 21 тест-кейс, шкала на 20 баллов',
    sourceDir: 'tech_QA',
    cohort: 49,
    cohortIsReal: true,
    graceDays: null,
    penaltyPerDay: null,
    reviewWindowDays: null,
    tasks: [
      /* Сдаётся Google Таблица с доступом «Комментатор» — единственное место,
         где условие требует именно комментирования, а не редактирования. */
      { code: 'ДЗ №1', title: 'Анализ требований и создание тест-документации', maxScore: 20, passThreshold: null, step: 1, deadline: null, channel: 'gsheet', reviewMinutes: 35, declareAi: false },
    ],
  },
]
