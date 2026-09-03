# Avito AI Reviewer

Рабочее место ревьюера образовательных программ Авито: одна вкладка вместо
GitHub + Google Docs + Sheets. Полная архитектура — `.claude/architecture.md`.

## Запуск

```bash
docker compose up --build
```

- API — http://localhost:8000
- Swagger — http://localhost:8000/docs

## Состав репозитория 

- `backend/` — Python-сервис (FastAPI + uv). Ingest реализован, остальное по плану.
- `frontend/` и инфраструктура — позже.

![architecture](docs/backend.drawio.png)

## Как это работает

Ссылка на PR → `ingest` собирает провайдеро-независимый `SubmissionBundle` (диффы, а не
тела файлов; полный текст по `content_ref`) → `ai`-слой через `PrivacyGateway`
обезличивает ПДн и вызывает LLM: `Review Agent` ставит вердикты по критериям с
обязательными цитатами, `AI-Detection` считает сигналы ГенИИ → детерминированный код
агрегирует баллы, ревьюер утверждает или правит.
