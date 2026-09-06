# Avito AI Reviewer

![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.141-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-5.7-3178C6?logo=typescript&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)
![Docker Compose](https://img.shields.io/badge/docker-compose-2496ED?logo=docker&logoColor=white)

Рабочее место ревьюера образовательных программ Авито: одна вкладка вместо
GitHub + Google Docs + Sheets. Ревьюер открывает сдачу — pull request студента
— и получает черновик разбора по рубрике курса: балл по каждому критерию с
цитатой из кода, формальные проверки условия и рекомендательный сигнал о
следах ИИ. Ревьюер правит и утверждает; окончательное решение всегда за ним.

## Как это устроено

![Пайплайн Avito AI Reviewer](docs/pipeline.drawio.png)

Исходник — [docs/pipeline.drawio](docs/pipeline.drawio), открывается в
[app.diagrams.net](https://app.diagrams.net). Диаграмма — как система собрана
в коде сейчас, а не как задумывалась (за целевой формой — `docs/architecture.md`).

Коротко о развязках на диаграмме:

- **backend** и **worker** — один и тот же образ (`./backend`), разный
  entrypoint. Между собой они не говорят напрямую: связка только через Redis,
  и только для одной задачи — `POST /submissions/{id}/review/rerun`. Всё
  остальное на пути запроса синхронно — рубрика по размеру укладывается в
  секунды, и очередь добавила бы только задержку.
- **ingest** превращает ссылку на pull request в `SubmissionBundle`: дерево
  файлов, диффы, метаданные — через `githubkit`. Токен GitHub нужен только для
  приватных репозиториев.
- Разбор идёт в четыре шага: `gate` (формальные проверки рубрики, без единого
  токена модели) → `review` (модель отвечает по одному критерию с цитатой,
  сумму считает код) → `detection` (форензика истории, стилометрия текста и
  модель-судья — три независимых сигнала, отчёт рекомендательный) → `chat`
  (ревьюер может переспросить модель про черновик).
- Всё, что идёт в модель, проходит через `PrivacyGateway` — единственную точку
  выхода наружу. Он обезличивает ПДн до отправки и восстанавливает их только
  в ответах, которые остаются внутри периметра. Маршрут выбирается одной
  переменной окружения: внешний провайдер (`external`, OpenAI-совместимый API
  — aitunnel, OpenRouter), локальная модель (`local`, Ollama/vLLM) или
  `fake` — провайдер по умолчанию: конвейер проходится целиком, наружу ничего
  не уходит, вердикты приезжают пустыми.

## Запуск

```bash
docker compose up --build
```

Поднимает `postgres`, `redis`, `backend`, `worker` и `frontend`. Без ключей
работает провайдер `fake` — путь пройден, оценивать всё равно вручную:

- UI — http://localhost:5173
- API — http://localhost:8000, Swagger — http://localhost:8000/docs

Все ручки бэкенда, кроме `/health`, `/init` и `/auth/login`, требуют вход;
фронтенд логинится сам, а для ручных запросов — один из сеяных аккаунтов
(`student` / `reviewer` / `methodist` / `admin`, пароль `avito2026`). Под
каждую карточку из `backend/reviewers/` на старте заводится свой аккаунт —
логин совпадает с именем файла:

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "reviewer", "password": "avito2026"}'
```

С ключом модели:

```bash
AI_LLM__PROVIDER=external AI_LLM__API_KEY="$ключ" \
INGEST_GITHUB__TOKEN="$(gh auth token)" docker compose up -d backend worker
```

`INGEST_GITHUB__TOKEN` нужен только если разбираемые pull request'ы лежат в
приватном репозитории — публичные `ingest` берёт и без него.

### По отдельности, без Docker

```bash
cd backend && uv sync && uv run uvicorn avito_reviewer.app.main:app --reload   # :8000
cd frontend && npm install && npm run dev                                     # :5173
```

Без Postgres/Redis: `DB_DSN=sqlite+aiosqlite:///./dev.db` в `backend/.env`
(Redis нужен только для `POST .../review/rerun`).

## Дальше

**[CLAUDE.md](CLAUDE.md)** — если берёте проект дальше: обязательные проверки,
правила, оплаченные здесь ошибками, и решения, которые не стоит пересматривать
наугад.

**[docs/](docs/README.md)** — архитектура, состояние бэкенда и фронтенда,
конфигурация, эндпоинты, грабли.
