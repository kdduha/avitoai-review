# scripts

Ручные примеры и утилиты (не тесты, не часть пакета).

## ingest_pr_example.py

Прогоняет `ingest` на реальном GitHub PR и печатает `SubmissionBundle` как JSON:
изменение (`artifacts[].diff` + `changed_ranges` + `excerpt`), историю коммитов,
карту репозитория (`repo.files`).

```bash
uv run python scripts/ingest_pr_example.py
uv run python scripts/ingest_pr_example.py https://github.com/<owner>/<repo>/pull/<n>
```

Работает без токена (анонимный GitHub API, 60 запросов/час); `INGEST_GITHUB__TOKEN`
или `GITHUB_TOKEN` поднимают лимит. По умолчанию — `psf/requests#6951`: репозиторий
на ~130 файлов, так что `repo.truncated` остаётся `false`, а из трёх изменённых
файлов два попадают в `excerpt` целиком, а большой (42 КБ) едет diff-only.
