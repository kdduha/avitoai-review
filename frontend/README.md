# Frontend

Рабочее место куратора: React + Vite + TypeScript, TanStack Query, Tailwind v4,
Recharts.

```bash
npm install
npm run dev        # http://localhost:5173
npm run build
npm run typecheck
npm test           # юнит-тесты (vitest)
npm run gen:api    # типы из OpenAPI поднятого бэкенда
```

Бэкенд нужен для проверки работ; ведомость и дашборд открываются и без него:

```bash
cd ../backend && uv run uvicorn avito_reviewer.app.main:app --port 8000
```

`/api` проксируется на `http://localhost:8000` (`vite.config.ts`), переопределяется
переменной `VITE_API_BASE`.

## Где что лежит

```
src/lib/backend.ts     клиент бэкенда; backend.d.ts генерируется из OpenAPI
src/lib/workspace.ts   три ответа сервера → один вид для панелей
src/lib/runs.ts        прогоны проверки: живые и записанные
src/lib/api.ts         данные админки, которых у бэкенда ещё нет
src/lib/rubric.ts      зеркало серверных проверок рубрики и справочник гейта
src/lib/*.test.ts      юнит-тесты: зеркало рубрики, сторож расхождения, адаптер
src/mocks/             каталог программ и записанные прогоны
src/features/review/   Review Workspace и запуск проверки
src/features/rubrics/  каталог рубрик, компилятор и редактор
src/features/courses/  ведомость, дашборд, кураторы
src/styles/index.css   токены визуального языка
```

**Состояние работы, список несделанного, правила бэкенда и инструкции «как
добавить программу, рубрику, прогон» — `docs/handover-frontend.md`.**
