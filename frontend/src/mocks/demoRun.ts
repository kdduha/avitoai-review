/** Демо-прогон в формате ответов бэкенда.
 *
 *  Важно, что он именно в формате `/review` и `/detect`, а не в собственном:
 *  живой прогон и демо проходят через один и тот же адаптер и рисуются одним
 *  и тем же кодом. Если бы демо имело свою форму, расхождение с сервером
 *  всплыло бы только на живом ключе.
 */

import type { DetectResponse, ReviewResponse, SubmissionBundle } from '@/lib/backend'
import { DEMO_FILES } from './files'

export const DEMO_RUN_ID = 'demo'

function locate(path: string, quote: string): { start: number; end: number } | null {
  const file = DEMO_FILES.find((item) => item.path === path)
  if (!file) return null
  const lines = file.text.split('\n')
  const needle = quote.split('\n')[0].trim()
  const index = lines.findIndex((line) => line.trim() === needle)
  if (index === -1) return null
  return { start: index + file.firstLine, end: index + file.firstLine + quote.split('\n').length - 1 }
}

function evidence(artifact: string, quote: string) {
  const at = locate(artifact, quote)
  return {
    artifact,
    start_line: at?.start ?? null,
    end_line: at?.end ?? null,
    quote,
    status: at ? ('valid' as const) : ('wrong_location' as const),
    char_start: null,
    char_end: null,
    note: at ? '' : 'фрагмент не найден в указанных строках',
  }
}

const BUNDLE: SubmissionBundle = {
  submission_id: 'demo-go-task1',
  source: 'github_pr',
  origin_url: 'https://github.com/ai-talent-hub-avito/homework_examples/pull/214',
  retrieved_at: '2026-09-02T14:05:00+03:00',
  student_ref: { internal_id: 'S-1043', external_handles: {} },
  submitted_at: '2026-09-02T17:12:00+03:00',
  deadline_at: '2026-09-02T21:00:00+03:00',
  assignment_id: null,
  base_ref: 'main',
  head_ref: 'feature/boilerplate',
  artifacts: [],
  revisions: [],
  repo: null,
} as unknown as SubmissionBundle

export const DEMO_REVIEW: ReviewResponse = {
  submission_id: 'demo-run',
  bundle: BUNDLE,
  files: DEMO_FILES.map((file) => ({
    path: file.path,
    role: 'solution',
    lang: file.lang,
    partial: file.partial,
    origin: file.origin,
    first_line: file.firstLine,
    last_line: file.firstLine + file.text.split('\n').length - 1,
    line_numbers: file.text.split('\n').map((_, index) => file.firstLine + index),
    changed_lines: file.changedLines,
    text: file.text,
  })),
  draft: {
    assignment_id: 'go-task1',
    rubric_title: 'Создание boilerplate сервиса, поднятие веб-сервера',
    raw_score: 8,
    score: 8,
    max_score: 10,
    passed: true,
    pass_explanation: 'Порог зачёта — 6 из 10. Обязательных минимумов по критериям не провалено.',
    late_explanation: 'сдано в срок',
    gate_facts: [
      'директории cmd/ и internal/ на месте',
      'строка «Shutting down service-courier» найдена в cmd/main.go',
      'файл .env.example в репозитории отсутствует',
    ],
    gate: {
      status: 'warning',
      facts: [],
      outcomes: [
        { check: 'required_paths', level: 'warning', label: 'Разделение на cmd/ и internal/', passed: true, inconclusive: false, detail: 'обе директории на месте', locations: ['cmd/main.go', 'internal/handler/health.go'] },
        { check: 'code_contains', level: 'blocking', label: 'Сообщение о завершении работы в логе', passed: true, inconclusive: false, detail: '«Shutting down service-courier»', locations: ['cmd/main.go:52'] },
        { check: 'code_contains', level: 'warning', label: 'Переопределение порта флагом', passed: true, inconclusive: false, detail: 'flag.String("port", …)', locations: ['cmd/main.go:21'] },
        { check: 'code_contains', level: 'warning', label: 'Эндпоинт GET /ping', passed: true, inconclusive: false, detail: 'маршрут зарегистрирован', locations: ['internal/handler/health.go:8'] },
        { check: 'code_contains', level: 'warning', label: 'Эндпоинт HEAD /healthcheck', passed: true, inconclusive: false, detail: 'маршрут зарегистрирован', locations: ['internal/handler/health.go:9'] },
        { check: 'code_contains', level: 'warning', label: 'Обработка сигналов завершения', passed: true, inconclusive: false, detail: 'signal.NotifyContext с SIGINT/SIGTERM', locations: ['cmd/main.go:47'] },
        { check: 'required_paths', level: 'warning', label: 'Файл .env.example', passed: false, inconclusive: false, detail: 'в репозитории не найден, хотя README ссылается на переменные окружения', locations: [] },
        { check: 'code_absent', level: 'warning', label: 'Реальный .env не закоммичен', passed: true, inconclusive: false, detail: 'в индексе нет', locations: [] },
      ],
    },
    verdicts: [
      {
        criterion_id: 'c1',
        score: 2,
        confidence: 0.9,
        verdict:
          'Раскладка соответствует golang-standards: точка входа в cmd/main.go, внутренние пакеты в internal/handler и internal/config. Импорт internal снаружи модуля невозможен по определению.',
        evidence: [evidence('cmd/main.go', 'func main() {')],
        student_feedback: 'Слои разложены правильно с первого коммита — это как раз то, чего просит условие.',
        improvement_hint: '',
        needs_human_attention: false,
        attention_reason: '',
      },
      {
        criterion_id: 'c2',
        score: 1,
        confidence: 0.72,
        verdict:
          'Порт переопределяется флагом --port, значение по умолчанию берётся из окружения. Но .env не читается: config.Load ходит только в os.Getenv, а файла .env.example в репозитории нет — воспроизвести конфигурацию по репозиторию нельзя.',
        evidence: [
          evidence('internal/config/config.go', 'Port: getenv("PORT", "8080"),'),
          evidence('cmd/main.go', 'port := flag.String("port", cfg.Port, "порт HTTP-сервера")'),
        ],
        student_feedback:
          'Приоритет «флаг важнее переменной окружения» выбран верно. Не хватает самого .env: сейчас конфигурация живёт только в окружении запускающего.',
        improvement_hint: 'Добавьте .env.example со списком переменных и чтение .env (godotenv или аналог) на старте.',
        needs_human_attention: false,
        attention_reason: '',
      },
      {
        criterion_id: 'c3',
        score: 2,
        confidence: 0.86,
        verdict:
          'Оба эндпоинта зарегистрированы и отвечают: /ping возвращает pong, /healthcheck — пустой 200, что для HEAD корректно.',
        evidence: [evidence('internal/handler/health.go', 'mux.HandleFunc("/ping", ping)')],
        student_feedback: 'Эндпоинты на месте и ведут себя ровно так, как описано в условии.',
        improvement_hint: '',
        needs_human_attention: false,
        attention_reason: '',
      },
      {
        criterion_id: 'c4',
        score: 2,
        confidence: 0.88,
        verdict:
          'signal.NotifyContext ловит SIGINT и SIGTERM, сервер гасится через Shutdown с таймаутом 5 секунд, сообщение в лог пишется до остановки.',
        evidence: [
          evidence('cmd/main.go', 'ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)'),
        ],
        student_feedback: 'Завершение сделано полностью: и сигнал, и таймаут, и лог.',
        improvement_hint: '',
        needs_human_attention: false,
        attention_reason: '',
      },
      {
        criterion_id: 'c5',
        score: 1,
        confidence: 0.58,
        verdict:
          'Код читается, имена по делу. Минус за необработанную ошибку w.Write в обоих хендлерах и за то, что весь текст README написан в отрыве от кода: описанного в нём чтения .env в проекте нет.',
        evidence: [evidence('internal/handler/health.go', 'w.Write([]byte("pong"))')],
        student_feedback:
          'С кодом всё в порядке. Приведите README в соответствие с тем, что действительно реализовано.',
        improvement_hint: 'Обработайте ошибку записи ответа и синхронизируйте README с кодом.',
        needs_human_attention: true,
        attention_reason: 'уверенность 0.58 — вердикт стоит перепроверить вручную',
      },
    ],
    needs_human_attention: true,
    attention_reasons: ['c5: уверенность 0.58 — вердикт стоит перепроверить вручную'],
    partial_artifacts: [],
    tokens_in: 6120,
    tokens_out: 980,
    cost_rub: 1.9,
    failed_criteria: [],
    evidence_coverage: 1,
  },
}

