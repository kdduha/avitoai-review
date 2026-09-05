# backend — avito-reviewer

Передача работы: **[handover-backend.md](handover-backend.md)** — что готово,
что нет и на чём здесь спотыкаются.

Единый модульный сервис: FastAPI + uv, Python 3.11.

## Запуск

```bash
cd backend
uv sync
uv run uvicorn avito_reviewer.app.main:app --reload   # http://localhost:8000/docs
uv run pytest                                         # тесты
uv run python scripts/ingest_pr_example.py            # разбор реального PR

docker compose up --build                             # из корня репозитория: postgres, redis,
                                                        # backend, worker, frontend — всё вместе
```

Локально без docker-compose нужен свой Postgres и Redis (или sqlite для
разработки — `DB_DSN=sqlite+aiosqlite:///./dev.db`, Redis нужен только для
`POST .../review/rerun`, остальное работает без него).

Конфиг — переменные окружения `INGEST_*`, `AI_*`, `DB_*`, `AUTH_*`, `QUEUE_*`
(см. `avito_reviewer/config.py`), `LOG_LEVEL` (по умолчанию `INFO`). Без ключей
приложение стартует на провайдере `fake`: конвейер проходится целиком, но
заглушке нечего ответить — черновик приходит с пометкой «оценить вручную».
Готовый черновик без ключа показывает `scripts/demo.py`, который подставляет
ответы, собранные из строк самой работы.

При старте приложение прогоняет миграции Alembic до `head` (`db/migrate.py`,
`migrations/`) и сеет три хардкод-аккаунта, один на роль:
`student` / `reviewer` / `admin`, пароль — `AUTH_SEED_PASSWORD`
(по умолчанию `avito2026`). `POST /auth/login` меняет логин на JWT; всё, кроме
`/health`, `/init` и `/auth/login`, требует `Authorization: Bearer <token>`.
Управление остальными аккаунтами — `GET/POST/PATCH/DELETE /users` (admin-only,
см. «Эндпоинты» ниже).

Новая ревизия схемы — `alembic revision --autogenerate -m "..."` из `backend/`
(`sqlalchemy.url` в `alembic.ini` не прописан статикой — `migrations/env.py`
берёт его из `DatabaseConfig`, так что миграции идут по тому же DSN, что и
приложение). Воркер тоже прогоняет `run_migrations()` при старте — идемпотентно,
как страховка на случай, если он поднялся раньше веб-процесса.

При `AI_LLM__PROVIDER=local` внешнего провайдера нет вовсе: задачи с маршрутом
«наружу после скраба» считаются локально, и понижение маршрута видно в аудите.

Живой прогон — через `.env` (`cp .env.example .env`, файл под gitignore):

```bash
AI_LLM__PROVIDER=external                      # любой OpenAI-совместимый эндпоинт
AI_LLM__BASE_URL=https://api.aitunnel.ru/v1
AI_LLM__MODEL=deepseek-v4-flash
AI_LLM__API_KEY=...

AI_LLM__PROVIDER=local                         # локальный контур целиком
AI_LLM__FORCE_LOCAL=true                       # аварийный тумблер

# Матрица роутинга (§8.3): задаче — своя модель. Пусто — модель провайдера.
AI_LLM__TASK_MODELS={"compile": "gpt-5.6-luna-pro"}
```

Смена провайдера — три поля, а не новый код: локальный сервинг, aitunnel и
OpenRouter говорят на одном протоколе, и клиент у них общий. В журнале шлюза
эндпоинт подписан по хосту, иначе в отчёте о стоимости все внешние вызовы
выглядят одинаково.

## Эндпоинты

RBAC — лестница `student < reviewer < admin`, каждая ручка требует свой
минимум роли (🔒 = нужен bearer-токен, без пометки — публично). Роли
«куратор» и «методист» из архитектуры слиты в одну — `admin`: в
хакатон-варианте с тремя сеяными аккаунтами разделять их незачем, разводить
руками некому.

**Аутентификация**
- `POST /auth/login` — `{username, password}` → `{access_token, role, ...}`.
  Три сеяных логина, один пароль (`AUTH_SEED_PASSWORD`)
