"""HTTP-слой: ревью и детектор как ручки, а не как библиотека.

Сеть не трогаем: ingest подменяется заглушкой, модель — фейковым провайдером.
Проверяется то, за что отвечает слой: коды ошибок, состав ответа и то, что
блокирующий разбор не выполняется в событийном цикле.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from conftest import as_role
from factories import GO_MAIN, artifact, go_bundle, go_rubric, partial_artifact
from fastapi.testclient import TestClient

from avito_reviewer.ai import AIService
from avito_reviewer.ai.llm import fake_gateway
from avito_reviewer.ai.rubric import RubricStore
from avito_reviewer.app.main import create_app
from avito_reviewer.config import AIConfig
from avito_reviewer.distribution import ReviewerStore
from avito_reviewer.ingest import InvalidLinkError, ProviderFetchError

PROFILE = json.dumps(
    {
        "topics": ["gRPC"],
        "stack": ["go"],
        "complexity": 0.4,
        "est_review_minutes": 25,
        "rationale": "один файл",
    },
    ensure_ascii=False,
)

VERDICTS = json.dumps(
    {
        "verdicts": [
            {
                "criterion_id": cid,
                "score": 2,
                "confidence": 0.9,
                "verdict": f"разбор {cid}",
                "evidence": [
                    {"artifact": "cmd/main.go", "start_line": 11, "end_line": 11,
                     "quote": 'r.Get("/ping", handlePing)'}
                ],
                "student_feedback": "",
                "improvement_hint": "",
                "needs_human_attention": False,
                "attention_reason": "",
            }
            for cid in ("c1", "c2", "c3")
        ]
    },
    ensure_ascii=False,
)

LINK = "https://github.com/acme/courier/pull/7"


class StubIngest:
    """Заглушка ingest: ручки не должны требовать сети, чтобы быть проверяемыми."""

    def __init__(self, bundle=None, error: Exception | None = None) -> None:
        self.bundle = bundle if bundle is not None else go_bundle()
        self.error = error
        self.calls = 0
        # Двойник обязан совпадать с настоящим сервисом по составу: на этом
        # расхождении здесь уже дважды пряталась ошибка.
        self.author_salt = ""

    async def ingest(self, link, source, *, context=None):
        self.calls += 1
        if self.error:
            raise self.error
        # Настоящий провайдер выдаёт новый `submission_id` на каждый ingest —
        # это не производное от содержимого PR, а метка одного прогона.
        # Двойник обязан вести себя так же: иначе повторный /review на одном
        # и том же стабе бьётся о уникальность первичного ключа `submissions`.
        return self.bundle.model_copy(update={"submission_id": uuid4()})

    async def fetch_content(self, content_ref):
        return None

    async def aclose(self):
        return None

    @property
    def sources(self):
        return []


@pytest.fixture
def make_client(tmp_path):
    def build(
        *, ingest=None, responses=None, rubrics=True, writable=False, reviewers=True, role="admin"
    ):
        app = create_app()
        client = TestClient(app)
        client.__enter__()
        gateway, provider = fake_gateway(responses if responses is not None else [VERDICTS])
        app.state.ingest = ingest or StubIngest()
        app.state.ai = AIService(AIConfig(), gateway=gateway, resolver=app.state.ingest)
        if not rubrics:
            app.state.rubrics = RubricStore("нет такого каталога")
        if not reviewers:
            app.state.reviewers = ReviewerStore("нет такого каталога")
        if writable:
            # Каталог на запись: подтверждение рубрики не должно трогать рабочий.
            app.state.rubrics = RubricStore(tmp_path)
        if role is not None:
            # `admin` по умолчанию: у него есть доступ и к тому, что видит
            # ревьюер, и к тому, что видит только admin (рубрики, /cost) —
            # большинству тестов ниже нужен не конкретный уровень, а «пропустят».
            as_role(client, role)
        return client, provider

    return build


# --------------------------------------------------------------------------- #
# каталог рубрик
# --------------------------------------------------------------------------- #

def test_rubrics_are_listed(make_client):
    client, _ = make_client()
    listed = client.get("/rubrics").json()
    assert any(item["assignment_id"] == "go-task1" for item in listed)


def test_one_rubric_comes_back_in_full(make_client):
    """Ревьюеру нужны критерии и якоря, чтобы понимать, против чего стоял вердикт."""
    client, _ = make_client()
    rubric = client.get("/rubrics/go-task1").json()
    assert rubric["criteria"][0]["checks"]
    assert client.get("/rubrics/нет-такой").status_code == 404


# --------------------------------------------------------------------------- #
# ревью
# --------------------------------------------------------------------------- #

def test_review_returns_bundle_files_and_draft(make_client):
    """Одним запросом — всё, что нужно рабочему месту: иначе три похода в GitHub."""
    client, _ = make_client()
    body = client.post("/review", json={"link": LINK, "rubric_id": "go-task1"}).json()

    assert body["bundle"]["origin_url"] == LINK
    assert [f["path"] for f in body["files"]] == ["cmd/main.go"]
    assert body["files"][0]["text"].startswith("package main")
    assert body["draft"]["score"] > 0
    assert body["draft"]["verdicts"][0]["evidence"][0]["status"] == "valid"


def test_review_accepts_an_inline_rubric(make_client):
    """Rubric Compiler отдаёт рубрику на подтверждение — в каталоге её ещё нет."""
    client, _ = make_client()
    response = client.post(
        "/review",
        json={"link": LINK, "rubric": go_rubric().model_dump(mode="json")},
    )
    assert response.status_code == 200
    assert len(response.json()["draft"]["verdicts"]) == 3


def test_review_demands_exactly_one_rubric(make_client):
    client, _ = make_client()
    assert client.post("/review", json={"link": LINK}).status_code == 422
    assert client.post(
        "/review",
        json={"link": LINK, "rubric_id": "go-task1",
              "rubric": go_rubric().model_dump(mode="json")},
    ).status_code == 422


def test_unknown_rubric_is_404_and_names_what_exists(make_client):
    client, _ = make_client()
    response = client.post("/review", json={"link": LINK, "rubric_id": "нет"})
    assert response.status_code == 404
    assert "go-task1" in response.json()["detail"]


def test_gate_facts_reach_the_model(make_client):
    client, provider = make_client()
    client.post(
        "/review",
        json={"link": LINK, "rubric_id": "go-task1",
              "gate_facts": ["Тест-кейсов: ожидалось 21, фактически 18."]},
    )
    assert "фактически 18" in provider.last_prompt


def test_partial_files_are_visible_in_the_response(make_client):
    """Ревьюер должен видеть, по каким файлам вывод модели заведомо неполон."""
    bundle = go_bundle(artifacts=[
        artifact("cmd/main.go", text=GO_MAIN),
        partial_artifact("internal/store/pg.go"),
    ])
    client, _ = make_client(ingest=StubIngest(bundle))
    body = client.post("/review", json={"link": LINK, "rubric_id": "go-task1"}).json()

    partial = [f for f in body["files"] if f["partial"]]
    assert [f["path"] for f in partial] == ["internal/store/pg.go"]
    assert body["draft"]["partial_artifacts"] == ["internal/store/pg.go"]


# --------------------------------------------------------------------------- #
# with_detection — один ingest на review и детектор
# --------------------------------------------------------------------------- #

def test_with_detection_runs_the_detector_off_the_same_ingest(make_client):
    ingest = StubIngest()
    client, _ = make_client(ingest=ingest, responses=[VERDICTS, '{"findings": []}'])
    body = client.post(
        "/review", json={"link": LINK, "rubric_id": "go-task1", "with_detection": True}
    ).json()

    assert body["detection"] is not None
    assert body["detection"]["advisory"] is True
    assert ingest.calls == 1, "второй поход к источнику сдачи не нужен — bundle уже есть"


def test_with_detection_false_by_default_leaves_detection_empty(make_client):
    client, _ = make_client()
    body = client.post("/review", json={"link": LINK, "rubric_id": "go-task1"}).json()
    assert body["detection"] is None


def test_a_failing_detector_does_not_lose_the_review_draft(make_client):
    """Advisory-сигнал необязателен: его отказ не должен стоить уже посчитанного черновика."""
    client, _ = make_client()

    def _raise(*args, **kwargs):
        raise RuntimeError("детектор упал")

    client.app.state.ai.detect = _raise

    response = client.post(
        "/review", json={"link": LINK, "rubric_id": "go-task1", "with_detection": True}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["draft"]["score"] > 0
    assert body["detection"] is None


# --------------------------------------------------------------------------- #
# детектор
# --------------------------------------------------------------------------- #

def test_detect_returns_an_advisory_report(make_client):
    client, _ = make_client(responses=['{"findings": []}'])
    body = client.post("/detect", json={"link": LINK}).json()

    assert body["report"]["advisory"] is True
    assert body["report"]["limitations"]
    assert "не влияет на балл" in body["report"]["advisory_note"]


def test_detect_spans_are_addressable(make_client):
    """Ревьюер подтверждает или отклоняет конкретный спан — ему нужен идентификатор."""
    bundle = go_bundle(artifacts=[artifact("internal/service/order.go", text="x\n" * 900)])
    client, _ = make_client(ingest=StubIngest(bundle), responses=['{"findings": []}'])
    body = client.post("/detect", json={"link": LINK}).json()

    for span in body["report"]["spans"]:
        assert span["id"] and span["reviewer_verdict"] == "pending"


# --------------------------------------------------------------------------- #
# ошибки источника
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "error,status",
    [(InvalidLinkError("не ссылка на PR"), 422), (ProviderFetchError("502 от GitHub"), 502)],
)
def test_ingest_failures_are_translated(make_client, error, status):
    client, _ = make_client(ingest=StubIngest(error=error))
    assert client.post("/review", json={"link": LINK, "rubric_id": "go-task1"}).status_code == status
    assert client.post("/detect", json={"link": LINK}).status_code == status


def test_a_missing_rubric_costs_no_ingest_call(make_client):
    """Незачем ходить в GitHub за работой, которую не с чем сверять."""
    ingest = StubIngest()
    client, _ = make_client(ingest=ingest)
    client.post("/review", json={"link": LINK, "rubric_id": "нет"})
    assert ingest.calls == 0


# --------------------------------------------------------------------------- #
# служебное
# --------------------------------------------------------------------------- #

def test_the_app_produces_a_draft_on_its_default_config():
    """Без ключей приложение обязано проходить весь путь, а не только стартовать.

    Здесь намеренно не подменяется шлюз: собранный из конфига, он ходит к
    провайдеру `fake`. Тот отвечает не по схеме, поэтому батчи не разбираются —
    и это правильный исход: черновик приходит с явной пометкой «оценить
    вручную», а обращения попадают в журнал стоимости.
    """
    app = create_app()
    with TestClient(app) as client:
        app.state.ingest = StubIngest()
        as_role(client, "admin")
        body = client.post("/review", json={"link": LINK, "rubric_id": "go-task1"}).json()
        cost = client.get("/cost").json()

    draft = body["draft"]
    assert draft["failed_criteria"], "провайдер ответил не по схеме — это должно быть видно"
    assert all(v["needs_human_attention"] for v in draft["verdicts"])
    assert cost["calls"] > 0, "обращения к модели обязаны попадать в журнал"


def test_init_reports_the_model_route_and_rubrics(make_client):
    client, _ = make_client()
    body = client.get("/init").json()
    assert body["llm_provider"] == "fake"
    assert "go-task1" in body["rubrics"]


def test_cost_accumulates_across_runs(make_client):
    """Журнал общий на приложение: счёт за поток работ складывается из прогонов."""
    client, _ = make_client(responses=[VERDICTS] * 4)
    client.post("/review", json={"link": LINK, "rubric_id": "go-task1"})
    after_first = client.get("/cost").json()
    client.post("/review", json={"link": LINK, "rubric_id": "go-task1"})
    after_second = client.get("/cost").json()

    assert after_first["calls"] > 0
    assert after_second["calls"] == after_first["calls"] * 2
    assert after_second["cost_rub"] > after_first["cost_rub"]


# --------------------------------------------------------------------------- #
# Format Gate в конвейере
# --------------------------------------------------------------------------- #

def test_blocked_submission_never_reaches_the_model(make_client):
    """Работа, не принимаемая по формату, не должна стоить ни рубля токенов."""
    bundle = go_bundle(artifacts=[artifact("cmd/main.go", text="package main\nfunc main() {}\n")])
    client, provider = make_client(ingest=StubIngest(bundle))

    body = client.post(
        "/review", json={"link": "https://x/pull/1", "rubric_id": "go-task1"}
    ).json()

    assert body["draft"]["gate"]["status"] == "blocked"
    assert provider.calls == []
    assert body["draft"]["cost_rub"] == 0
    assert body["draft"]["needs_human_attention"] is True


def test_gate_facts_are_returned_with_the_draft(make_client):
    client, _ = make_client()
    body = client.post(
        "/review", json={"link": "https://x/pull/1", "rubric_id": "go-task1"}
    ).json()

    gate = body["draft"]["gate"]
    assert gate["status"] in ("passed", "warning")
    assert any("Shutting down service-courier" in fact for fact in body["draft"]["gate_facts"])
    # Каждая проверка приходит с местом, чтобы ревьюер мог кликнуть.
    found = [o for o in gate["outcomes"] if o["passed"] and o["locations"]]
    assert found and ":" in found[0]["locations"][0]


# --------------------------------------------------------------------------- #
# распределение
# --------------------------------------------------------------------------- #

WORK = {"item_id": "s1", "est_review_minutes": 40, "course_id": "go"}


def test_distribute_needs_no_model(make_client):
    """Раскладка не должна стоить ни одного токена: к модели она не ходит вовсе."""
    client, provider = make_client(responses=[])
    response = client.post("/distribute", json={"items": [WORK]})

    assert response.status_code == 200
    assert provider.calls == []
    assert response.json()["allocations"]


def test_distribute_uses_the_catalogue_when_no_pool_is_given(make_client):
    client, _ = make_client(responses=[])
    plan = client.post("/distribute", json={"items": [WORK]}).json()

    assert plan["reviewers"] == len(client.app.state.reviewers.ids)
    assert plan["allocations"][0]["reviewer_id"].startswith("c-")
    assert plan["allocations"][0]["explain"]


def test_distribute_rejects_an_unknown_reviewer_id(make_client):
    client, _ = make_client(responses=[])
    response = client.post(
        "/distribute", json={"items": [WORK], "reviewer_ids": ["c-kruglov", "нет-такого"]}
    )

    assert response.status_code == 422
    assert "нет-такого" in response.json()["detail"]


def test_distribute_with_nobody_to_distribute_to_is_404(make_client):
    client, _ = make_client(responses=[], reviewers=False)
    response = client.post("/distribute", json={"items": [WORK]})

    assert response.status_code == 404
    assert "каталог ревьюеров пуст" in response.json()["detail"]


def test_an_exhausted_pool_is_a_200_with_reasons(make_client):
    """Исчерпание ёмкости — результат, а не ошибка: координатору нужен список причин."""
    client, _ = make_client(responses=[])
    plan = client.post(
        "/distribute",
        json={
            "items": [WORK],
            "reviewer_ids": ["c-kruglov"],
            "committed_minutes": {"c-kruglov": 600},
        },
    ).json()

    assert plan["allocations"] == []
    assert plan["unassigned"][0]["reason"] == "capacity"
    assert plan["unassigned"][0]["blocked_by"][0]["reviewer_id"] == "c-kruglov"


def test_a_work_without_a_duration_is_refused_at_the_edge(make_client):
    client, _ = make_client(responses=[])
    response = client.post("/distribute", json={"items": [{"item_id": "s1"}]})

    assert response.status_code == 422


def test_init_lists_the_reviewer_catalogue(make_client):
    client, _ = make_client()
    assert "c-kruglov" in client.get("/init").json()["reviewers"]


def test_work_profile_returns_an_item_ready_to_distribute(make_client):
    """Улики соавторства собирает бэкенд: клиент не должен воспроизводить author_hash."""
    client, _ = make_client(responses=[PROFILE])
    body = client.post("/work-profile", json={"link": LINK, "rubric_id": "go-task1"}).json()

    assert body["profile"]["est_review_minutes"] == 25
    assert body["item"]["author_hashes"] == ["author1"]
    assert body["item"]["assignment_id"] == "go-task1"


def test_a_profile_and_a_plan_are_one_road(make_client):
    """Профиль обязан приниматься распределением как есть, без правки руками."""
    client, _ = make_client(responses=[PROFILE])
    item = client.post("/work-profile", json={"link": LINK}).json()["item"]

    plan = client.post("/distribute", json={"items": [item]}).json()

    assert len(plan["allocations"]) == 1
    assert plan["allocations"][0]["est_review_minutes"] == 25


def test_work_profile_upstream_failure_is_502(make_client):
    client, _ = make_client(responses=["не json", "снова не json", "и ещё"])
    assert client.post("/work-profile", json={"link": LINK}).status_code == 502


def test_work_profile_translates_a_bad_link(make_client):
    client, _ = make_client(
        ingest=StubIngest(error=InvalidLinkError("не ссылка на PR")), responses=[PROFILE]
    )
    assert client.post("/work-profile", json={"link": LINK}).status_code == 422


# --------------------------------------------------------------------------- #
# Rubric Compiler
# --------------------------------------------------------------------------- #

CONDITION = """# Лаба 1