export const DEMO_DETECT: DetectResponse = {
  bundle: BUNDLE,
  files: DEMO_REVIEW.files,
  report: {
    overall_score: 0.68,
    confidence_low: 0.55,
    confidence_high: 0.8,
    label: 'средняя вероятность',
    declared_ai_usage: false,
    declaration_note: 'Блок с декларацией об использовании ИИ в работе не найден.',
    mismatch: true,
    advisory: true,
    advisory_note:
      'Сигнал носит рекомендательный характер, не является доказательством нарушения и не влияет на балл автоматически. Решение принимает ревьюер.',
    limitations: [
      'Фрагменты короче 200 символов не оцениваются',
      'Перплексия недоступна: локальная модель не подключена',
      'Шаблонный код и сгенерированные файлы исключены по allowlist',
    ],
    tokens_in: 1840,
    tokens_out: 260,
    cost_rub: 0.6,
    signals: [
      { kind: 'forensics', status: 'ok', score: 0.62, weight: 0.35, spans: [], findings: ['вся работа одним коммитом «init»'], note: '' },
      { kind: 'perplexity', status: 'unavailable', score: 0, weight: 0.25, spans: [], findings: [], note: 'локальная модель не настроена' },
      { kind: 'stylometry', status: 'ok', score: 0.71, weight: 0.15, spans: [], findings: ['клише «Важно отметить, что»', 'нулевая плотность TODO'], note: '' },
      { kind: 'judge', status: 'ok', score: 0.78, weight: 0.25, spans: [], findings: [], note: '' },
    ],
    spans: [
      {
        id: 'span-readme',
        artifact: 'README.md',
        start: null,
        end: null,
        start_line: 8,
        end_line: 15,
        score: 0.84,
        signals: ['stylometry', 'judge'],
        reason:
          'Обороты «Важно отметить, что» и «Следует отметить», ровный ритм абзаца и описание того, чего в коде нет.',
        excerpt: 'Важно отметить, что подобное разделение обеспечивает высокую степень поддерживаемости…',
        ai_sensitive: true,
        reviewer_verdict: 'pending',
      },
      {
        id: 'span-main',
        artifact: 'cmd/main.go',
        start: null,
        end: null,
        start_line: 1,
        end_line: 54,
        score: 0.61,
        signals: ['forensics'],
        reason: 'Весь проект добавлен одним коммитом «init» за 4 минуты, промежуточных правок нет.',
        excerpt: 'commit 8f2a1c0 «init» · +160 −0 · 02.09 17:08 → 17:12',
        ai_sensitive: false,
        reviewer_verdict: 'pending',
      },
    ],
  },
}