- `GET /me` 🔒 любая роль — кто владеет токеном
- `GET /users`, `POST /users`, `GET/PATCH/DELETE /users/{id}` 🔒 admin+ —
  управление аккаунтами: заводить ревьюеров, менять роль/пароль, удалять.
  Удаление блокируется (`409`), пока за пользователем числятся сдачи (сам
  проверял или утверждал) — сначала переназначить (`reassign`); удаление и
  разжалование `409`-ится и на последнем оставшемся `admin` — сидинг заполняет
  только пустую таблицу, рестарт его не восстановит

**Разбор сдачи**
- `GET /health`, `GET /init` — liveness и статус бутстрапа: провайдеры ingest,
  маршрут модели, рубрики
- `POST /ingest` 🔒 reviewer+ — `{link, source, assignment_id?, deadline_at?}`
  → `SubmissionBundle`
- `GET /rubrics`, `GET /rubrics/{assignment_id}` 🔒 reviewer+ — каталог рубрик
- `POST /rubrics/compile`, `POST /rubrics` 🔒 admin — условие → черновик
  рубрики → подтверждение (см. «Какой моделью что считать» ниже)
- `DELETE /rubrics/{assignment_id}` 🔒 admin — снять рубрику из каталога
- `POST /review` 🔒 reviewer+ — `{link, rubric_id | rubric, gate_facts?,
  condition_text?, with_detection?, reviewer_username?}` → `{bundle, files,
  draft, detection?, submission_id}`. Сохраняет `Submission`: ревьюер = вызвавший,
  если не указан `reviewer_username` (только admin может назначить
  другого). `with_detection: true` заодно прогоняет детектор на тех же
  `bundle`/`texts` — без второго похода к источнику сдачи
- `POST /detect` 🔒 reviewer+ — `{link, rubric_id?}` → `{bundle, files,
  report}`: разовый прогон, ничего не сохраняет
- `GET /cost`, `GET /audit/llm-calls` 🔒 admin — журнал шлюза: сводка и
  построчно

**Персистентные сдачи** (`Submission` — см. `db/models.py`)
- `GET /me/queue` 🔒 reviewer+ — своя очередь; `?all=true` для admin
- `GET /submissions/{id}` 🔒 reviewer+ (только свои для reviewer) — карточка целиком,
  включая `rubric` — снимок рубрики на момент разбора (`Submission.rubric_snapshot`),
  не текущий каталог, чтобы клиент мог честно отрисовать критерии в обход
  `/review`, которого для этой сдачи он не звал
- `GET /submissions/{id}/artifacts/{path}` 🔒 — текст одного файла как его видела модель
- `GET/PATCH /submissions/{id}/review` 🔒 — черновик; `PATCH` правит счёт/вердикт
  по критериям, пересчитывает итог (`review/aggregate.py`) и пишет
  `review_revisions` с авторством
- `POST /submissions/{id}/review/approve` 🔒 — `409`, если уже утверждена
- `POST /submissions/{id}/review/rerun` 🔒 — ставит `ANALYZING` и кладёт задачу в
  Redis/arq; `503`, если очередь недоступна (воркер: `uv run arq
  avito_reviewer.queue.WorkerSettings`)
- `GET /submissions/{id}/ai-detection`, `POST .../{span_id}/verdict` 🔒 —
  сохранённый отчёт и подтверждение/отклонение спана ревьюером (advisory,
  на балл не влияет — работает и после утверждения сдачи)
- `POST /submissions/{id}/reassign` 🔒 admin — передать сдачу другому ревьюеру
- `DELETE /submissions/{id}` 🔒 admin — удалить сдачу целиком (каскадом —
  ревизии, сообщения чата)
- `GET /submissions/{id}/chat` 🔒 reviewer+ (только свои) — история разговора с
  моделью по этой сдаче
- `POST /submissions/{id}/chat` 🔒 reviewer+ (только свои) — `{message}` →
  SSE-поток (`text/event-stream`) сообщений хода: reply / вызовы тулов /
  предложенный патч (§6.3 архитектуры, детали — ниже)

`/review` и `/detect` сами тянут сдачу по ссылке: разложить на два вызова
значило бы дважды сходить в GitHub за одним и тем же. Рерун — исключение: он
переиспользует уже сохранённый `bundle` и не ходит за PR повторно.

### Чат ревьюера с моделью

