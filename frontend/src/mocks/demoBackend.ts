/** Демо-прогон по основам backend-разработки: FastAPI-сервис модерации
 *  объявлений против рубрики `backend-task1`.
 *
 *  Работа среднего уровня, как в примерах организаторов: вся логика живёт в
 *  роутере, слоя services нет, обработчик возвращает объект вместо голого
 *  булева, а параметризации в тестах не хватает до третьего балла. Это даёт
 *  единственный случай, которого не было в двух других прогонах, — оценку с
 *  промежуточной градацией 0.5 из условия.
 */

import type { DetectResponse, ReviewResponse, SubmissionBundle } from '@/lib/backend'
import { locator, toArtifacts, type DemoFile } from './demoUtils'

export const DEMO_BACKEND_ID = 'demo-backend'

const MAIN = `from fastapi import FastAPI

from routers.moderation import router as moderation_router

app = FastAPI(title="Moderation service")
app.include_router(moderation_router)


@app.get("/")
def root():
    return {"message": "Hello World"}
`

const ROUTER = `from fastapi import APIRouter, HTTPException

from models.predict import PredictRequest, PredictResponse

router = APIRouter()


@router.post("/predict", response_model=PredictResponse)
def predict(payload: PredictRequest) -> PredictResponse:
    try:
        if payload.is_verified_seller:
            is_valid = True
        else:
            is_valid = payload.images_qty > 0
        return PredictResponse(is_valid=is_valid)
    except Exception:
        raise HTTPException(status_code=500, detail="Не удалось проверить объявление")
`

const MODELS = `from pydantic import BaseModel, Field


class PredictRequest(BaseModel):
    seller_id: int = Field(..., ge=0)
    is_verified_seller: bool
    item_id: int = Field(..., ge=0)
    name: str = Field(..., min_length=1)
    description: str
    category: int = Field(..., ge=0)
    images_qty: int = Field(..., ge=0)


class PredictResponse(BaseModel):
    is_valid: bool
`

const TESTS = `from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def payload(**overrides):
    body = {
        "seller_id": 1,
        "is_verified_seller": True,
        "item_id": 10,
        "name": "Велосипед",
        "description": "Почти новый",
        "category": 3,
        "images_qty": 2,
    }
    body.update(overrides)
    return body


def test_verified_seller_is_valid():
    response = client.post("/predict", json=payload())
    assert response.status_code == 200
    assert response.json()["is_valid"] is True


def test_unverified_without_images_is_invalid():
    response = client.post("/predict", json=payload(is_verified_seller=False, images_qty=0))
    assert response.json()["is_valid"] is False


def test_unverified_with_images_is_valid():
    response = client.post("/predict", json=payload(is_verified_seller=False, images_qty=1))
    assert response.json()["is_valid"] is True


def test_missing_field_is_rejected():
    body = payload()
    del body["images_qty"]
    response = client.post("/predict", json=body)
    assert response.status_code == 422


def test_negative_images_qty_is_rejected():
    response = client.post("/predict", json=payload(images_qty=-1))
    assert response.status_code == 400
`

const FILES: DemoFile[] = [
  { path: 'main.py', lang: 'python', firstLine: 1, partial: false, origin: 'fetched', changedLines: '1–11', text: MAIN },
  { path: 'routers/moderation.py', lang: 'python', firstLine: 1, partial: false, origin: 'fetched', changedLines: '1–19', text: ROUTER },
  { path: 'models/predict.py', lang: 'python', firstLine: 1, partial: false, origin: 'fetched', changedLines: '1–17', text: MODELS },
  { path: 'tests/test_predict.py', lang: 'python', firstLine: 1, partial: false, origin: 'fetched', changedLines: '1–48', text: TESTS },
]

const at = locator(FILES)

const BUNDLE = {
  submission_id: 'demo-backend-task1',
  source: 'github_pr',
  origin_url: 'https://github.com/ai-talent-hub-avito/homework_examples/pull/91',
  retrieved_at: '2026-09-03T09:10:00+03:00',
  student_ref: { internal_id: '204877', external_handles: {} },
  submitted_at: '2026-09-03T22:47:00+03:00',
  deadline_at: '2026-09-02T21:00:00+03:00',
  assignment_id: null,
  base_ref: 'main',
  head_ref: 'hw1',
  artifacts: [],
  revisions: [],
  repo: null,
} as unknown as SubmissionBundle

