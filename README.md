# Avito AI Reviewer

Рабочее место ревьюера образовательных программ Авито: одна вкладка вместо
GitHub + Google Docs + Sheets. Что это и как устроено — **[docs/](docs/README.md)**.

## Запуск: всё вместе (docker compose)

```bash
docker compose up --build
```

- UI — http://localhost:5173
- API — http://localhost:8000, Swagger — http://localhost:8000/docs

Поднимает `postgres`, `redis` + `worker` (очередь), `backend`, `frontend`.
Ключей для старта не нужно: без них LLM-слой работает на провайдере `fake` —
конвейер проходится целиком, черновик приходит с пометкой «оценить вручную».

Все ручки бэкенда, кроме `/health`, `/init` и `/auth/login`, требуют вход;
фронтенд логинится сам, а для ручных запросов — один из трёх сеяных
аккаунтов (`student` / `reviewer` / `admin`, пароль
`avito2026`):

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "reviewer", "password": "avito2026"}'
```

## Запуск: по отдельности

```bash
cd backend && uv sync && uv run uvicorn avito_reviewer.app.main:app --reload   # :8000
cd frontend && npm install && npm run dev                                     # :5173
```

Без Postgres/Redis: `DB_DSN=sqlite+aiosqlite:///./dev.db` в `backend/.env`
(Redis нужен только для `POST .../review/rerun`).

Дальше — **[docs/](docs/README.md)**: архитектура, состояние бэкенда и
фронтенда, конфигурация, эндпоинты, грабли.
