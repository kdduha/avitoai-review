# backend — avito-reviewer

Передача работы: **[../docs/handover-backend.md](../docs/handover-backend.md)** —
что готово, что нет и на чём здесь спотыкаются.

Единый модульный сервис: FastAPI + uv, Python 3.11.

## Запуск

```bash
uv sync
uv run uvicorn avito_reviewer.app.main:app --reload   # http://localhost:8000/docs
uv run pytest                                         # тесты
uv run python scripts/ingest_pr_example.py            # разбор реального PR

docker compose up --build                             # из корня репозитория
```

Конфиг — переменные окружения `INGEST_*` и `AI_*` (см. `avito_reviewer/config.py`),
`LOG_LEVEL` (по умолчанию `INFO`). Без ключей приложение стартует на провайдере
`fake`: конвейер проходится целиком, но заглушке нечего ответить — черновик
приходит с пометкой «оценить вручную». Готовый черновик без ключа показывает
`scripts/demo.py`, который подставляет ответы, собранные из строк самой работы.

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

- `GET /health` — liveness
- `GET /init` — статус бутстрапа: провайдеры ingest, маршрут модели, рубрики
- `POST /ingest` — `{link, source, assignment_id?, deadline_at?}` → `SubmissionBundle`
- `GET /rubrics`, `GET /rubrics/{assignment_id}` — каталог рубрик
- `POST /review` — `{link, rubric_id | rubric, gate_facts?, condition_text?}` →
  `{bundle, files, draft}`: сдача, тексты файлов и черновик с проверенными цитатами
- `POST /detect` — `{link, rubric_id?}` → `{bundle, files, report}`: рекомендательный
  отчёт о признаках ГенИИ
- `POST /rubrics/compile` — `{assignment_id, condition_text, course?, hint?}` →
  черновик рубрики из условия. Ничего не сохраняет: рубрика действует на весь
  поток, поэтому подтверждение методистом обязательно по устройству
- `POST /rubrics` — `{rubric, confirmed_by, overwrite?}` → рубрика подтверждена
  методистом и вступила в силу для потока. `422` — не считается (список поломок),
  `409` — такая уже есть
- `GET /cost` — журнал шлюза в цифрах: вызовы, токены, рубли

`/review` и `/detect` сами тянут сдачу по ссылке и отдают `bundle` вместе с
результатом: разложить это на три вызова значило бы трижды сходить в GitHub за
одним и тем же. Базы ещё нет, поэтому каждый прогон — свежий ingest.

### Какой моделью что считать

Задачи разные по цене ошибки. Ревью идёт потоком — там решает стоимость. Rubric
Compiler считается один раз на задание, его результат подтверждает человек, а
ошибка тиражируется на весь поток — там решает устойчивость. Замер на одном и
том же условии: дешёвая модель дважды дала разный результат и один раз вернула
ноль критериев, сильная — шесть критериев со стопроцентным подтверждением
цитатами за 2 ₽. Отсюда матрица `AI_LLM__TASK_MODELS`, а не одна модель на всё.

## Демо без ключа и без GitHub

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

## Структура

```
src/avito_reviewer/
  config.py              IngestConfig / AIConfig и вложенные, читаются из env
  logsetup.py            configure_logging(): один stderr-хендлер на дерево avito_reviewer
  app/                   HTTP-слой
    main.py              create_app(): configure_logging, lifespan (IngestService), роутеры
    routers/             APIRouter по доменам: base (/health, /init), ingest (/ingest)
    schemas/             Pydantic-модели запросов/ответов, по файлу на роутер
  ingest/                ссылка → SubmissionBundle
    service.py           IngestService: SubmissionSource → провайдер; резолвер content_ref
    models.py            SubmissionBundle и связанные модели — контракт для всех слоёв ниже
    diff.py              разбор unified diff (unidiff): изменённые строки и текст головы
    content.py           разбор ручек content_ref — схемы знает только ingest
    providers/github.py  единственный провайдер, клиент — githubkit
  ai/                    всё, что связано с моделями
    service.py           AIService: prepare (async) → review / detect (sync)
    content.py           тексты артефактов: excerpt | дозагрузка | дифф, флаг partial
    rubric.py            схема рубрики, разбор JSON, реестр каталога
    llm/                 PrivacyGateway — единственный выход к моделям
    review/              промпт из рубрики, валидатор цитат, агрегатор баллов
    detection/           ансамбль сигналов ГенИИ + signals/
rubrics/                 рубрики как данные: добавить курс = добавить JSON
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

## TODO (по `.claude/architecture.md`)

**Инфраструктура**
- [ ] PostgreSQL + SQLAlchemy 2 (async) + Alembic; ORM-модели по §10
- [ ] Redis + arq: воркеры для нормализации, батч-распределения, прогона детектора
- [ ] S3/MinIO для сырых артефактов; резолвер `content_ref` читает отсюда
- [ ] `AppConfig` через `pydantic-settings` на всё приложение, не только ingest

**Доступ**
- [ ] JWT-аутентификация; `get_current_user` в `app/dependencies.py`
- [ ] RBAC: роли `student` / `reviewer` / `coordinator` / `admin`; скоуп по курсу и назначению
- [ ] хакатон-вариант: по одному хардкод-логину на роль

**Ingest**
- [ ] классификатор артефактов + денилист шума (`solution` / `evidence` / `tooling` / `noise`)
- [ ] стриппинг ноутбуков; парсеры docx / xlsx / pdf
- [ ] GitHub webhook: проверка HMAC-подписи, дедуп по `delivery_id`; poller как fallback
- [x] резолвер `content_ref` (`IngestService.fetch_content`) и ручки на любой путь репо
- [ ] `get_file` как тул агента в чате ревьюера (резолвер под ним уже есть)

**Проверки и оценка**
- [ ] Format Gate (объём, шрифты, число тест-кейсов, smoke-тесты) — до вызова LLM;
      правила уже лежат в рубриках (`format_gate`), исполнителя ещё нет
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
- [ ] SSE-стрим чата ревьюера с моделью; `review_revisions` с авторством (ai / human / ai-assisted)
