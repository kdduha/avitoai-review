import { expect, test } from '@playwright/test'
import { putToken, readToken, restoreSession, signInThroughForm, tokenFor } from './session'

/** Авторизация целиком: аноним не видит ничего, вход — только через форму,
 *  сессия переживает перезагрузку, 401 отовсюду возвращает на экран входа.
 *  Фронт не знает ни одного пароля — раньше он логинился сам при монтировании.
 */

test('an anonymous visitor is sent to the login screen from any route', async ({ page }) => {
  await page.goto('/rubrics')

  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByRole('button', { name: 'Войти' })).toBeVisible()
  await expect(page.getByText('Каталог рубрик')).toHaveCount(0)
})

test('the login screen names no accounts, endpoints or docs', async ({ page }) => {
  await page.goto('/login')

  const text = (await page.locator('body').innerText()).toLowerCase()
  for (const leak of ['/users', '/auth/login', 'post ', 'docs/', 'avito2026', 'student/', 'reviewer-2']) {
    expect(text, `экран входа не должен показывать «${leak}»`).not.toContain(leak)
  }
})

test('a wrong password is refused in plain words, without the backend detail', async ({ page }) => {
  await page.goto('/login')
  await signInThroughForm(page, 'reviewer', 'не-тот-пароль')

  await expect(page.getByRole('alert')).toHaveText('Неверный логин или пароль')
  await expect(page).toHaveURL(/\/login$/)
})

test('signing in lands the reviewer on their own screen and survives a reload', async ({ page }) => {
  await page.goto('/login')
  await signInThroughForm(page, 'reviewer')

  await expect(page).toHaveURL(/\/queue$/)
  await expect(page.getByText('reviewer · ревьюер')).toBeVisible()

  await page.reload()
  await expect(page).toHaveURL(/\/queue$/)
  await expect(page.getByText('reviewer · ревьюер')).toBeVisible()
})

test('signing out clears the token and returns to the login screen', async ({ page, request }) => {
  await restoreSession(page, request, 'reviewer')
  await page.goto('/queue')
  await expect(page.getByText('reviewer · ревьюер')).toBeVisible()

  await page.getByRole('button', { name: 'Выйти' }).click()

  await expect(page).toHaveURL(/\/login$/)
  expect(await readToken(page)).toBeNull()
})

test('a stale token in storage does not open the app', async ({ page }) => {
  await putToken(page, 'eyJhbGciOiJIUzI1NiJ9.протухший.подпись')
  await page.goto('/queue')

  await expect(page).toHaveURL(/\/login$/)
  expect(await readToken(page)).toBeNull()
})

test('a 401 in the middle of a session drops it instead of blaming the backend', async ({ page, request }) => {
  await restoreSession(page, request, 'reviewer')
  await page.goto('/queue')
  await expect(page.getByText('reviewer · ревьюер')).toBeVisible()

  await page.route('**/api/streams', (route) =>
    route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'токен недействителен' }),
    }),
  )
  await page.getByRole('link', { name: 'Потоки' }).click()

  await expect(page).toHaveURL(/\/login$/)
  expect(await readToken(page)).toBeNull()
})

test('the token is the only thing the app needs to come back', async ({ page, request }) => {
  const token = await tokenFor(request, 'methodist')
  await putToken(page, token)
  await page.goto('/')

  await expect(page).toHaveURL(/\/assignments$/)
  await expect(page.getByText('methodist · методист')).toBeVisible()
})

test('compiling a rubric round-trips to the real backend', async ({ page, request }) => {
  await restoreSession(page, request, 'methodist')
  await page.goto('/rubrics')
  await page.getByRole('button', { name: 'Собрать из условия' }).click()

  await page.getByPlaceholder('sysdesign-lab2').fill('e2e-go-task1')
  await page
    .getByPlaceholder('Вставьте условие целиком — критерии, шкалу, штрафы, всё как есть.')
    .fill(
      'Задание 1. Boilerplate сервиса. Разделите код на cmd/ и internal/. ' +
        'Реализуйте GET /ping (200) и HEAD /healthcheck (204). При завершении ' +
        'пишите в лог "Shutting down service-courier".',
    )
  await page.getByRole('button', { name: 'Собрать рубрику' }).click()

  // Провайдер `fake` не отвечает по схеме компилятора — 0 критериев и
  // открытые вопросы вместо придуманных цифр. Это ровно то же самое "честно
  // не смог", что видит методист с настоящим ключом на кривом условии:
  // компилятор не выдумывает, а поднимает вопрос наверх (§6.0 архитектуры).
  await expect(page.getByText(/открыт(ый|ых) вопрос/i)).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText('цитатами подтверждено 0%')).toBeVisible()
})
