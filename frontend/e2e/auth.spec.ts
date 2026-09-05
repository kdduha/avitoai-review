import { expect, test } from '@playwright/test'

/** Бэкенд требует Bearer-токен на всём, кроме /health, /init и /auth/login —
 *  без входа `/rubrics` (реальный API, не мок) отвечает 401 и экран показывает
 *  офлайн-заглушку вместо каталога. Эти тесты проверяют, что вход происходит
 *  сам, до того как экран успевает отправить первый запрос.
 */

test('logging in happens before any authenticated request, catalogue loads for real', async ({ page }) => {
  const loginRequests: string[] = []
  page.on('request', (request) => {
    if (request.url().includes('/auth/login')) loginRequests.push(request.url())
  })

  await page.addInitScript(() => localStorage.setItem('avito-reviewer:role', 'curator'))
  await page.goto('/rubrics')

  await expect(page.getByText('Каталог рубрик не загрузился')).toHaveCount(0)
  await expect(page.getByText('Создание boilerplate сервиса')).toBeVisible()
  expect(loginRequests.length).toBeGreaterThanOrEqual(1)
})

test('switching role re-authenticates as the matching backend account', async ({ page }) => {
  const logins: { username: string }[] = []
  page.on('request', (request) => {
    if (!request.url().includes('/auth/login')) return
    const body = request.postDataJSON() as { username: string } | null
    if (body) logins.push(body)
  })

  await page.addInitScript(() => localStorage.setItem('avito-reviewer:role', 'curator'))
  await page.goto('/rubrics')
  await expect(page.getByText('Создание boilerplate сервиса')).toBeVisible()
  expect(logins.at(-1)?.username).toBe('reviewer')

  await page.getByRole('button', { name: 'Руководитель' }).click()
  await expect.poll(() => logins.at(-1)?.username).toBe('admin')
})

test('the compile-rubric screen is only offered to the admin-mapped role', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('avito-reviewer:role', 'curator'))
  await page.goto('/rubrics')
  await expect(page.getByRole('button', { name: 'Собрать из условия' })).toHaveCount(0)

  await page.getByRole('button', { name: 'Руководитель' }).click()
  await expect(page.getByRole('button', { name: 'Собрать из условия' })).toBeVisible()
})

test('compiling a rubric round-trips to the real backend', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('avito-reviewer:role', 'head'))
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
  // Черновик с реально подтверждёнными критериями проверен вручную на живом
  // ключе — см. docs/handover-frontend.md.
  await expect(page.getByText(/открыт(ый|ых) вопрос/i)).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText('цитатами подтверждено 0%')).toBeVisible()
})
