"""Классификатор артефактов: что работа студента, а что выхлоп инструмента.

Цена ошибки несимметрична. Пропустить шум в ревью — потраченные токены;
записать сгенерированный `docker-compose` в работу студента — обвинение в
использовании ГенИИ, выставленное коду, который студент не писал.
"""

from __future__ import annotations

import pytest
from factories import artifact, atext, go_bundle

from avito_reviewer.ai.content import gradable_texts, solution_texts
from avito_reviewer.ai.detection.signals.judge import is_template
from avito_reviewer.ingest import ArtifactRole
from avito_reviewer.ingest.classify import classify


@pytest.mark.parametrize(
    "path,role",
    [
        ("internal/handler/order.go", ArtifactRole.SOLUTION),
        ("README.md", ArtifactRole.SOLUTION),
        ("notebooks/train.ipynb", ArtifactRole.SOLUTION),
        # §5.5: 314 файлов трекинга MLflow в «хорошем решении» курса LLM.
        ("mlruns/0/meta.yaml", ArtifactRole.NOISE),
        ("mlruns/0/abc/artifacts/model/MLmodel", ArtifactRole.NOISE),
        ("node_modules/react/index.js", ArtifactRole.NOISE),
        ("go.sum", ArtifactRole.NOISE),
        ("uv.lock", ArtifactRole.NOISE),
        ("src/__pycache__/app.cpython-311.pyc", ArtifactRole.NOISE),
        ("Dockerfile", ArtifactRole.TOOLING),
        ("docker-compose.yml", ArtifactRole.TOOLING),
        ("go.mod", ArtifactRole.TOOLING),
        (".github/workflows/ci.yml", ArtifactRole.TOOLING),
        ("migrations/001_init.sql", ArtifactRole.TOOLING),
        ("api/order.pb.go", ArtifactRole.TOOLING),
        ("api/order_pb2_grpc.py", ArtifactRole.TOOLING),
        ("docs/scheme.png", ArtifactRole.EVIDENCE),
        ("evidence/loss.svg", ArtifactRole.EVIDENCE),
    ],
)
def test_paths_get_their_class(path: str, role: ArtifactRole):
    assert classify(path) is role


def test_a_diagram_is_evidence_not_noise():
    """Работа с приложенным графиком отличается от работы без него.

    Прочесть картинку нечем, но её наличие — факт, и ревьюер должен его видеть,
    поэтому она не выбрасывается вместе с мусором.
    """
    assert classify("docs/c4-context.png") is ArtifactRole.EVIDENCE


def test_go_mod_is_tooling_but_go_sum_is_noise():
    """`go.mod` студент правит руками, `go.sum` дописывает тулчейн."""
    assert classify("go.mod") is ArtifactRole.TOOLING
    assert classify("go.sum") is ArtifactRole.NOISE


# --------------------------------------------------------------------------- #
# следствия для слоёв ниже
# --------------------------------------------------------------------------- #

def test_tooling_is_kept_out_of_the_detector():
    """Сгенерированный фреймворком код ничего не говорит о самостоятельности.

    Без этого детектор ловит сам себя: `docker-compose` и `*.pb.go` написаны
    не человеком по определению.
    """
    texts = [
        atext("internal/service/order.go", text="package service\n"),
        atext("Dockerfile", text="FROM golang:1.22\n", lang=None),
    ]
    texts[1].role = ArtifactRole.TOOLING

    assert [t.path for t in solution_texts(texts)] == ["internal/service/order.go"]


def test_evidence_counts_for_review_but_not_for_the_detector():
    """Учитывается по факту наличия: в ревью идёт, в стилометрию — нет."""
    code = atext("main.go", text="package main\n")
    plot = atext("docs/loss.png", text="", lang=None)
    plot.role = ArtifactRole.EVIDENCE

    assert [t.path for t in gradable_texts([code, plot])] == ["main.go", "docs/loss.png"]
    assert [t.path for t in solution_texts([code, plot])] == ["main.go"]


def test_the_detector_and_the_classifier_agree_on_what_is_template():
    """Два списка «чья это работа» дали бы два разных ответа."""
    for path in ("go.sum", "api/order.pb.go", "migrations/001.sql", "Dockerfile"):
        assert is_template(path), path
    for path in ("internal/handler/order.go", "README.md"):
        assert not is_template(path), path


def test_a_bundle_carries_the_classes_the_layers_below_expect():
    bundle = go_bundle(artifacts=[
        artifact("cmd/main.go", text="package main\n"),
        artifact("Dockerfile", text="FROM golang\n", lang=None, role=classify("Dockerfile")),
        artifact("mlruns/0/meta.yaml", text="x\n", lang=None, role=classify("mlruns/0/meta.yaml")),
    ])
    roles = {a.path: a.role for a in bundle.artifacts}

    assert roles["cmd/main.go"] is ArtifactRole.SOLUTION
    assert roles["Dockerfile"] is ArtifactRole.TOOLING
    assert roles["mlruns/0/meta.yaml"] is ArtifactRole.NOISE
