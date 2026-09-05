import { expect, test, type Page } from '@playwright/test'

/** То, что раньше проверялось руками на каждом демо: обход маршрутов без
 *  ошибок в консоли и без горизонтального скролла (см. `docs/handover-frontend.md`).
 *  Роль переключается в шапке и живёт в `localStorage` — читаем/пишем его
 *  напрямую, не гоняя реальный клик по каждому маршруту дважды.
 */

const ROUTES = ['/queue', '/check', '/courses/go', '/curators', '/rubrics', '/review/demo']

async function setRole(page: Page, role: 'curator' | 'head') {
  await page.addInitScript((value) => localStorage.setItem('avito-reviewer:role', value), role)
}

async function collectConsoleErrors(page: Page): Promise<string[]> {
  const errors: string[] = []
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text())
  })
  page.on('pageerror', (error) => errors.push(error.message))
  return errors
}

for (const role of ['curator', 'head'] as const) {
  for (const route of ROUTES) {
    test(`${route} loads without console errors as ${role}`, async ({ page }) => {
      await setRole(page, role)
      const errors = await collectConsoleErrors(page)

      await page.goto(route)
      await expect(page.locator('body')).toBeVisible()
      // Вход в сеяный аккаунт — единственный запрос перед рендером экрана.
      await expect(page.getByText('Выполняется вход…')).toHaveCount(0)

      const bodyErrors = errors.filter(
        (text) =>
          // Известный шум браузера/расширений, не наш код.
          !text.includes('ResizeObserver') && !text.includes('Failed to load resource'),
      )
      expect(bodyErrors, `console errors on ${route}: ${bodyErrors.join('; ')}`).toEqual([])
    })

    test(`${route} has no horizontal scroll as ${role}`, async ({ page }) => {
      await setRole(page, role)
      await page.goto(route)
      await page.waitForLoadState('networkidle')

      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
      expect(overflow, `horizontal overflow on ${route}: ${overflow}px`).toBeLessThanOrEqual(1)
    })
  }
}
