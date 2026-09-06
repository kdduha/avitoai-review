import type { APIRequestContext, Page } from '@playwright/test'

/** Ключ хранилища и сеяный пароль знают только тесты: во фронте пароля нет,
 *  вход — только через форму (`src/features/auth/LoginPage.tsx`). */
const TOKEN_KEY = 'avito-reviewer:token'
export const SEED_PASSWORD = 'avito2026'

export async function tokenFor(
  request: APIRequestContext,
  username: string,
  password: string = SEED_PASSWORD,
): Promise<string> {
  const response = await request.post('/api/auth/login', { data: { username, password } })
  const body = (await response.json()) as { access_token: string }
  return body.access_token
}

/** Вернувшийся человек: токен уже в хранилище, сессия восстанавливается по
 *  `/me`. Так тесты про экраны не проходят форму на каждом маршруте. */
export async function restoreSession(
  page: Page,
  request: APIRequestContext,
  username: string,
): Promise<void> {
  const token = await tokenFor(request, username)
  await page.addInitScript(
    ([key, value]) => localStorage.setItem(key, value),
    [TOKEN_KEY, token] as const,
  )
}

export async function putToken(page: Page, token: string): Promise<void> {
  await page.addInitScript(
    ([key, value]) => localStorage.setItem(key, value),
    [TOKEN_KEY, token] as const,
  )
}

export async function readToken(page: Page): Promise<string | null> {
  return page.evaluate((key) => localStorage.getItem(key), TOKEN_KEY)
}

/** Вход руками, как его проходит человек. */
export async function signInThroughForm(
  page: Page,
  username: string,
  password: string = SEED_PASSWORD,
): Promise<void> {
  await page.getByLabel('Логин', { exact: true }).fill(username)
  await page.getByLabel('Пароль', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Войти', exact: true }).click()
}
