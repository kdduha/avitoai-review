/** Адаптер трёх источников в один вид для панелей.
 *
 *  Проверяется не форма объекта, а правила, которые ломаются молча и выглядят
 *  при этом правдоподобно: номера строк из диффа, признак «в файле есть что
 *  показать» и запрет на пересчёт итога после правки балла.
 */

import { describe, expect, it } from 'vitest'
import type {
  ArtifactText,
  DetectionReport,
  Evidence,
  ReviewDraft,
  ReviewResponse,
  Rubric,
} from './backend'
import { buildWorkspace, withScore } from './workspace'
import { blankRubric, normalizeRubric } from './rubric'

function file(patch: Partial<ArtifactText> = {}): ArtifactText {
  const text = patch.text ?? 'a\nb\nc'
  return {
    path: 'main.go',
    role: 'submission',
    lang: 'go',
    partial: false,
    origin: 'excerpt',
    first_line: 1,
    last_line: text.split('\n').length,
    line_numbers: text.split('\n').map((_, index) => index + 1),
    changed_lines: '1–3',
    ...patch,
    text,
  } as ArtifactText
}

function evidence(patch: Partial<Evidence> = {}): Evidence {
  return { artifact: 'main.go', quote: 'b', status: 'valid', note: '', ...patch }
}

function draft(patch: Partial<ReviewDraft> = {}): ReviewDraft {
  return {
    assignment_id: 'demo-task1',
    rubric_title: 'Демо',
    verdicts: [],
    raw_score: 0,
    score: 0,
    max_score: 2,
    passed: false,
    pass_explanation: '',
    late_explanation: '',
    needs_human_attention: false,
    tokens_in: 100,
    tokens_out: 50,
    cost_rub: 1,
    ...patch,
  } as ReviewDraft
}

function response(patch: Partial<ReviewResponse> = {}): ReviewResponse {
  return {
    bundle: {
      source: 'github_pr',
      origin_url: 'https://github.com/org/repo/pull/42',
      retrieved_at: '2026-09-01T10:00:00Z',
      student_ref: { internal_id: '171345' },
      submitted_at: '2026-09-01T09:00:00Z',
    },
    files: [file()],
    draft: draft(),
    ...patch,
  } as ReviewResponse
}

function rubric(): Rubric {
  return normalizeRubric({
    ...blankRubric(),
    assignment_id: 'demo-task1',
    scale: { total_max: 2, pass_threshold: null, step: 0.5 },
    criteria: [
      {
        id: 'c1',
        title: 'Хендлеры',
        max_score: 2,
        min_score_for_pass: null,
        weight: 1,
        description: '',
        checks: ['есть /ping'],
        anchors: {},
        evidence_required: true,
        auto_verifiable: false,
        ai_sensitive: false,
      },
    ],
  })
}

describe('номера строк', () => {
  /* У фрагмента из диффа номера идут с пропусками: 1–2, затем 119–120.
     Нумерация по позиции увела бы цитату на 120-ю строку в четвёртую. */
  it('берутся из line_numbers, когда их столько же, сколько строк', () => {
    const workspace = buildWorkspace(
      'r1',
      response({ files: [file({ text: 'a\nb\nc\nd', line_numbers: [1, 2, 119, 120] })] }),
      rubric(),
    )
    expect(workspace.files[0].lineNumbers).toEqual([1, 2, 119, 120])
  })

  it('достраиваются от first_line, если сервер прислал их не столько', () => {
    const workspace = buildWorkspace(
      'r1',
      response({ files: [file({ text: 'a\nb\nc', line_numbers: [7], first_line: 7 })] }),
      rubric(),
    )
    expect(workspace.files[0].lineNumbers).toEqual([7, 8, 9])
  })

  it('пустой first_line не уводит нумерацию в ноль', () => {
    const workspace = buildWorkspace(
      'r1',
      response({ files: [file({ text: 'a\nb', line_numbers: [], first_line: 0 })] }),
      rubric(),
    )
    expect(workspace.files[0].lineNumbers).toEqual([1, 2])
  })
})

