# scripts

Ручные примеры и утилиты (не тесты, не часть пакета).

## ingest_pr_example.py

Прогоняет `ingest` на реальном GitHub PR и печатает разбор `SubmissionBundle`:
source, base..head, карту проекта (`tree`), изменённые файлы с диапазонами строк,
историю коммитов со статистикой и начало unified diff.

```bash
uv run python scripts/ingest_pr_example.py
uv run python scripts/ingest_pr_example.py https://github.com/<owner>/<repo>/pull/<n>
```

Работает без токена (анонимный GitHub API, 60 запросов/час). Для повышения лимита —
`INGEST_GITHUB__TOKEN` или `GITHUB_TOKEN` в окружении. По умолчанию берётся
маленький PR `pydantic/pydantic#13756` (одна строка в одном файле).
