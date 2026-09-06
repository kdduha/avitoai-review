import { expect, test } from '@playwright/test'
import { restoreSession, signInThroughForm, tokenFor } from './session'

/** Роль решает, где человек оказывается после входа и какие маршруты ему
 *  вообще отвечают. Роль приходит с сервера (`/auth/login`, затем `/me`) —
 *  переключателя ролей в интерфейсе нет. */

const HOME: Record<string, RegExp> = {
  student: /\/my-work$/,
  reviewer: /\/queue$/,
  methodist: /\/assignments$/,
  admin: /\/streams$/,
}

for (const [username, home] of Object.entries(HOME)) {
  test(`${username} signs in and lands on their own start screen`, async ({ page }) => {
    await page.goto('/login')
    await signInThroughForm(page, username)

    await expect(page).toHaveURL(home)
  })
}

test('a student asking for a reviewer route gets their own screen, not an empty one', async ({ page, request }) => {
  await restoreSession(page, request, 'student')

  await page.goto('/queue')
  await expect(page).toHaveURL(/\/my-work$/)

  await page.goto('/rubrics')
  await expect(page).toHaveURL(/\/my-work$/)
})

test('a reviewer is kept out of the methodist and admin screens', async ({ page, request }) => {
  await restoreSession(page, request, 'reviewer')

  await page.goto('/rubrics/new')
  await expect(page).toHaveURL(/\/queue$/)

  await page.goto('/curators')
  await expect(page).toHaveURL(/\/queue$/)
})

test('an account created through the API signs in like any other', async ({ page, request }) => {
  const token = await tokenFor(request, 'admin')
  const username = `e2e-reviewer-${Date.now()}`
  const created = await request.post('/api/users', {
    headers: { authorization: `Bearer ${token}` },
    data: { username, password: 's3cret123', role: 'reviewer', display_name: 'Второй ревьюер' },
  })
  expect(created.ok()).toBeTruthy()

  await page.goto('/login')
  await signInThroughForm(page, username, 's3cret123')

  await expect(page).toHaveURL(/\/queue$/)
  await expect(page.getByText('Второй ревьюер')).toBeVisible()
  await expect(page.getByText(`${username} · ревьюер`)).toBeVisible()

  // База стенда переживает прогон: аккаунт за собой убираем, иначе список
  // аккаунтов в `/admin` обрастает мусором от каждого запуска.
  const { id } = (await (await request.get('/api/users', {
    headers: { authorization: `Bearer ${token}` },
  })).json() as { id: string; username: string }[]).find((row) => row.username === username)!
  await request.delete(`/api/users/${id}`, { headers: { authorization: `Bearer ${token}` } })
})
