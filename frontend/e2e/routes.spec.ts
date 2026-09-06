import { expect, test, type Page } from '@playwright/test'
import { restoreSession } from './session'

/** То, что раньше проверялось руками на каждом демо: обход маршрутов без
 *  ошибок в консоли и без горизонтального скролла (см. `docs/handover-frontend.md`).
 *  Сессия восстанавливается из токена в хранилище — форму входа гоняют
 *  `auth.spec.ts` и `login.spec.ts`, здесь она была бы шумом на каждом маршруте.
 */

const ROUTES: Record<string, string[]> = {
  student: ['/my-work'],
  reviewer: ['/queue', '/check', '/courses/go', '/rubrics', '/streams', '/assignments', '/review/demo'],
  admin: ['/queue', '/check', '/courses/go', '/curators', '/rubrics', '/streams', '/assignments', '/review/demo'],
}

async function collectConsoleErrors(page: Page): Promise<string[]> {
  const errors: string[] = []
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text())
  })
  page.on('pageerror', (error) => errors.push(error.message))
  return errors
}

for (const [username, routes] of Object.entries(ROUTES)) {
  for (const route of routes) {
    test(`${route} loads without console errors as ${username}`, async ({ page, request }) => {
      await restoreSession(page, request, username)
      const errors = await collectConsoleErrors(page)

      await page.goto(route)
      await expect(page.locator('body')).toBeVisible()
      // Восстановление сессии — один запрос `/me` перед первым экраном.
      await expect(page.getByText('Загрузка…')).toHaveCount(0)
      await expect(page).not.toHaveURL(/\/login$/)

      const bodyErrors = errors.filter(
        (text) =>
          // Известный шум браузера/расширений, не наш код.
          !text.includes('ResizeObserver') && !text.includes('Failed to load resource'),
      )
      expect(bodyErrors, `console errors on ${route}: ${bodyErrors.join('; ')}`).toEqual([])
    })

    test(`${route} has no horizontal scroll as ${username}`, async ({ page, request }) => {
      await restoreSession(page, request, username)
      await page.goto(route)
      await page.waitForLoadState('networkidle')

      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
      expect(overflow, `horizontal overflow on ${route}: ${overflow}px`).toBeLessThanOrEqual(1)
    })
  }
}
