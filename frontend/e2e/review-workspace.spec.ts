import { expect, test } from '@playwright/test'

/** Записанный прогон `/review/demo` — без бэкенда, детерминированный: то, на
 *  чём раньше руками проверялись правка балла и переход по цитате. */

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('avito-reviewer:role', 'curator'))
  await page.goto('/review/demo')
})

test('editing a score marks it as corrected by the reviewer', async ({ page }) => {
  const row = page.locator('article').first()
  const scoreButton = row.getByTitle('Поправить балл')
  const before = await row.locator('.num').first().innerText()

  await scoreButton.click()
  // Уменьшить, не увеличить: первый критерий демо-прогона не гарантированно
  // ниже максимума, а вот выше нуля — да, так что убыль всегда меняет счёт.
  await row.getByLabel('Уменьшить балл').click()
  await row.getByText('Готово').click()

  await expect(row.getByText('Балл поправлен куратором')).toBeVisible()
  const after = await row.locator('.num').first().innerText()
  expect(after).not.toBe(before)

  // Демо-прогон не персистентен — сумма показана как предварительная.
  await expect(page.getByText('Сумма по критериям')).toBeVisible()
  await expect(page.getByText('пересчитает сервер')).toBeVisible()
})

test('clicking a citation highlights it in the file viewer', async ({ page }) => {
  const quoteButton = page.locator('article button', { hasText: '.go' }).first()
  await quoteButton.click()
  await expect(page.getByText('подсвечено по цитате')).toBeVisible()
})

test('chat is explicitly disabled on a live-shaped panel, not silently missing', async ({ page }) => {
  await page.getByText('Разговор с моделью').click()
  await expect(page.getByPlaceholder('Демо-ветка: ответы записаны заранее')).toBeDisabled()
})
