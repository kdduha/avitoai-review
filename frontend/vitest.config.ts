import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vitest/config'

/** Юнит-тесты живут рядом с кодом в `src`.
 *
 *  Каталог `e2e/` рядом — это Playwright (`npm run e2e`), и его спеки нельзя
 *  отдавать vitest: чужой раннер их не выполнит, а прогон станет красным без
 *  всякой причины. Отсюда явный `include`. */
export default defineConfig({
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  test: {
    include: ['src/**/*.test.ts'],
  },
})
