# avito-reviewer (backend)

Единый модульный Python-сервис. `src/avito_reviewer/`:

- `config.py` — конфиг приложения (`IngestConfig` / `GitHubConfig`), env `INGEST_*`
- `ingest/` — ссылка на сдачу → канонический `SubmissionBundle` (реализован GitHub PR)
- `ai/` — LLM-слой, ревью-агент, детектор ГенИИ (заглушка)

## Старт

```bash
uv sync
source .venv/bin/activate
uv run python scripts/ingest_pr_example.py           # разбор реального PR
```

## ingest

Провайдер выбирается явно по `SubmissionSource`, не угадывается по ссылке.

```python
from avito_reviewer.ingest import create_ingest_service, IngestContext, SubmissionSource

service = create_ingest_service()
bundle = await service.ingest(
    "https://github.com/<owner>/<repo>/pull/<n>",
    SubmissionSource.GITHUB_PR,
    context=IngestContext(assignment_id=..., deadline_at=...),
)
await service.aclose()
```

`SubmissionBundle` рассчитан на отправку агенту целиком: описывает изменение
(`artifacts[].diff` + `changed_ranges`), полный текст файла (`excerpt`) кладётся
только если он меньше `excerpt_max_bytes`, иначе берётся по `content_ref`; окружение —
плоский список путей `repo.files`. См. докстринги в `ingest/models.py`.

Основные env-переменные: `INGEST_GITHUB__TOKEN`, `INGEST_GITHUB__EXCERPT_MAX_BYTES`
(дефолт 16000), `INGEST_GITHUB__MAX_ARTIFACTS` / `MAX_CONTEXT_FILES` / `MAX_COMMITS`.
