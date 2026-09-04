"""Детектор признаков ГенИИ.

Вывод рекомендательный, и половина ценности здесь — в том, чего детектор НЕ
утверждает: молчащий сигнал не читается как «чисто», неполный файл не идёт в
статистику, находка без подтверждённой цитаты не показывается вовсе.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from factories import (
    NOW,
    artifact,
    go_bundle,
    partial_artifact,
    revision,
    texts_of,
)

from avito_reviewer.ai.content import from_artifact
from avito_reviewer.ai.detection import (
    DetectionService,
    SignalKind,
    SignalStatus,
    merge_spans,
)
from avito_reviewer.ai.detection.ensemble import combine
from avito_reviewer.ai.detection.schema import SignalResult, Span
from avito_reviewer.ai.detection.signals import forensics, judge, stylometry
from avito_reviewer.ai.llm import LLMUnavailable, fake_gateway
from avito_reviewer.config import DetectionOptions
from avito_reviewer.ingest import ArtifactRole, ChangeStatus


def text_of(path: str, body: str, **kwargs):
    result = from_artifact(artifact(path, text=body, **kwargs))
    assert result is not None
    return result


# --------------------------------------------------------------------------- #
# форензика
# --------------------------------------------------------------------------- #

def test_bulk_paste_is_detected():
    bundle = go_bundle(revisions=[
        revision(minutes_ago=125, added=12),
        revision(minutes_ago=122, added=640),
        revision(minutes_ago=5, added=30),
    ])
    result = forensics.analyse(bundle)
    assert result.score >= 0.6
    assert any("640 строк" in f for f in result.findings)


def test_spans_admit_the_link_to_a_commit_is_indirect():
    """История не хранит списка файлов; притворяться, что мы нашли строку, нельзя."""
    bundle = go_bundle(
        artifacts=[artifact("internal/service/order.go", text="x\n" * 900)],
        revisions=[revision(minutes_ago=125, added=12), revision(minutes_ago=122, added=640)],
    )
    span = forensics.analyse(bundle).spans[0]
    assert span.artifact == "internal/service/order.go"
    assert span.start_line is None
    assert "косвенная" in span.reason


def test_single_commit_is_suspicious():
    result = forensics.analyse(go_bundle(revisions=[revision(minutes_ago=5, added=900)]))
    assert result.score >= 0.75
    assert "одного коммита" in result.findings[0]


def test_normal_history_is_clean():
    """Обычная работа с растущей историей не должна подсвечиваться."""
    bundle = go_bundle(revisions=[
        revision(minutes_ago=(8 - i) * 300 + i * 7, added=30 + i * 9) for i in range(8)
    ])
    assert forensics.analyse(bundle).score < 0.3


def test_daily_routine_is_not_suspicious():
    """Студент, который коммитит каждый вечер, — это распорядок дня, а не признак."""
    bundle = go_bundle(revisions=[
        revision(minutes_ago=(7 - i) * 1440, added=40) for i in range(7)
    ])
    assert forensics.analyse(bundle).score < 0.3


def test_missing_history_is_unavailable_not_clean():
    """Отсутствие сигнала и отсутствие признаков — разные вещи."""
    result = forensics.analyse(go_bundle(revisions=[]))
    assert result.status is SignalStatus.UNAVAILABLE
    assert result.score == 0.0
    assert "недоступна" in result.note


# --------------------------------------------------------------------------- #
# стилометрия
# --------------------------------------------------------------------------- #

CLICHE_TEXT = (
    "Важно отметить, что данный подход имеет ряд преимуществ. "
    "В современном мире архитектура играет важную роль. "
    "Таким образом, следует учитывать все аспекты проектирования. "
    "Стоит подчеркнуть, что комплексный подход обеспечивает надёжность системы. "
) * 3


def test_cliches_are_detected():
    result = stylometry.analyse([text_of("doc.md", CLICHE_TEXT, lang="markdown")])
    assert result.score >= 0.4
    assert any("обороты" in f for f in result.findings)


def test_normal_prose_is_clean():
    text = (
        "Взял сервис доставки. Разбил на три компонента: приём заказа, "
        "подбор курьера, трекинг.\n\n"
        "Почему так. Приём заказа меняется чаще всего — там маркетинг постоянно "
        "что-то крутит, и я не хочу, чтобы каждый эксперимент задевал трекинг. "
        "Подбор курьера наоборот стабильный, но требователен к latency.\n\n"
        "Контракты между ними — gRPC. Событий не хотел: сложнее отлаживать, "
        "а нагрузки тут нет.\n\n"
        "Слабое место — общая база на приём и трекинг. Знаю, что так себе, "
        "но разносить не стал: не успел бы к дедлайну.\n"
    )
    assert stylometry.analyse([text_of("doc.md", text, lang="markdown")]).score < 0.4


def test_short_text_is_skipped():
    assert stylometry.analyse([text_of("a.md", "Коротко.", lang="markdown")]).score < 0.1


def test_over_commented_code_is_flagged():
    lines = []
    for i in range(60):
        lines.append(f"// Эта функция выполняет операцию номер {i}")
        lines.append(f"func step{i}() {{ return }}")
    assert stylometry.analyse([text_of("a.go", "\n".join(lines))]).score >= 0.4


def test_fragments_are_skipped_not_scored():
    """По обрывкам строк статистика даёт и ложную ровность, и ложную рваность."""
    result = stylometry.analyse([from_artifact(partial_artifact("pg.go"))])
    assert result.status is SignalStatus.UNAVAILABLE
    assert "фрагментом" in result.note


# --------------------------------------------------------------------------- #
# LLM-judge
# --------------------------------------------------------------------------- #

DOC = (
    "# Карта рисков\n\n"
    "Важно отметить, что риски мошенничества требуют комплексного подхода "
    "и системного анализа на каждом этапе пользовательского пути.\n\n"
    "Далее приведён список этапов CJM.\n"
)


def _judge_response(quote: str, score: float = 0.8, artifact_path: str = "doc.md") -> str:
    return json.dumps(
        {"findings": [{"artifact": artifact_path, "quote": quote, "score": score,
                       "reason": "клишированный оборот и избыточная пояснительность"}]},
        ensure_ascii=False,
    )


def test_judge_maps_quote_to_offsets():
    quote = "Важно отметить, что риски мошенничества требуют комплексного подхода"
    gateway, _ = fake_gateway([_judge_response(quote)])
    result = judge.analyse(gateway, [text_of("doc.md", DOC, lang="markdown")])

    assert result.score == 0.8
    span = result.spans[0]
    assert DOC[span.start : span.end] == quote
    assert span.start_line == 3


def test_judge_matches_quote_across_line_breaks():
    """Модель переносит строки иначе, чем файл, — цитата всё равно должна найтись."""
    quote = "риски мошенничества требуют комплексного подхода и системного анализа"
    gateway, _ = fake_gateway([_judge_response(quote)])
    result = judge.analyse(gateway, [text_of("doc.md", DOC, lang="markdown")])
    assert result.spans and result.spans[0].start is not None


def test_judge_discards_findings_without_a_real_quote():
    """Без подтверждённой цитаты показывать ревьюеру нечего."""
    gateway, _ = fake_gateway([
        _judge_response("этого текста в работе нет и никогда не было, выдумка целиком")
    ])
    result = judge.analyse(gateway, [text_of("doc.md", DOC, lang="markdown")])
    assert result.spans == []
    assert result.score < 0.1


def test_judge_ignores_too_short_quotes():
    gateway, _ = fake_gateway([_judge_response("Важно отметить")])
    assert judge.analyse(gateway, [text_of("doc.md", DOC, lang="markdown")]).spans == []


def test_judge_reads_fragments_but_says_so():
    """Находка judge — утверждение о показанном тексте, и его можно сверить."""
    fragment = from_artifact(partial_artifact("pg.go"))
    quote = "rows, err := s.db.Query(ctx, q)\n\tif err != nil {"
    gateway, provider = fake_gateway([_judge_response(quote, artifact_path="pg.go")])
    result = judge.analyse(gateway, [fragment])

    assert "ФРАГМЕНТ" in provider.last_prompt
    assert result.spans[0].start_line == 41  # номер строки в файле, не в куске
    assert result.spans[0].start is None     # смещений в символах у фрагмента нет


def test_template_files_are_excluded():
    """Без allowlist детектор уверенно ловит go.sum, то есть самого себя."""
    artifacts = [
        text_of("go.sum", "module x\n" * 200),
        text_of("migrations/001_init.sql", "CREATE TABLE x();\n" * 50, lang="sql"),
    ]
    result = judge.analyse(fake_gateway()[0], artifacts)
    assert result.status is SignalStatus.UNAVAILABLE
    assert judge.is_template("go.sum") and judge.is_template("api/x.pb.go")


def test_judge_failure_does_not_break_the_pipeline():
    gateway, _ = fake_gateway([LLMUnavailable("нет сети")] * 3)
    result = judge.analyse(gateway, [text_of("doc.md", DOC, lang="markdown")])
    assert result.status is SignalStatus.FAILED
    assert result.score == 0.0


# --------------------------------------------------------------------------- #
# ансамбль
# --------------------------------------------------------------------------- #

def test_weights_are_renormalised_when_a_signal_is_missing():
    """Молчащий сигнал не должен читаться как «признаков нет»."""
    report = combine([
        SignalResult(kind=SignalKind.FORENSICS, status=SignalStatus.UNAVAILABLE,
                     weight=0.35, note="нет истории"),
        SignalResult(kind=SignalKind.STYLOMETRY, score=0.8, weight=0.15),
        SignalResult(kind=SignalKind.JUDGE, score=0.8, weight=0.25),
    ])
    assert report.overall_score == pytest.approx(0.8, abs=0.01)
    assert any("форензика" in limit for limit in report.limitations)


def test_disagreement_widens_the_interval():
    agree = combine([
        SignalResult(kind=SignalKind.FORENSICS, score=0.7, weight=0.35),
        SignalResult(kind=SignalKind.JUDGE, score=0.7, weight=0.25),
    ])
    disagree = combine([
        SignalResult(kind=SignalKind.FORENSICS, score=1.0, weight=0.35),
        SignalResult(kind=SignalKind.JUDGE, score=0.2, weight=0.25),
    ])
    assert (agree.confidence_high - agree.confidence_low) < (
        disagree.confidence_high - disagree.confidence_low
    )


def test_no_signals_means_no_verdict():
    report = combine([
        SignalResult(kind=SignalKind.FORENSICS, status=SignalStatus.UNAVAILABLE, weight=0.35),
        SignalResult(kind=SignalKind.JUDGE, status=SignalStatus.FAILED, weight=0.25),
    ])
    assert report.label == "недостаточно данных"
    assert report.overall_score == 0.0


def test_overlapping_spans_merge_with_both_reasons():
    merged = merge_spans([
        Span(artifact="a.go", start=0, end=100, score=0.6,
             signals=[SignalKind.PERPLEXITY], reason="ровная перплексия"),
        Span(artifact="a.go", start=50, end=180, score=0.7,
             signals=[SignalKind.JUDGE], reason="клише"),
    ])
    assert len(merged) == 1
    assert set(merged[0].signals) == {SignalKind.PERPLEXITY, SignalKind.JUDGE}
    assert merged[0].score > 0.7  # совпадение двух сигналов усиливает вывод
    assert "ровная перплексия" in merged[0].reason and "клише" in merged[0].reason


def test_distant_spans_do_not_merge():
    assert len(merge_spans([
        Span(artifact="a.go", start=0, end=50, score=0.6, signals=[SignalKind.JUDGE]),
        Span(artifact="a.go", start=500, end=600, score=0.6, signals=[SignalKind.JUDGE]),
    ])) == 2


def test_located_finding_keeps_its_lines_next_to_a_whole_file_span():
    """У находки в файле-фрагменте нет смещений — только строки.

    Слияние по смещениям утаскивало такую находку в «спан на весь файл», и
    ревьюер терял место, где что-то нашли.
    """
    merged = merge_spans(
        [
            Span(artifact="pg.go", score=0.6, signals=[SignalKind.FORENSICS], reason="коммит"),
            Span(
                artifact="pg.go",
                start_line=44,
                end_line=58,
                score=0.7,
                signals=[SignalKind.JUDGE],
                reason="клише",
            ),
        ]
    )
    located = [span for span in merged if span.start_line is not None]

    assert len(merged) == 2
    assert (located[0].start_line, located[0].end_line) == (44, 58)


def test_overlapping_line_spans_merge_without_offsets():
    merged = merge_spans(
        [
            Span(
                artifact="pg.go", start_line=40, end_line=50, score=0.6, signals=[SignalKind.JUDGE]
            ),
            Span(
                artifact="pg.go",
                start_line=45,
                end_line=60,
                score=0.7,
                signals=[SignalKind.PERPLEXITY],
            ),
        ]
    )
    assert len(merged) == 1
    assert (merged[0].start_line, merged[0].end_line) == (40, 60)


def test_span_has_a_stable_id_for_the_reviewer_verdict():
    span = Span(artifact="a.go", start_line=4, end_line=9, score=0.5, signals=[SignalKind.JUDGE])
    twin = Span(artifact="a.go", start_line=4, end_line=9, score=0.9, signals=[SignalKind.FORENSICS])
    assert span.id == twin.id
    assert span.model_dump()["id"] == span.id


def test_ai_sensitive_spans_come_first():
    report = combine(
        [SignalResult(kind=SignalKind.JUDGE, score=0.6, weight=0.25, spans=[
            Span(artifact="docker-compose.yml", start=0, end=10, score=0.9,
                 signals=[SignalKind.JUDGE]),
            Span(artifact="risks.md", start=0, end=10, score=0.5, signals=[SignalKind.JUDGE]),
        ])],
        ai_sensitive_paths={"risks.md"},
    )
    assert report.spans[0].artifact == "risks.md"
    assert report.spans[0].ai_sensitive is True


# --------------------------------------------------------------------------- #
# сервис целиком
# --------------------------------------------------------------------------- #

QUOTE = "Важно отметить, что риски мошенничества требуют комплексного подхода"


def _bundle(**kwargs):
    defaults = dict(
        artifacts=[artifact("doc.md", text=DOC, lang="markdown")],
        revisions=[revision(minutes_ago=10, added=8), revision(minutes_ago=8, added=700)],
    )
    defaults.update(kwargs)
    return go_bundle(**defaults)


def _analyse(bundle, gateway=None, options=None):
    return DetectionService(gateway, options).analyse(bundle, texts_of(bundle))


def test_report_is_advisory_and_carries_limitations():
    gateway, _ = fake_gateway([_judge_response(QUOTE)])
    report = _analyse(_bundle(), gateway)

    assert report.advisory is True
    assert "не влияет на балл автоматически" in report.advisory_note
    assert report.limitations
    assert 0.0 <= report.confidence_low <= report.overall_score <= report.confidence_high <= 1.0


def test_missing_declaration_with_signals_is_the_headline():
    """По условию запрещено не использование ИИ, а несогласованное использование."""
    gateway, _ = fake_gateway([_judge_response(QUOTE)])
    report = _analyse(_bundle(), gateway)

    assert report.declared_ai_usage is False
    assert report.mismatch is True
    assert "расхождение" in report.declaration_note


def test_declaration_is_found_and_quoted():
    declared = DOC + "\n\nПри подготовке работы я использовал ChatGPT для проверки формулировок.\n"
    bundle = _bundle(
        artifacts=[artifact("doc.md", text=declared, lang="markdown")],
        revisions=[revision(minutes_ago=10, added=10)],
    )
    gateway, _ = fake_gateway(['{"findings": []}'])
    report = _analyse(bundle, gateway)

    assert report.declared_ai_usage is True
    assert "ChatGPT" in report.declaration_note
    assert report.mismatch is False


def test_perplexity_absence_is_reported_not_hidden():
    gateway, _ = fake_gateway(['{"findings": []}'])
    report = _analyse(_bundle(), gateway)
    assert report.signal(SignalKind.PERPLEXITY).status is SignalStatus.UNAVAILABLE
    assert any("ерплексия" in limit for limit in report.limitations)


def test_partial_files_are_named_as_a_limitation():
    gateway, _ = fake_gateway(['{"findings": []}'])
    bundle = _bundle(artifacts=[
        artifact("doc.md", text=DOC, lang="markdown"),
        partial_artifact("internal/store/pg.go"),
    ])
    report = _analyse(bundle, gateway)
    assert any("Доступны только фрагментами" in limit for limit in report.limitations)


def test_tooling_is_excluded_from_the_detector_too():
    """Сгенерированный docker-compose ничего не говорит о самостоятельности студента."""
    gateway, _ = fake_gateway([_judge_response(QUOTE, artifact_path="ops/deploy.md")])
    bundle = _bundle(artifacts=[
        artifact("ops/deploy.md", text=DOC, lang="markdown", role=ArtifactRole.TOOLING)
    ])
    report = _analyse(bundle, gateway)
    assert report.spans == []


def test_detection_works_without_a_gateway_at_all():
    """Форензика и стилометрия не нуждаются в модели — детектор обязан работать без неё."""
    report = _analyse(_bundle(), None, DetectionOptions(use_judge=False))
    assert report.overall_score > 0.3
    assert report.signal(SignalKind.FORENSICS).status is SignalStatus.OK


def test_cost_of_the_run_is_reported():
    gateway, _ = fake_gateway([_judge_response(QUOTE)])
    report = _analyse(_bundle(), gateway)
    assert report.tokens_in > 0 and report.cost_rub > 0