export const DEMO_BACKEND_REVIEW: ReviewResponse = {
  submission_id: 'demo-backend',
  bundle: BUNDLE,
  files: toArtifacts(FILES),
  draft: {
    assignment_id: 'backend-task1',
    rubric_title: 'Основы веб-разработки: обработчик predict и тесты',
    raw_score: 6.5,
    score: 5.5,
    max_score: 10,
    passed: false,
    pass_explanation: 'Порог зачёта — 6 из 10.',
    late_explanation: 'просрочка 1 дн., штраф −1',
    gate_facts: [
      'обработчик predict на месте',
      'каталог tests/ на месте',
      'параметризации в тестах нет',
    ],
    gate: {
      status: 'warning',
      facts: [],
      outcomes: [
        { check: 'code_contains', level: 'blocking', label: 'Обработчик predict', passed: true, inconclusive: false, detail: 'единственный, в routers/moderation.py', locations: ['routers/moderation.py:9'] },
        { check: 'code_contains', level: 'warning', label: 'Сервис на FastAPI', passed: true, inconclusive: false, detail: 'from fastapi import FastAPI', locations: ['main.py:1'] },
        { check: 'code_contains', level: 'warning', label: 'Поле is_verified_seller во входной модели', passed: true, inconclusive: false, detail: '', locations: ['models/predict.py:6'] },
        { check: 'code_contains', level: 'warning', label: 'Поле images_qty во входной модели', passed: true, inconclusive: false, detail: '', locations: ['models/predict.py:11'] },
        { check: 'required_paths', level: 'warning', label: 'Каталог tests/', passed: true, inconclusive: false, detail: 'tests/test_predict.py', locations: ['tests/test_predict.py'] },
        { check: 'code_contains', level: 'warning', label: 'Параметризация в тестах', passed: false, inconclusive: false, detail: 'pytest.mark.parametrize не встречается', locations: [] },
        { check: 'code_absent', level: 'warning', label: 'Скомпилированные файлы не закоммичены', passed: true, inconclusive: false, detail: 'в индексе нет', locations: [] },
      ],
    },
    verdicts: [
      {
        criterion_id: 'c1',
        score: 1,
        confidence: 0.87,
        verdict:
          'Обработчик соответствует API: путь, метод и все семь полей на месте, валидация типов и границ задана через Field. Но условие требует вернуть «лишь одно булево значение», а обработчик отдаёт объект PredictResponse — до второго балла не хватает именно этого.',
        evidence: [
          at('routers/moderation.py', 'def predict(payload: PredictRequest) -> PredictResponse:'),
          at('models/predict.py', 'class PredictResponse(BaseModel):'),
        ],
        student_feedback:
          'Валидация входа сделана аккуратно — границы и обязательность полей заданы декларативно. Осталось привести ответ к тому, что просит условие.',
        improvement_hint: 'Верните bool напрямую: response_model=bool и return is_valid.',
        needs_human_attention: false,
        attention_reason: '',
      },
      {
        criterion_id: 'c2',
        score: 1,
        confidence: 0.94,
        verdict:
          'Логика в точности как в условии: подтверждённый продавец публикует всегда, неподтверждённый — только при наличии изображений.',
        evidence: [at('routers/moderation.py', 'is_valid = payload.images_qty > 0')],
        student_feedback: 'Правило перенесено из условия без искажений.',
        improvement_hint: '',
        needs_human_attention: false,
        attention_reason: '',
      },
      {
        criterion_id: 'c3',
        score: 0,
        confidence: 0.9,
        verdict:
          'Слоя services нет: бизнес-правило живёт прямо в теле обработчика. По рубрике это ноль — балл даётся за выделенные уровни routes и services.',
        evidence: [at('routers/moderation.py', 'if payload.is_verified_seller:')],
        student_feedback:
          'Пока правило одно, соблазн оставить его в роутере понятен. Но условие оценивает именно разделение — и на втором правиле роутер начнёт разрастаться.',
        improvement_hint: 'Вынесите правило в services/moderation.py и вызывайте его из роутера.',
        needs_human_attention: false,
        attention_reason: '',
      },
      {
        criterion_id: 'c4',
        score: 1,
        confidence: 0.72,
        verdict: 'Приложение собирается: роутер подключается в main.py, импорты разрешаются, точка входа для fastapi dev на месте.',
        evidence: [at('main.py', 'app.include_router(moderation_router)')],
        student_feedback: 'Запуск ровный, ничего доруками доводить не нужно.',
        improvement_hint: '',
        needs_human_attention: false,
        attention_reason: '',
      },
      {
        criterion_id: 'c5',
        score: 2,
        confidence: 0.83,
        verdict:
          'Пять тестов покрывают позитивный и негативный пути, отсутствующее поле и отрицательное значение — corner-cases закрыты. Третий балл рубрика даёт за параметризацию, а её нет: четыре теста отличаются одним значением и дублируют друг друга.',
        evidence: [at('tests/test_predict.py', 'def test_unverified_without_images_is_invalid():')],
        student_feedback:
          'Набор сценариев подобран правильно, включая негативные. Их же можно записать одной параметризованной функцией — это и есть третий балл.',
        improvement_hint: 'Соберите случаи в @pytest.mark.parametrize с парами (is_verified_seller, images_qty, ожидание).',
        needs_human_attention: false,
        attention_reason: '',
      },
      {
        criterion_id: 'c6',
        score: 0.5,
        confidence: 0.61,
        verdict:
          'Тесты запускаются, но последний падает: при images_qty = -1 pydantic отдаёт 422, а тест ждёт 400. По рубрике это промежуточная градация 0.5 — «запускаются, но не все проходят».',
        evidence: [at('tests/test_predict.py', 'assert response.status_code == 400')],
        student_feedback:
          'Ожидание в последнем тесте разошлось с поведением FastAPI: ошибка валидации схемы — это 422, а не 400.',
        improvement_hint: 'Либо ждите 422, либо перехватывайте RequestValidationError и отдавайте 400 осознанно.',
        needs_human_attention: true,
        attention_reason: 'уверенность 0.61 — стоит прогнать тесты вручную',
      },
      {
        criterion_id: 'c7',
        score: 1,
        confidence: 0.68,
        verdict:
          'Неизвестная ошибка бизнес-логики заворачивается в 500 с понятным сообщением, ошибка валидации отдаётся фреймворком. Требование рубрики выполнено.',
        evidence: [at('routers/moderation.py', 'raise HTTPException(status_code=500, detail="Не удалось проверить объявление")')],
        student_feedback: 'Пятисотка с человеческим текстом — то, что нужно.',
        improvement_hint: '',
        needs_human_attention: false,
        attention_reason: '',
      },
    ],
    needs_human_attention: true,
    attention_reasons: [
      'после штрафа за просрочку работа не добирает до зачёта половину балла',
      'c6: уверенность 0.61 — стоит прогнать тесты вручную',
    ],
    partial_artifacts: [],
    tokens_in: 5340,
    tokens_out: 1290,
    cost_rub: 1.8,
    failed_criteria: [],
    evidence_coverage: 1,
  },
}

