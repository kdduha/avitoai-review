import { expect, test, type Page } from '@playwright/test'
import { SEED_PASSWORD as PASSWORD, signInThroughForm, tokenFor } from './session'

/** Админка руководителя: аккаунты и учебный каталог против настоящего бэкенда.
 *  Вход — формой, как его проходит человек: тесты про права должны ломаться
 *  вместе с правами, а не обходить экран входа. */

async function login(page: Page, username: string, password = PASSWORD) {
  const signOut = page.getByRole('button', { name: 'Выйти' })
  if (await signOut.isVisible().catch(() => false)) await signOut.click()
  await page.goto('/login')
  await signInThroughForm(page, username, password)
  await expect(page.getByText(new RegExp(`^${username} · `))).toBeVisible()
}

/** Что этот воркер завёл в общей базе стенда. Убирать «всё, что похоже на
 *  тестовое» нельзя: воркеры идут параллельно и снесли бы данные друг друга. */
const litter = { courses: new Set<string>(), users: new Set<string>() }

async function openAdmin(page: Page, tab: 'Аккаунты' | 'Курсы') {
  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: 'Управление' })).toBeVisible()
  await page.getByRole('tab', { name: tab }).click()
}

test('аккаунт заводится, меняет роль, входит и удаляется', async ({ page }) => {
  const username = `e2e-user-${Date.now()}`
  litter.users.add(username)
  await login(page, 'admin')
  await openAdmin(page, 'Аккаунты')

  await page.getByRole('button', { name: 'Новый аккаунт' }).click()
  const form = page.getByRole('region', { name: 'Новый аккаунт' })
  await form.getByLabel('Логин', { exact: true }).fill(username)
  await form.getByLabel('Имя', { exact: true }).fill('Пробный ревьюер')
  await form.getByLabel('Роль', { exact: true }).selectOption('reviewer')
  await form.getByLabel('Пароль', { exact: true }).fill(PASSWORD)
  await form.getByRole('button', { name: 'Создать' }).click()

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
  litter.courses.add(key)
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
  await expect(course.getByLabel('Поток a')).toBeVisible()

  // Курс с потоком не удаляется — сервер объясняет, почему.
  await course.getByRole('button', { name: 'Удалить' }).first().click()
  await course.getByRole('button', { name: 'Удалить', exact: true }).last().click()
  await expect(course.getByText(/у курса есть потоки/)).toBeVisible()

  await course.getByRole('button', { name: 'Состав' }).click()

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

/** Прогон оставляет за собой курсы, потоки и аккаунты в общей базе стенда:
 *  без уборки второй запуск видит два «Потока a» и падает на неоднозначности. */
test.afterAll(async ({ request }) => {
  const token = await tokenFor(request, 'admin')
  const auth = { Authorization: `Bearer ${token}` }
  const get = async <T,>(path: string): Promise<T> =>
    (await (await request.get(`/api${path}`, { headers: auth })).json()) as T
  const drop = (path: string) => request.delete(`/api${path}`, { headers: auth })

  for (const course of await get<{ id: string; key: string }[]>('/courses')) {
    if (!litter.courses.has(course.key)) continue
    for (const stream of await get<{ id: string }[]>(`/streams?course_id=${course.id}`)) {
      for (const item of await get<{ id: string }[]>(`/assignments?stream_id=${stream.id}`)) {
        await drop(`/assignments/${item.id}`)
      }
      for (const student of await get<{ username: string }[]>(`/streams/${stream.id}/students`)) {
        await drop(`/streams/${stream.id}/students/${student.username}`)
      }
      await drop(`/streams/${stream.id}`)
    }
    await drop(`/courses/${course.id}`)
  }

  for (const account of await get<{ id: string; username: string }[]>('/users')) {
    if (litter.users.has(account.username)) await drop(`/users/${account.id}`)
  }
})