describe('отметка «в файле есть что показать»', () => {
  const verdict = (items: Evidence[]) =>
    response({
      draft: draft({
        verdicts: [
          {
            criterion_id: 'c1',
            score: 1,
            verdict: 'ок',
            evidence: items,
          },
        ] as ReviewDraft['verdicts'],
      }),
    })

  it('подтверждённая цитата отмечает файл', () => {
    const workspace = buildWorkspace('r1', verdict([evidence()]), rubric())
    expect(workspace.files[0].hasFindings).toBe(true)
  })

  /* Несошедшаяся цитата — не находка: по ней некуда вести. */
  it('несошедшаяся цитата файл не отмечает', () => {
    const workspace = buildWorkspace('r1', verdict([evidence({ status: 'wrong_location' })]), rubric())
    expect(workspace.files[0].hasFindings).toBe(false)
  })

  it('спан детектора отмечает файл', () => {
    const report = {
      overall_score: 0.7,
      signals: [{ kind: 'forensics', status: 'ok', score: 0.7, weight: 0.35 }],
      spans: [{ id: 's1', artifact: 'main.go', reason: 'ровный ритм', score: 0.7 }],
      limitations: [],
    } as unknown as DetectionReport
    const workspace = buildWorkspace('r1', response({ detection: report }), rubric())
    expect(workspace.files[0].hasFindings).toBe(true)
  })
})

describe('детектор внутри ответа ревью', () => {
  it('null значит «не просили»', () => {
    expect(buildWorkspace('r1', response(), rubric()).detection).toBeNull()
  })

  it('отчёт доезжает до вида как есть', () => {
    const report = { overall_score: 0.4, signals: [], spans: [], limitations: ['нечего сказать'] } as unknown as DetectionReport
    const workspace = buildWorkspace('r1', response({ detection: report }), rubric())
    expect(workspace.detection?.limitations).toEqual(['нечего сказать'])
  })

  it('токены и стоимость складываются с расходом детектора', () => {
    const report = { tokens_in: 400, tokens_out: 20, cost_rub: 0.5, signals: [], spans: [], limitations: [] } as unknown as DetectionReport
    const workspace = buildWorkspace('r1', response({ detection: report }), rubric())
    expect(workspace.tokensIn).toBe(500)
    expect(workspace.tokensOut).toBe(70)
    expect(workspace.costRub).toBe(1.5)
  })
})

describe('вердикт соединяется с рубрикой', () => {
  const workspace = () =>
    buildWorkspace(
      'r1',
      response({
        draft: draft({
          verdicts: [{ criterion_id: 'c1', score: 1, verdict: 'ок' }] as ReviewDraft['verdicts'],
        }),
      }),
      rubric(),
    )

  it('название, максимум и проверочные пункты берутся из рубрики', () => {
    const [first] = workspace().verdicts
    expect(first.title).toBe('Хендлеры')
    expect(first.maxScore).toBe(2)
    expect(first.checks).toEqual(['есть /ping'])
  })

  it('шаг правки балла берётся из шкалы задания, а не единица', () => {
    expect(workspace().scoreStep).toBe(0.5)
  })

  it('неизвестный критерий показывается идентификатором, а не пропадает', () => {
    const built = buildWorkspace(
      'r1',
      response({
        draft: draft({
          verdicts: [{ criterion_id: 'c-нет-в-рубрике', score: 0, verdict: '' }] as ReviewDraft['verdicts'],
        }),
      }),
      rubric(),
    )
    expect(built.verdicts[0].title).toBe('c-нет-в-рубрике')
  })
})

describe('правка балла куратором', () => {
  const base = () =>
    buildWorkspace(
      'r1',
      response({
        draft: draft({
          score: 2,
          raw_score: 2,
          passed: true,
          verdicts: [{ criterion_id: 'c1', score: 2, verdict: 'ок' }] as ReviewDraft['verdicts'],
        }),
      }),
      rubric(),
    )

  it('сумма по критериям считается с весами', () => {
    const next = withScore(base(), 'c1', 1.5)
    expect(next.rawScore).toBe(1.5)
  })

  /* Итог сервера не трогаем: у агрегатора веса, шаг, обязательные минимумы и
     штраф за просрочку — правдоподобное число рядом с объяснением сервера
     хуже, чем честная пометка «пересчитает сервер». */
  it('итог сервера не пересчитывается, а помечается правленым', () => {
    const next = withScore(base(), 'c1', 1.5)
    expect(next.score).toBe(2)
    expect(next.edited).toBe(true)
    expect(next.verdicts[0].edited).toBe(true)
  })

  it('правка чужого критерия ничего не меняет', () => {
    const next = withScore(base(), 'нет-такого', 0)
    expect(next.rawScore).toBe(2)
    expect(next.verdicts[0].edited).toBe(false)
  })
})