`POST /submissions/{id}/chat` — SSE-транспорт, а не потоковая генерация токен
за токеном: сервер сперва досчитывает весь ход целиком (`ai/chat.py:run_chat`,
ReAct-цикл до `MAX_STEPS=4` обращений к `complete_json`), пишет каждый шаг в
`chat_messages`, и только потом отдаёт их как `data: {...}\n\n` — по одному
событию на шаг — с завершающим `event: done`. У модели нет нативного
function-calling у используемых провайдеров, поэтому вызов тула — это тоже
JSON, разобранный по ручной схеме в системном промпте `run_chat`, а не по
API-функциям.

Тулы модели — только чтение: `get_file`, `get_diff`, `get_criterion`,
`search_submission`. Единственное действие с побочным эффектом —
`propose_review_patch`: модель предлагает конкретную правку (критерий, балл,
вердикт, фидбек студенту), но не применяет её сама — цикл на этом
останавливается, и ревьюер применяет патч (или нет) отдельным вызовом
`PATCH /submissions/{id}/review`, как и любую другую свою правку. Так в
`review_revisions` не появляются записи с авторством `ai`, за которые никто не
расписался.

### Какой моделью что считать

Задачи разные по цене ошибки. Ревью идёт потоком — там решает стоимость. Rubric
Compiler считается один раз на задание, его результат подтверждает человек, а
ошибка тиражируется на весь поток — там решает устойчивость. Замер на одном и
том же условии: дешёвая модель дважды дала разный результат и один раз вернула
ноль критериев, сильная — шесть критериев со стопроцентным подтверждением
цитатами за 2 ₽. Отсюда матрица `AI_LLM__TASK_MODELS`, а не одна модель на всё.

## Демо и ручные скрипты

`scripts/` — ручные примеры и утилиты, не тесты и не часть пакета.

```bash
uv run python scripts/demo.py review     # записанный бандл, ключей не нужно
uv run python scripts/demo.py detect
```

По умолчанию берётся `scripts/fixtures/go-task1-pr42.json` — ровно та форма, что
отдаёт ingest на настоящем PR, включая крупный файл без инлайненного тела. Другие
источники (флаги идут до подкоманды):

```bash
git clone https://github.com/ai-talent-hub-avito/homework_examples.git
uv run python scripts/demo.py --repo "homework_examples/GO/Хорошее решение 1-3" review
uv run python scripts/demo.py --link https://github.com/owner/repo/pull/1 review
```

`scripts/local_bundle.py` собирает из каталога тот же `SubmissionBundle`, что отдал
бы провайдер, — демо идёт по настоящему пути, а не по параллельному. Провайдером
он не оформлен намеренно: заглушек под нереализованные источники в коде не держим.

`scripts/ingest_pr_example.py` прогоняет `ingest` на реальном GitHub PR и печатает
`SubmissionBundle` как JSON: изменение (`artifacts[].diff` + `changed_ranges` +
`excerpt`), историю коммитов, карту репозитория (`repo.files`).

```bash
uv run python scripts/ingest_pr_example.py
uv run python scripts/ingest_pr_example.py https://github.com/<owner>/<repo>/pull/<n>
```

Работает без токена (анонимный GitHub API, 60 запросов/час); `INGEST_GITHUB__TOKEN`
или `GITHUB_TOKEN` поднимают лимит. По умолчанию — `psf/requests#6951`: репозиторий
на ~130 файлов, так что `repo.truncated` остаётся `false`, а из трёх изменённых
файлов два попадают в `excerpt` целиком, а большой (42 КБ) едет diff-only.

## Структура