Максимальный балл — 6, зачёт с 4.

## Что нужно сделать

Выполнить декомпозицию системы по двум и более признакам.
"""

COMPILED = json.dumps(
    {
        "title": "Лаба 1",
        "total_max": 6,
        "pass_threshold": 4,
        "criteria": [
            {"id": "c1", "title": "Декомпозиция", "max_score": 6,
             "source_quote": "Выполнить декомпозицию системы по двум и более признакам."}
        ],
        "open_questions": [],
    },
    ensure_ascii=False,
)


def test_compile_returns_a_draft_not_a_saved_rubric(make_client):
    """Черновик подтверждает методист: в каталог он попасть не должен."""
    client, _ = make_client(responses=[COMPILED])
    body = client.post(
        "/rubrics/compile",
        json={"assignment_id": "lab1", "condition_text": CONDITION},
    ).json()

    assert body["grounded_share"] == 1.0
    assert body["draft"]["rubric"]["criteria"][0]["title"] == "Декомпозиция"
    assert "подтверждению методистом" in body["draft"]["rubric"]["source_note"]
    # В каталоге его нет: сохранение — отдельное решение человека.
    assert "lab1" not in client.get("/rubrics").json()[0]["assignment_id"]


def test_compile_exposes_criteria_the_condition_does_not_support(make_client):
    """Придуманный критерий — главная опасность шага, и он обязан быть виден."""
    invented = json.dumps(
        {
            "total_max": 6, "pass_threshold": 4,
            "criteria": [{"id": "c1", "title": "Покрытие тестами 80%", "max_score": 6,
                          "source_quote": "Покрытие тестами должно быть не ниже 80 процентов."}],
        },
        ensure_ascii=False,
    )
    client, _ = make_client(responses=[invented])
    body = client.post(
        "/rubrics/compile",
        json={"assignment_id": "lab1", "condition_text": CONDITION},
    ).json()

    assert body["grounded_share"] == 0.0
    assert body["draft"]["sources"][0]["status"] == "paraphrased"


def test_compile_rejects_a_condition_too_short_to_be_one(make_client):
    client, _ = make_client()
    response = client.post(
        "/rubrics/compile", json={"assignment_id": "lab1", "condition_text": "короче некуда"}
    )
    assert response.status_code == 422


def test_model_failure_on_compile_is_502(make_client):
    client, _ = make_client(responses=["не json", "снова не json", "и ещё раз"])
    response = client.post(
        "/rubrics/compile", json={"assignment_id": "lab1", "condition_text": CONDITION}
    )
    assert response.status_code == 502


# --------------------------------------------------------------------------- #
# подтверждение рубрики
# --------------------------------------------------------------------------- #

CONFIRMED = {
    "assignment_id": "lab1",
    "title": "Лаба 1",
    "scale": {"total_max": 4, "pass_threshold": 3, "step": 0.5},
    "criteria": [
        {"id": "c1", "title": "Раз", "max_score": 2},
        {"id": "c2", "title": "Два", "max_score": 2},
    ],
}


def test_confirmed_rubric_becomes_available_for_review(make_client):
    """Смысл шага: с этого момента по рубрике можно проверять работы."""
    client, _ = make_client(writable=True)
    response = client.post(
        "/rubrics", json={"rubric": CONFIRMED, "confirmed_by": "Ирина Ходасевич"}
    )

    assert response.status_code == 200
    assert "Ирина Ходасевич" in response.json()["rubric"]["source_note"]
    assert client.get("/rubrics/lab1").status_code == 200
    assert any(r["assignment_id"] == "lab1" for r in client.get("/rubrics").json())


def test_rubric_that_does_not_add_up_is_refused_with_reasons(make_client):
    """Рубрика действует до конца курса: ошибка в ней стоит дороже любого черновика."""
    client, _ = make_client(writable=True)
    broken = {**CONFIRMED, "scale": {"total_max": 4, "pass_threshold": 99}}
    response = client.post("/rubrics", json={"rubric": broken, "confirmed_by": "методист"})

    assert response.status_code == 422
    assert any("зачёт недостижим" in p for p in response.json()["detail"])
    assert client.get("/rubrics/lab1").status_code == 404


def test_existing_rubric_needs_an_explicit_overwrite(make_client):
    client, _ = make_client(writable=True)
    client.post("/rubrics", json={"rubric": CONFIRMED, "confirmed_by": "методист"})

    again = client.post("/rubrics", json={"rubric": CONFIRMED, "confirmed_by": "методист"})
    assert again.status_code == 409

    forced = client.post(
        "/rubrics",
        json={"rubric": {**CONFIRMED, "title": "Правленая"}, "confirmed_by": "методист",
              "overwrite": True},
    )
    assert forced.status_code == 200
    assert client.get("/rubrics/lab1").json()["title"] == "Правленая"


def test_compile_then_confirm_is_one_road(make_client):
    """Черновик компилятора должен приниматься ручкой подтверждения как есть."""
    client, _ = make_client(responses=[COMPILED], writable=True)
    draft = client.post(
        "/rubrics/compile", json={"assignment_id": "lab1", "condition_text": CONDITION}
    ).json()["draft"]

    confirmed = client.post(
        "/rubrics", json={"rubric": draft["rubric"], "confirmed_by": "методист"}
    )
    assert confirmed.status_code == 200
    note = confirmed.json()["rubric"]["source_note"]
    assert "Подтверждено: методист" in note
    # Метка черновика снята: рубрика не может ждать подтверждения и быть подтверждённой.
    assert "Подлежит подтверждению" not in note


# --------------------------------------------------------------------------- #
# удаление рубрики
# --------------------------------------------------------------------------- #

def test_delete_rubric_requires_admin(make_client):
    client, _ = make_client(writable=True, role="reviewer")
    assert client.delete("/rubrics/go-task1").status_code == 403


def test_delete_removes_it_from_the_catalogue(make_client):
    client, _ = make_client(writable=True)
    client.post("/rubrics", json={"rubric": CONFIRMED, "confirmed_by": "методист"})
    assert client.get("/rubrics/lab1").status_code == 200

    assert client.delete("/rubrics/lab1").status_code == 204
    assert client.get("/rubrics/lab1").status_code == 404


def test_delete_unknown_rubric_is_404(make_client):
    client, _ = make_client(writable=True)
    assert client.delete("/rubrics/нет-такой").status_code == 404
