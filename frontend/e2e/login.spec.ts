import { expect, test } from '@playwright/test'

/** `LoginModal` — единственный способ войти под аккаунтом, заведённым через
 *  `POST /users`, а не под одним из двух дефолтных за `RoleSwitch`. */

test('logging in via the modal as a freshly created reviewer updates the header', async ({ page, request }) => {
  const admin = await request.post('/api/auth/login', {
    data: { username: 'admin', password: 'avito2026' },
  })
  const { access_token: token } = await admin.json()

  const username = `e2e-reviewer-${Date.now()}`
  const created = await request.post('/api/users', {
    headers: { authorization: `Bearer ${token}` },
    data: { username, password: 's3cret123', role: 'reviewer', display_name: 'Второй ревьюер' },
  })
  expect(created.ok()).toBeTruthy()

  await page.addInitScript(() => localStorage.setItem('avito-reviewer:role', 'head'))
  await page.goto('/queue')
  await expect(page.getByText('руководитель программы')).toBeVisible()

  await page.getByRole('button', { name: 'Войти' }).click()
  await page.getByPlaceholder('reviewer-2').fill(username)
  await page.locator('input[type="password"]').fill('s3cret123')
  await page.getByRole('button', { name: 'Войти' }).nth(1).click()

  await expect(page.getByText('Второй ревьюер')).toBeVisible()
  await expect(page.getByText(`${username} · куратор`)).toBeVisible()
})

test('logging in via the modal with student credentials is rejected', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('avito-reviewer:role', 'curator'))
  await page.goto('/queue')

  await page.getByRole('button', { name: 'Войти' }).click()
  await page.getByPlaceholder('reviewer-2').fill('student')
  await page.locator('input[type="password"]').fill('avito2026')
  await page.getByRole('button', { name: 'Войти' }).nth(1).click()

  await expect(page.getByText(/нет экрана в этом интерфейсе/i)).toBeVisible()
})