```
src/avito_reviewer/
  config.py              AppConfig — единая точка сборки: агрегирует IngestConfig /
                         AIConfig / DatabaseConfig / AuthConfig / QueueConfig
  logsetup.py            configure_logging(): один stderr-хендлер на дерево avito_reviewer
  queue.py                единственная очередь: arq-задача review/rerun + WorkerSettings
  db/                     users, submissions, review_revisions, chat_messages — SQLAlchemy 2 (async)
    models.py             Base, Role, SubmissionStatus, AuthorType, ChatRole, четыре таблицы
    session.py             engine/sessionmaker, FastAPI-зависимость
    migrate.py             run_migrations(): alembic upgrade head программно (лежит в lifespan)
  app/                   HTTP-слой
    main.py              create_app(): configure_logging, lifespan (миграции+ingest+seed), роутеры
    auth.py               JWT + RBAC: hash/verify, create/decode token, seed_users, require_role
    routers/             APIRouter по доменам: base, auth, ingest, review, submissions, users
    schemas/             Pydantic-модели запросов/ответов, по файлу на роутер
  ingest/                ссылка → SubmissionBundle
    service.py           IngestService: SubmissionSource → провайдер; резолвер content_ref
    models.py            SubmissionBundle и связанные модели — контракт для всех слоёв ниже
    diff.py              разбор unified diff (unidiff): изменённые строки и текст головы
    content.py           разбор ручек content_ref — схемы знает только ingest
    providers/github.py  единственный провайдер, клиент — githubkit
  ai/                    всё, что связано с моделями
    service.py           AIService: prepare (async) → review / detect (sync)
    content.py           тексты артефактов: excerpt | дозагрузка | дифф, флаг partial;
                         стриппинг ноутбуков (strip_notebook) для lang == "jupyter"
    rubric.py            схема рубрики, разбор JSON, реестр каталога
    compiler.py          условие задания → черновик рубрики с цитатами
    gate.py              формальные проверки рубрики без единого токена
    chat.py              ReAct-цикл чата ревьюера с моделью (§6.3): тулы read-only +
                         propose_review_patch, структурированный вывод вместо function-calling
    llm/                 PrivacyGateway — единственный выход к моделям
    review/              промпт из рубрики, валидатор цитат, агрегатор баллов
    detection/           ансамбль сигналов ГенИИ + signals/
rubrics/                 рубрики как данные: добавить курс = добавить JSON
migrations/              Alembic (async шаблон); env.py берёт DSN из DatabaseConfig
scripts/                 ручные примеры и демо (не тесты)
tests/                   pytest; factories.py строит настоящие модели, не двойники
```

### Границы

`ai` работает только с `SubmissionBundle` и `Rubric` — про источник сдачи он не
знает ничего, эта зависимость заперта в `ingest`. Обратно: схемы `content_ref`
разбирает только `ingest`, а `ai` ходит за телами файлов через протокол
`ContentResolver`, которому `IngestService` удовлетворяет структурно.

Наружу к моделям ходит один `PrivacyGateway`. Прямые вызовы провайдеров вне
`ai/llm` запрещены архитектурно и проверяются тестом
`test_llm_calls_leave_only_through_the_gateway`: он же разрешает сетевые вызовы в
`ingest` — доступ к источнику сдачи это его работа — и запрещает там SDK моделей.

### Чего в `SubmissionBundle` нет, и что из этого следует

**Полного текста файла может не быть.** Ingest инлайнит `excerpt` только в пределах
своего бюджета; крупные файлы едут diff-only. `ai/content.py` сводит три источника
(`excerpt`, дозагрузка по `content_ref`, дифф) к одному объекту и помечает неполные
флагом `partial`. Дифф файла, добавленного этой сдачей, — это весь файл, и
фрагментом он не считается.

Что из этого следует по всему слою: в промпте такой файл помечен, и системная
инструкция запрещает утверждать по нему, что чего-то нет; валидатор цитат говорит
«не найдено в доступной части», а не «такого текста нет»; стилометрия и перплексия
такие файлы пропускают; список уходит в черновик (`partial_artifacts`) и в
ограничения детектора.

**История не хранит списка файлов.** `Revision` несёт время и объём коммита, но не
пути: GitHub отдаёт их отдельным запросом на каждый коммит. Поэтому форензика не
обещает «эта строка из того коммита» — она подсвечивает крупные файлы, добавленные
сдачей, и пишет в обосновании, что связь косвенная.

Роутер только оркестрирует, логика — в сервисах; схемы ответа отделены от доменных
моделей; всё I/O — `async`. Общий `IngestService` создаётся в lifespan и берётся из
`request.app.state`.

**Логи.** Только осмысленные события: старт/стоп сервиса, итог каждого ingest,
`WARNING` на отклонённый запрос и обрезанную карту репо. Детали фетча — `DEBUG`.
Логгеры — `getLogger(__name__)`, уровень из `LOG_LEVEL`.

## Как расширять

- **Новый роутер** — `app/routers/<name>.py` (`APIRouter`) + `app/schemas/<name>.py`,
  `include_router` в `main.py`.
- **Новый провайдер ingest** — `SubmissionProvider` в `ingest/providers/<name>.py`, запись
  в словарь `IngestService`, конфиг в `config.py`, значение в `SubmissionSource`.
- **Новый домен** (assignment, review, detection) — пакет рядом с `ingest`/`ai`; на входе
  только `SubmissionBundle`, наружу — сервисный класс, который зовёт роутер.