export const DEMO_BACKEND_DETECT: DetectResponse = {
  bundle: BUNDLE,
  files: DEMO_BACKEND_REVIEW.files,
  report: {
    overall_score: 0.22,
    confidence_low: 0.12,
    confidence_high: 0.35,
    label: 'низкая вероятность',
    declared_ai_usage: null,
    declaration_note: 'Условие этого задания не требует заявлять использование ИИ.',
    mismatch: false,
    advisory: true,
    advisory_note:
      'Сигнал носит рекомендательный характер, не является доказательством нарушения и не влияет на балл автоматически. Решение принимает куратор.',
    limitations: [
      'Фрагменты короче 200 символов не оцениваются',
      'Перплексия недоступна: локальная модель не подключена',
      'Скелет из условия исключён из анализа по allowlist',
    ],
    tokens_in: 720,
    tokens_out: 90,
    cost_rub: 0.2,
    signals: [
      { kind: 'forensics', status: 'ok', score: 0.18, weight: 0.35, spans: [], findings: ['шесть коммитов за два дня, средний +30 строк'], note: '' },
      { kind: 'perplexity', status: 'unavailable', score: 0, weight: 0.25, spans: [], findings: [], note: 'локальная модель не настроена' },
      { kind: 'stylometry', status: 'ok', score: 0.31, weight: 0.15, spans: [], findings: [], note: '' },
      { kind: 'judge', status: 'ok', score: 0.24, weight: 0.25, spans: [], findings: [], note: '' },
    ],
    spans: [],
  },
}
