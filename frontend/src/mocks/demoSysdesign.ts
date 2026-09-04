/** Демо-прогон по системному дизайну: Markdown-документ с диаграммами,
 *  как в примерах организаторов. Формат ответов — тот же, что у `/review` и
 *  `/detect`, поэтому рисуется тем же кодом, что живой прогон.
 *
 *  Работа намеренно набирает ровно порог: 4 из 6. Это самая полезная для
 *  куратора ситуация — решение зависит от одного вердикта.
 */

import type { DetectResponse, ReviewResponse, SubmissionBundle } from '@/lib/backend'
import { locator, toArtifacts, type DemoFile } from './demoUtils'

export const DEMO_SYSDESIGN_ID = 'demo-sysdesign'

const DOC = `# Лабораторная работа №1. Сервис бронирования занятий фитнес-клуба

## 1. Контекст

Сервис позволяет клиенту клуба записаться на групповое занятие, отменить
запись и увидеть свои будущие тренировки. Администратор клуба заводит
расписание и управляет вместимостью залов.

## 2. Декомпозиция

Декомпозиция выполнена по двум признакам: по функциям и по ролям.

По функциям выделены: каталог расписания, бронирование, уведомления,
профиль клиента. По ролям: контур клиента и контур администратора — они
живут в разных сценариях нагрузки и имеют разные требования к отклику.

## 3. Границы системы и внешние акторы

Внешние акторы: клиент клуба, администратор, платёжный провайдер,
СМС-шлюз. Внутрь системы входят каталог, бронирование и уведомления;
биллинг остаётся снаружи и вызывается по API.

## 4. Контракты

    POST /bookings
    { "slot_id": "uuid", "client_id": "uuid" }
    -> 201 { "booking_id": "uuid", "status": "confirmed" }

    DELETE /bookings/{id}
    -> 204

Взаимодействие синхронное, поверх HTTP. Уведомления отправляются
асинхронно через очередь.

## 5. Модель данных

Основные сущности: Slot, Booking, Client. Slot хранит вместимость,
Booking ссылается на слот и клиента.

## 6. Диаграмма C4

\`\`\`mermaid
C4Context
  Person(client, "Клиент клуба")
  System(booking, "Сервис бронирования")
  System_Ext(sms, "СМС-шлюз")
  Rel(client, booking, "Записывается на занятие")
  Rel(booking, sms, "Отправляет напоминание")
\`\`\`

## 7. Нефункциональные требования

Система должна работать быстро и выдерживать высокую нагрузку.
Важно отметить, что отказоустойчивость является ключевым требованием
современных распределённых систем, поэтому необходимо предусмотреть
соответствующие механизмы защиты на всех уровнях архитектуры.

## 8. Отказоустойчивость

При недоступности СМС-шлюза напоминания складываются в очередь и
отправляются позже. При отказе базы данных сервис переходит в режим
только чтения: расписание показывается, бронирование недоступно.

## 9. Узкое место

Узкое место — запись в слот при массовом открытии расписания: сотни
клиентов одновременно бронируют один и тот же слот. Масштабируется
горизонтально по каталогу и очередью на запись.

## 10. Итог

Архитектура покрывает основные сценарии. Компромисс: синхронное
бронирование проще в отладке, но хуже держит пик.
`

const FILES: DemoFile[] = [
  {
    path: 'docs/lab1-booking.md',
    lang: 'markdown',
    firstLine: 1,
    partial: false,
    origin: 'fetched',
    changedLines: '1–86',
    text: DOC,
  },
]

const at = locator(FILES)

const BUNDLE = {
  submission_id: 'demo-sysdesign-lab1',
  source: 'github_pr',
  origin_url: 'https://github.com/ai-talent-hub-avito/homework_examples/pull/58',
  retrieved_at: '2026-09-04T11:20:00+03:00',
  student_ref: { internal_id: '318204', external_handles: {} },
  submitted_at: '2026-09-04T20:41:00+03:00',
  deadline_at: '2026-09-04T23:59:00+03:00',
  assignment_id: null,
  base_ref: 'main',
  head_ref: 'lab1',
  artifacts: [],
  revisions: [],
  repo: null,
} as unknown as SubmissionBundle