## TODO (по [architecture.md](architecture.md))

**Инфраструктура**
- [x] PostgreSQL + SQLAlchemy 2 (async); три таблицы (`users`, `submissions`,
      `review_revisions`) вместо полной схемы §10 — курсов, рубрик-в-БД и
      Assignment Engine ещё нет, наращивать некуда
- [x] Alembic — миграции до `head` в lifespan (`db/migrate.py`), автогенерация
      против `Base.metadata`; воркер прогоняет их же идемпотентной страховкой
- [x] Redis + arq: воркер на одну задачу — `review/rerun`. Остальной async
      (нормализация, батч-распределение) ждёт Assignment Engine, которого нет
- [ ] S3/MinIO для сырых артефактов; резолвер `content_ref` читает отсюда
- [x] единый `AppConfig` — агрегирует `IngestConfig` / `AIConfig` /
      `DatabaseConfig` / `AuthConfig` / `QueueConfig` в одну точку сборки

**Доступ**
- [x] JWT-аутентификация: `POST /auth/login`, `app/auth.py` (`get_current_user`,
      `require_role`), pyjwt + stdlib PBKDF2 — без внешнего хешера, потому что
      сеяные учётки не секрет по устройству
- [x] RBAC: `student < reviewer < admin`; reviewer видит и правит только свою
      очередь (404 на чужую сдачу, не 403 — не подтверждаем даже её
      существование), admin — весь поток. Роли «куратор»/«методист» из
      архитектуры слиты в `admin` — разводить их некому. Скоуп по
      курсу/назначению не нужен: концепции курса в API ещё нет
- [x] хакатон-вариант: по одному хардкод-логину на роль (`seed_users`,
      общий `AUTH_SEED_PASSWORD`) + `GET/POST/PATCH/DELETE /users` для
      остальных аккаунтов

**Ingest**
- [ ] классификатор артефактов + денилист шума (`solution` / `evidence` / `tooling` / `noise`)
- [x] стриппинг ноутбуков (`ai/content.py:strip_notebook`, `nbformat`) — код и
      markdown-ячейки целиком, вывод обрезан до 800 символов, картинки →
      `[plot: cell N]` без выдумывания описания; парсеры docx / xlsx / pdf — нет
- [ ] GitHub webhook: проверка HMAC-подписи, дедуп по `delivery_id`; poller как fallback
- [x] резолвер `content_ref` (`IngestService.fetch_content`) и ручки на любой путь репо
- [x] `get_file` как тул агента в чате ревьюера (и `get_diff`/`get_criterion`/`search_submission`)

**Проверки и оценка**
- [x] Format Gate — статические проверки рубрики по git-каналу
      (`required_paths`, `forbidden_paths`, `code_contains`, `code_absent`,
      `token_budget`), до вызова LLM; `blocked` останавливает модель
- [x] Rubric Compiler: условие → JSON-рубрика; каждый критерий сверяется с
      условием цитатой, чего в условии нет — уходит в `open_questions`
- [x] подтверждение черновика методистом: `POST /rubrics` с проверкой рубрики кодом
- [ ] Assignment Engine: `WorkProfile` от LLM + детерминированный солвер (венгерский / min-cost flow)
- [x] агрегатор баллов в коде: `Σ criterion × weight`, штраф за срок, confidence-флаги

**AI-слой**
- [x] PrivacyGateway: regex + псевдонимизация + валидатор остатка + аудит
- [ ] PrivacyGateway: NER на локальной модели (Natasha / slovnet) поверх регулярок
- [x] Review Agent: structured output по критериям, обязательные цитаты + их программная валидация
- [x] AI-Detection: git-форензика + стилометрия + LLM-judge; перплексия ждёт локального сервинга
- [ ] калибровка порогов детектора на вердиктах ревьюеров — данных пока нет

**Интеграции**
- [ ] экспорт ведомости в Google Sheets
- [ ] комментарий в PR через GitHub API
- [x] `review_revisions` с авторством (human / ai_assisted; `ai` — значение есть,
      писать пока некому: рерайт полностью замещает черновик, а не патчит его)
- [x] SSE-стрим чата ревьюера с моделью, `propose_review_patch` (§6.3) —
      транспорт SSE, не токен-стриминг: ход считается целиком, шаги отдаются
      как готовые события
