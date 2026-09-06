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
фронтенд логинится сам, а для ручных запросов — один из четырёх сеяных
аккаунтов (`student` / `reviewer` / `methodist` / `admin`, пароль
`avito2026`). Под каждую карточку из `backend/reviewers/` на старте заводится
свой аккаунт — логин совпадает с именем файла:

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

## С ключом модели

```bash
AI_LLM__PROVIDER=external AI_LLM__API_KEY="$ключ" docker compose up -d backend worker
```

Добавьте `INGEST_GITHUB__TOKEN`, если разбираемые pull request'ы лежат в
приватном репозитории — публичные ingest берёт и без него.

Дальше — **[CLAUDE.md](CLAUDE.md)**, если вы берёте проект дальше: обязательные
проверки, правила, оплаченные здесь ошибками, и решения, которые не стоит
пересматривать наугад. И **[docs/](docs/README.md)**: архитектура, состояние
бэкенда и фронтенда, конфигурация, эндпоинты, грабли.
