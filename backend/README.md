# backend — avito-reviewer

Единый модульный сервис: FastAPI + uv, Python 3.11.

## Запуск

```bash
uv sync
uv run uvicorn avito_reviewer.app.main:app --reload   # http://localhost:8000/docs
uv run python scripts/ingest_pr_example.py            # разбор реального PR

docker compose up --build                             # из корня репозитория
```

Конфиг — переменные окружения `INGEST_*` (см. `avito_reviewer/config.py`),
`LOG_LEVEL` (по умолчанию `INFO`).

## Эндпоинты

- `GET /health` — liveness
- `GET /init` — статус бутстрапа (поднятые провайдеры ingest)
- `POST /ingest` — `{link, source, assignment_id?, deadline_at?}` → `SubmissionBundle`

## Структура

```
src/avito_reviewer/
  config.py              IngestConfig / GitHubConfig, читаются из env
  logsetup.py            configure_logging(): один stderr-хендлер на дерево avito_reviewer
  app/                   HTTP-слой
    main.py              create_app(): configure_logging, lifespan (IngestService), роутеры
    routers/             APIRouter по доменам: base (/health, /init), ingest (/ingest)
    schemas/             Pydantic-модели запросов/ответов, по файлу на роутер
  ingest/                ссылка → SubmissionBundle
    service.py           IngestService: SubmissionSource → провайдер
    models.py            SubmissionBundle и связанные модели — контракт для всех слоёв ниже
    diff.py              разбор unified diff (unidiff)
    providers/github.py  единственный провайдер, клиент — githubkit
  ai/                    PrivacyGateway, Review Agent, AI-Detection — пока пусто
scripts/                 ручные примеры (не тесты)
```

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
- [ ] `get_file`-тул: резолвер `content_ref` и произвольных путей репозитория

**Проверки и оценка**
- [ ] Format Gate (объём, шрифты, число тест-кейсов, smoke-тесты) — до вызова LLM
- [ ] Rubric Compiler: условие → JSON-рубрика, подтверждение методистом
- [ ] Assignment Engine: `WorkProfile` от LLM + детерминированный солвер (венгерский / min-cost flow)
- [ ] агрегатор баллов в коде: `Σ criterion × weight`, штраф за срок, confidence-флаги

**AI-слой**
- [ ] PrivacyGateway: regex + NER (Natasha / slovnet) + псевдонимизация + валидатор остатка + аудит
- [ ] Review Agent: structured output по критериям, обязательные цитаты + их программная валидация
- [ ] AI-Detection: git-форензика + перплексия (local logprobs) + стилометрия + LLM-judge, калибровка

**Интеграции**
- [ ] экспорт ведомости в Google Sheets
- [ ] комментарий в PR через GitHub API
- [ ] SSE-стрим чата ревьюера с моделью; `review_revisions` с авторством (ai / human / ai-assisted)