export const DEMO_SYSDESIGN_REVIEW: ReviewResponse = {
  bundle: BUNDLE,
  files: toArtifacts(FILES),
  draft: {
    assignment_id: 'sysdesign-lab1',
    rubric_title: 'Проектирование системы: декомпозиция и архитектурное описание',
    raw_score: 4,
    score: 4,
    max_score: 6,
    passed: true,
    pass_explanation: 'Порог зачёта — 4 из 6. Работа набрала ровно порог.',
    late_explanation: 'сдано в срок',
    gate_facts: [
      'документ с решением на месте',
      'в работе одна диаграмма из двух требуемых',
      'нефункциональные требования числами не выражены',
    ],
    gate: {
      status: 'warning',
      facts: [],
      outcomes: [
        { check: 'required_paths', level: 'blocking', label: 'Документ с решением на месте', passed: true, inconclusive: false, detail: 'docs/lab1-booking.md', locations: ['docs/lab1-booking.md'] },
        { check: 'code_contains', level: 'warning', label: 'Диаграмма C4 упомянута в тексте', passed: true, inconclusive: false, detail: 'раздел 6', locations: ['docs/lab1-booking.md:48'] },
        { check: 'code_contains', level: 'warning', label: 'В работе есть хотя бы одна диаграмма', passed: true, inconclusive: false, detail: 'mermaid-блок C4Context', locations: ['docs/lab1-booking.md:50'] },
        { check: 'code_contains', level: 'info', label: 'Нефункциональные требования названы числами', passed: false, inconclusive: false, detail: 'чисел в разделе 7 нет', locations: [] },
        { check: 'token_budget', level: 'info', label: 'Объём работы', passed: true, inconclusive: false, detail: 'около 1100 токенов при лимите 40000', locations: [] },
        { check: 'revision_history_visible', level: 'warning', label: 'Видна история изменений документа', passed: false, inconclusive: true, detail: 'требование условия для сдачи через Google Docs; в git-канале не проверяется', locations: [] },
        { check: 'font', level: 'warning', label: 'Шрифт Arial 11, таблицы 10', passed: false, inconclusive: true, detail: 'проверяется только для .docx и Google Docs', locations: [] },
      ],
    },
    verdicts: [
      {
        criterion_id: 'c1',
        score: 1,
        confidence: 0.88,
        verdict: 'Декомпозиция выполнена по двум признакам — по функциям и по ролям, — и для каждого показан результат разбиения. Требование условия «минимум по двум признакам» закрыто.',
        evidence: [at('docs/lab1-booking.md', 'Декомпозиция выполнена по двум признакам: по функциям и по ролям.')],
        student_feedback: 'Оба признака названы явно, и по каждому видно, что получилось.',
        improvement_hint: '',
        needs_human_attention: false,
        attention_reason: '',
      },
      {
        criterion_id: 'c2',
        score: 0.5,
        confidence: 0.84,
        verdict: 'Внешние акторы перечислены, граница проведена: биллинг явно оставлен снаружи и вызывается по API.',
        evidence: [at('docs/lab1-booking.md', 'Внешние акторы: клиент клуба, администратор, платёжный провайдер,')],
        student_feedback: 'Граница системы проведена честно — видно, что снаружи, а что внутри.',
        improvement_hint: '',
        needs_human_attention: false,
        attention_reason: '',
      },
      {
        criterion_id: 'c3',
        score: 0.5,
        confidence: 0.66,
        verdict: 'Контракты заданы: методы, тела запросов и коды ответов. Не описаны ошибки — условие требует «входы, выходы и ошибки», а в примере только успешные пути.',
        evidence: [at('docs/lab1-booking.md', 'POST /bookings')],
        student_feedback: 'Формат запросов и ответов задан конкретно. Не хватает ошибочных ответов: что вернётся, когда слот уже заполнен.',
        improvement_hint: 'Добавьте коды ошибок с телами: занятый слот, чужая бронь, несуществующий слот.',
        needs_human_attention: false,
        attention_reason: '',
      },
      {
        criterion_id: 'c4',
        score: 0,
        confidence: 0.71,
        verdict: 'Сущности перечислены одной строкой, но модели данных нет: не названы поля, ключи и связи, обоснование выбора отсутствует.',
        evidence: [at('docs/lab1-booking.md', 'Основные сущности: Slot, Booking, Client. Slot хранит вместимость,')],
        student_feedback: 'Раздел про данные сейчас самый тонкий: по нему нельзя восстановить схему.',
        improvement_hint: 'Опишите поля и связи Slot–Booking–Client и объясните, где хранится вместимость и как считается остаток мест.',
        needs_human_attention: false,
        attention_reason: '',
      },
      {
        criterion_id: 'c5',
        score: 0.5,
        confidence: 0.92,
        verdict: 'Контекстная диаграмма C4 построена в корректной нотации. Компонентной диаграммы нет, а условие требует обе — контекст и компоненты одного контейнера.',
        evidence: [at('docs/lab1-booking.md', 'C4Context')],
        student_feedback: 'Контекст нарисован по нотации, это заметно лучше произвольного flowchart. Осталась вторая диаграмма.',
        improvement_hint: 'Добавьте C4Component для контейнера бронирования.',
        needs_human_attention: false,
        attention_reason: '',
      },
      {
        criterion_id: 'c6',
        score: 0,
        confidence: 0.9,
        verdict: 'Нефункциональные требования сформулированы словами «быстро» и «высокая нагрузка». Чисел нет ни одного, проверить такое требование нельзя.',
        evidence: [at('docs/lab1-booking.md', 'Система должна работать быстро и выдерживать высокую нагрузку.')],
        student_feedback: 'Требование без числа невозможно ни проверить, ни нарушить.',
        improvement_hint: 'Назовите p95 отклика, целевой RPS и допустимую долю ошибок.',
        needs_human_attention: false,
        attention_reason: '',
      },
      {
        criterion_id: 'c7',
        score: 0.5,
        confidence: 0.79,
        verdict: 'Два сценария деградации описаны конкретно: очередь при отказе шлюза и режим только чтения при отказе базы.',
        evidence: [at('docs/lab1-booking.md', 'При недоступности СМС-шлюза напоминания складываются в очередь и')],
        student_feedback: 'Режим только чтения — хорошее решение: сервис остаётся полезным даже без записи.',
        improvement_hint: '',
        needs_human_attention: false,
        attention_reason: '',
      },
      {
        criterion_id: 'c8',
        score: 0.5,
        confidence: 0.81,
        verdict: 'Узкое место названо предметно — конкуренция за слот при массовом открытии расписания, — и предложен способ масштабирования.',
        evidence: [at('docs/lab1-booking.md', 'Узкое место — запись в слот при массовом открытии расписания: сотни')],
        student_feedback: 'Узкое место выбрано верно и описано через сценарий, а не абстрактно.',
        improvement_hint: '',
        needs_human_attention: false,
        attention_reason: '',
      },
      {
        criterion_id: 'c9',
        score: 0.5,
        confidence: 0.58,
        verdict: 'Один компромисс назван явно — простота синхронного бронирования против устойчивости к пику. Остальные решения приняты без объяснения альтернатив.',
        evidence: [at('docs/lab1-booking.md', 'Архитектура покрывает основные сценарии. Компромисс: синхронное')],
        student_feedback: 'Хорошо, что компромисс назван прямо. Дальше стоит так же разобрать выбор синхронного HTTP против событий.',
        improvement_hint: 'Добавьте по одной альтернативе к двум ключевым решениям и скажите, почему выбрали не её.',
        needs_human_attention: true,
        attention_reason: 'уверенность 0.58 — вердикт стоит перепроверить вручную',
      },
    ],
    needs_human_attention: true,
    attention_reasons: [
      'работа набрала ровно порог зачёта: любая правка балла меняет исход',
      'c9: уверенность 0.58 — вердикт стоит перепроверить вручную',
    ],
    partial_artifacts: [],
    tokens_in: 4180,
    tokens_out: 1120,
    cost_rub: 1.4,
    failed_criteria: [],
    evidence_coverage: 1,
  },
}

