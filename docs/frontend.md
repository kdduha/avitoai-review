# Frontend

Рабочее место куратора: React + Vite + TypeScript, TanStack Query, Tailwind v4,
Recharts.

```bash
npm install
npm run dev        # http://localhost:5173
npm run build
npm run typecheck
npm run gen:api    # типы из OpenAPI поднятого бэкенда
npm run e2e        # Playwright — поднимает и фронт, и бэкенд сам (playwright.config.ts)
```

Бэкенд нужен для проверки работ; ведомость и дашборд открываются и без него:

```bash
cd ../backend && uv run uvicorn avito_reviewer.app.main:app --port 8000
```

`/api` проксируется на `http://localhost:8000` (`vite.config.ts`), переопределяется
переменной `VITE_API_BASE`.

Бэкенд требует Bearer-токен почти везде (см. `docs/backend.md`) — фронт логинится
сам при старте и при смене роли (`app/session.tsx`), в один из трёх сеяных
аккаунтов: куратор → `reviewer`, руководитель → `admin` (бэкенд не заводит
отдельной роли координатора — см. `docs/backend.md`). Пароль —
`VITE_BACKEND_PASSWORD` (по умолчанию `avito2026`, тот же, что `AUTH_SEED_PASSWORD`
на бэкенде). Токен живёт в памяти вкладки (`lib/backend.ts`), не в `localStorage`.

## Docker

```bash
docker compose up --build frontend   # из корня — соберёт и бэкенд с базой заодно
```

Многоступенчатый билд: `npm run build` → статика в nginx (`Dockerfile`,
`nginx.conf`). `/api/*` nginx проксирует на сервис `backend:8000` — тот же путь,
что у `vite.config.ts` в dev, только имя хоста другое (докер-сеть, а не localhost).

## Где что лежит

```
src/lib/backend.ts     клиент бэкенда; backend.d.ts генерируется из OpenAPI
src/lib/workspace.ts   три ответа сервера → один вид для панелей
src/lib/runs.ts        прогоны проверки: живые (с сохранением на сервере) и записанные
src/lib/api.ts         данные админки, которых у бэкенда ещё нет
src/app/session.tsx    роль → авторизация: логин в сеяный аккаунт, токен в lib/backend.ts
src/mocks/             каталог программ и записанные прогоны
src/features/review/   Review Workspace и запуск проверки
src/features/rubrics/  каталог рубрик + CompileRubricPanel (условие → черновик → подтверждение)
src/features/courses/  ведомость, дашборд, кураторы
src/styles/index.css   токены визуального языка
e2e/                    Playwright: обход маршрутов, правка балла, вход, компилятор рубрик
```

**Состояние работы, список несделанного, правила бэкенда и инструкции «как
добавить программу, рубрику, прогон» — [handover-frontend.md](handover-frontend.md).**
