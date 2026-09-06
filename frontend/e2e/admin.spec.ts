import { expect, test, type Page } from '@playwright/test'

/** Админка руководителя: аккаунты и учебный каталог против настоящего бэкенда.
 *
 *  Вход делается явно формой, а не автологином по сохранённой роли: экран
 *  входа переезжает, и тест, завязанный на автологин, сломается вместе с ним.
 */

const PASSWORD = 'avito2026'

async function login(page: Page, username: string, password = PASSWORD) {
  await page.goto('/login')
  const onLoginScreen = await page
    .getByLabel('Логин')
    .first()
    .isVisible()
    .catch(() => false)
  if (!onLoginScreen) {
    await page.goto('/')
    await page.getByRole('button', { name: 'Войти' }).first().click()
  }
  await page.getByLabel('Логин').first().fill(username)
  await page.getByLabel('Пароль').first().fill(password)
  await page.getByRole('button', { name: /^(Войти|Вхожу)$/ }).last().click()
  await expect(page.getByText(username, { exact: true }).first()).toBeVisible()
}

async function openAdmin(page: Page, tab: 'Аккаунты' | 'Курсы') {
  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: 'Управление' })).toBeVisible()
  await page.getByRole('tab', { name: tab }).click()
}

test('аккаунт заводится, меняет роль, входит и удаляется', async ({ page }) => {
  const username = `e2e-user-${Date.now()}`
  await login(page, 'admin')
  await openAdmin(page, 'Аккаунты')

  await page.getByRole('button', { name: 'Новый аккаунт' }).click()
  await page.getByLabel('Логин', { exact: true }).fill(username)
  await page.getByLabel('Имя').fill('Пробный ревьюер')
  await page.getByLabel('Роль').selectOption('reviewer')
  await page.getByLabel('Пароль', { exact: true }).fill(PASSWORD)
  await page.getByRole('button', { name: 'Создать' }).click()

  const role = page.getByLabel(`Роль ${username}`)
  await expect(role).toHaveValue('reviewer')

  await role.selectOption('methodist')
  await page.reload()
  await page.getByRole('tab', { name: 'Аккаунты' }).click()
  await expect(page.getByLabel(`Роль ${username}`)).toHaveValue('methodist')

  // Новая роль работает: методист видит задания, админку — нет.
  await login(page, username)
  await page.goto('/assignments')
  await expect(page.getByRole('heading', { name: 'Задания' })).toBeVisible()
  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: 'Управление' })).toHaveCount(0)

  await login(page, 'admin')
  await openAdmin(page, 'Аккаунты')
  await page
    .getByRole('listitem')
    .filter({ hasText: username })
    .getByRole('button', { name: 'Удалить' })
    .click()
  await page.getByRole('button', { name: 'Удалить', exact: true }).last().click()
  await expect(page.getByLabel(`Роль ${username}`)).toHaveCount(0)
})

test('курс, поток, задание и состав заводятся и убираются', async ({ page }) => {
  const key = `e2e${Date.now()}`
  await login(page, 'admin')
  await openAdmin(page, 'Курсы')

  await page.getByRole('button', { name: 'Новый курс' }).click()
  await page.getByLabel('Ключ курса').fill(key)
  await page.getByLabel('Название курса').fill('Курс из теста')
  await page.getByRole('button', { name: 'Создать' }).click()

  const course = page.getByRole('listitem').filter({ has: page.getByLabel(`Курс ${key}`) }).first()
  await expect(course).toBeVisible()

  await course.getByRole('button', { name: 'Новый поток' }).click()
  await page.getByLabel('Ключ потока').fill('a')
  await page.getByLabel('Название потока').fill('Поток из теста')
  await page.getByRole('button', { name: 'Создать' }).click()
  await expect(page.getByLabel('Поток a')).toBeVisible()

  // Курс с потоком не удаляется — сервер объясняет, почему.
  await course.getByRole('button', { name: 'Удалить' }).first().click()
  await course.getByRole('button', { name: 'Удалить', exact: true }).last().click()
  await expect(course.getByText(/у курса есть потоки/)).toBeVisible()

  await page.getByRole('button', { name: 'Состав' }).click()

  await page.getByRole('button', { name: 'Выдать рубрику' }).click()
  await page.getByRole('button', { name: 'Выдать', exact: true }).click()
  await expect(page.getByText('Заданий нет — выдайте потоку рубрику.')).toHaveCount(0)

  await page.getByRole('button', { name: 'Зачислить' }).click()
  await page.getByRole('button', { name: '+ Student' }).click()
  await expect(page.getByText('student', { exact: true })).toBeVisible()

  await page.getByRole('button', { name: 'Отчислить' }).click()
  await page.getByRole('button', { name: 'Отчислить', exact: true }).last().click()
  await expect(page.getByText('Никого не зачислено.')).toBeVisible()

  await expect(page.locator('body')).not.toContainText('Внутренняя ошибка')
})

test('не руководителю админка не открывается', async ({ page }) => {
  await login(page, 'reviewer')
  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: 'Управление' })).toHaveCount(0)
  await expect(page.getByRole('heading', { name: 'Мои проверки' })).toBeVisible()
})
