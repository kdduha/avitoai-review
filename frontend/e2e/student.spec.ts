import { expect, test } from '@playwright/test'
import { restoreSession, tokenFor } from './session'

/** Кабинет студента: что видно, пока работа обрабатывается, и что видно, когда
 *  обработать её не вышло. Раньше на оба вопроса экран отвечал молчанием.
 */

/** Курс, поток, задание и зачисление — руками через API: на пустом стенде у
 *  сеяного студента нет ни одного задания, а без задания сдавать нечего. */
/** Что этот воркер завёл в общей базе стенда: воркеры идут параллельно, и
 *  уборка «всего похожего на тестовое» снесла бы чужие данные. */
const litter = new Set<string>()

async function enrolStudent(request: import('@playwright/test').APIRequestContext) {
  const token = await tokenFor(request, 'admin')
  const auth = { authorization: `Bearer ${token}` }
  const key = `e2e${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
  litter.add(key)

  const course = await (await request.post('/api/courses', {
    headers: auth, data: { key, title: 'Курс из теста' },
  })).json()
  const stream = await (await request.post('/api/streams', {
    headers: auth, data: { course_id: course.id, key: 'a', title: 'Поток из теста' },
  })).json()
  await request.post(`/api/streams/${stream.id}/students`, {
    headers: auth, data: { usernames: ['student'] },
  })
  const rubrics = await (await request.get('/api/rubrics', { headers: auth })).json()
  await request.post('/api/assignments', {
    headers: auth,
    data: { stream_id: stream.id, rubric_key: rubrics[0].assignment_id, title: 'Задание из теста' },
  })
  return { auth, courseId: course.id, streamId: stream.id }
}

test('сдача видна в списке, пока она обрабатывается', async ({ page, request }) => {
  await enrolStudent(request)
  await restoreSession(page, request, 'student')

  /* Ответ сервера подставляем: настоящий ingest пошёл бы на GitHub за
     несуществующим PR и честно ответил 502, а проверяем мы здесь экран —
     что видно, пока запрос идёт, и что видно, когда он вернулся. Серверный
     путь закрыт pytest'ом (`tests/test_student.py`). */
  const card = {
    id: '00000000-0000-4000-8000-000000000001',
    assignment_title: 'Задание из теста',
    course_key: 'e2e', stream_key: 'a',
    origin_url: 'https://github.com/org/repo/pull/214',
    submitted_at: new Date().toISOString(),
    deadline_at: null, created_at: new Date().toISOString(),
    status: 'draft_ready', approved: false, max_score: 10,
    passed: null, pass_explanation: '', late_explanation: '', summary: null, verdicts: [],
  }
  let sent = false
  await page.route('**/api/me/submissions', async (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({ json: sent ? [card] : [] })
    }
    await new Promise((resolve) => setTimeout(resolve, 2500))
    sent = true
    await route.fulfill({ status: 201, json: card })
  })

  await page.goto('/my-work')
  await page.getByRole('button', { name: 'Сдать работу' }).first().click()
  await page.getByLabel('Ссылка на работу').fill('https://github.com/org/repo/pull/214')
  await page.getByRole('button', { name: 'Сдать', exact: true }).click()

  await expect(page.getByText(/Отправляю: собираю работу/)).toBeVisible()
  await expect(page.getByText(/Ждёт ревьюера/)).toBeVisible()
  await expect(page.getByText(/Отправляю: собираю работу/)).toHaveCount(0)
})

test('не отправившаяся работа не исчезает молча', async ({ page, request }) => {
  await enrolStudent(request)
  await restoreSession(page, request, 'student')

  await page.route('**/api/me/submissions', (route) =>
    route.request().method() === 'POST'
      ? route.fulfill({ status: 502, json: { detail: 'источник сдачи не ответил' } })
      : route.continue(),
  )

  await page.goto('/my-work')
  await page.getByRole('button', { name: 'Сдать работу' }).first().click()
  await page.getByLabel('Ссылка на работу').fill('https://github.com/org/repo/pull/214')
  await page.getByRole('button', { name: 'Сдать', exact: true }).click()

  await expect(page.getByText(/Работа не отправилась: источник сдачи не ответил/)).toBeVisible()
})

test.afterAll(async ({ request }) => {
  const token = await tokenFor(request, 'admin')
  const auth = { authorization: `Bearer ${token}` }
  const get = async <T,>(path: string): Promise<T> =>
    (await (await request.get(`/api${path}`, { headers: auth })).json()) as T
  const drop = (path: string) => request.delete(`/api${path}`, { headers: auth })

  for (const course of await get<{ id: string; key: string }[]>('/courses')) {
    if (!litter.has(course.key)) continue
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
})
