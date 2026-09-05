import { defineConfig, devices } from '@playwright/test'

/** E2E покрытие того, что раньше проверялось руками (см. `docs/handover-frontend.md`,
 *  «Что не сделано» — «Нет тестов»): обход маршрутов без ошибок консоли и
 *  горизонтального скролла, правка балла, переход по цитате, отключённый чат.
 *
 *  Бэкенд поднимается тут же вторым `webServer`, на провайдере `fake` — живой
 *  прогон (`/check`) не тестируется по-настоящему (ключей нет и не нужно),
 *  но авторизация, каталог рубрик и офлайн-обработка проверяются по-настоящему,
 *  не через мок.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: 'npm run dev',
      url: 'http://localhost:5173',
      reuseExistingServer: !process.env.CI,
      env: { VITE_BACKEND_PORT: '8010' },
    },
    {
      // Порт 8010, не 8000: docker-compose обычно уже держит бэкенд на 8000, и
      // `reuseExistingServer` иначе молча подключился бы к нему — настоящий
      // ключ вместо `fake` ломает тесты, завязанные на его вырожденный ответ
      // (см. `auth.spec.ts`, «compiling a rubric round-trips»).
      command:
        'cd ../backend && AI_LLM__PROVIDER=fake DB_DSN=sqlite+aiosqlite:///./e2e.db uv run uvicorn avito_reviewer.app.main:app --port 8010',
      url: 'http://localhost:8010/health',
      reuseExistingServer: !process.env.CI,
      stdout: 'pipe',
    },
  ],
})