export const DEMO_SYSDESIGN_DETECT: DetectResponse = {
  bundle: BUNDLE,
  files: DEMO_SYSDESIGN_REVIEW.files,
  report: {
    overall_score: 0.44,
    confidence_low: 0.31,
    confidence_high: 0.58,
    label: 'низкая вероятность',
    declared_ai_usage: null,
    declaration_note: 'Условие лабораторной не требует заявлять использование ИИ.',
    mismatch: false,
    advisory: true,
    advisory_note:
      'Сигнал носит рекомендательный характер, не является доказательством нарушения и не влияет на балл автоматически. Решение принимает куратор.',
    limitations: [
      'Фрагменты короче 200 символов не оцениваются',
      'Перплексия недоступна: локальная модель не подключена',
      'Разметка mermaid и блоки кода исключены из анализа',
    ],
    tokens_in: 980,
    tokens_out: 140,
    cost_rub: 0.3,
    signals: [
      { kind: 'forensics', status: 'ok', score: 0.29, weight: 0.35, spans: [], findings: ['документ рос четырьмя коммитами за три дня'], note: '' },
      { kind: 'perplexity', status: 'unavailable', score: 0, weight: 0.25, spans: [], findings: [], note: 'локальная модель не настроена' },
      { kind: 'stylometry', status: 'ok', score: 0.63, weight: 0.15, spans: [], findings: ['оборот «Важно отметить, что» в разделе НФТ'], note: '' },
      { kind: 'judge', status: 'ok', score: 0.52, weight: 0.25, spans: [], findings: [], note: '' },
    ],
    spans: [
      {
        id: 'span-nfr',
        artifact: 'docs/lab1-booking.md',
        start: null,
        end: null,
        start_line: 66,
        end_line: 69,
        score: 0.71,
        signals: ['stylometry', 'judge'],
        reason:
          'Абзац общий и не привязан к системе: «отказоустойчивость является ключевым требованием современных распределённых систем». Ровный ритм, оборот «Важно отметить, что».',
        excerpt: 'Важно отметить, что отказоустойчивость является ключевым требованием современных…',
        ai_sensitive: true,
        reviewer_verdict: 'pending',
      },
    ],
  },
}
