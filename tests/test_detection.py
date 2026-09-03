"""Тесты детектора признаков ГенИИ."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from doubles import Artifact, Bundle, HistoryEvent
from detection_service import DetectionConfig, DetectionService, SignalKind, SignalStatus, merge_spans
from detection_service.ensemble import combine
from detection_service.schema import SignalResult, Span
from detection_service.signals import forensics, judge, stylometry
from llm import fake_gateway

BASE = datetime(2026, 2, 8, 2, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# форензика
# --------------------------------------------------------------------------- #

def test_bulk_paste_is_detected():
    bundle = Bundle(history=[
        HistoryEvent(at=BASE, added=12, touched_paths=["go.mod"]),
        HistoryEvent(at=BASE + timedelta(minutes=3), added=640,
                     touched_paths=["internal/service/order.go"]),
        HistoryEvent(at=BASE + timedelta(hours=2), added=30, touched_paths=["README.md"]),
    ])
    result = forensics.analyse(bundle)
    assert result.score >= 0.6
    assert any("640 строк" in f for f in result.findings)
    assert result.spans[0].artifact == "internal/service/order.go"


def test_single_commit_is_suspicious():
    bundle = Bundle(history=[HistoryEvent(at=BASE, added=900, touched_paths=["main.go"])])
    result = forensics.analyse(bundle)
    assert result.score >= 0.75
    assert "одного коммита" in result.findings[0]


def test_normal_history_is_clean():
    """Обычная работа с растущей историей не должна подсвечиваться."""
    bundle = Bundle(history=[
        HistoryEvent(at=BASE + timedelta(hours=i * 5 + i, minutes=i * 7), added=30 + i * 9,
                     touched_paths=[f"f{i}.go"])
        for i in range(8)
    ])
    result = forensics.analyse(bundle)
    assert result.score < 0.3


def test_daily_routine_is_not_suspicious():
    """Студент, который коммитит каждый вечер, — это распорядок дня, а не признак."""
    bundle = Bundle(history=[
        HistoryEvent(at=BASE + timedelta(days=i), added=40, touched_paths=[f"f{i}.go"])
        for i in range(7)
    ])
    assert forensics.analyse(bundle).score < 0.3


def test_missing_history_is_unavailable_not_clean():
    """Отсутствие сигнала и отсутствие признаков — разные вещи."""
    result = forensics.analyse(Bundle())
    assert result.status is SignalStatus.UNAVAILABLE
    assert result.score == 0.0
    assert "недоступна" in result.note


# --------------------------------------------------------------------------- #
# стилометрия
# --------------------------------------------------------------------------- #

def test_cliches_are_detected():
    text = (
        "Важно отметить, что данный подход имеет ряд преимуществ. "
        "В современном мире архитектура играет важную роль. "
        "Таким образом, следует учитывать все аспекты проектирования. "
        "Стоит подчеркнуть, что комплексный подход обеспечивает надёжность системы. "
    ) * 3
    result = stylometry.analyse([Artifact(path="doc.md", text=text)])
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
    assert stylometry.analyse([Artifact(path="doc.md", text=text)]).score < 0.4


def test_short_text_is_skipped():
    assert stylometry.analyse([Artifact(path="a.md", text="Коротко.")]).score < 0.1


def test_over_commented_code_is_flagged():
    lines = []
    for i in range(60):
        lines.append(f"// Эта функция выполняет операцию номер {i}")
        lines.append(f"func step{i}() {{ return }}")
    result = stylometry.analyse([Artifact(path="a.go", text="\n".join(lines))])
    assert result.score >= 0.4


# --------------------------------------------------------------------------- #
# LLM-judge
# --------------------------------------------------------------------------- #

DOC = (
    "# Карта рисков\n\n"
    "Важно отметить, что риски мошенничества требуют комплексного подхода "
    "и системного анализа на каждом этапе пользовательского пути.\n\n"
    "Далее приведён список этапов CJM.\n"
)


def _judge_response(quote: str, score: float = 0.8) -> str:
    return json.dumps(
        {"findings": [{"artifact": "doc.md", "quote": quote, "score": score,
                       "reason": "клишированный оборот и избыточная пояснительность"}]},
        ensure_ascii=False,
    )


def test_judge_maps_quote_to_offsets():
    quote = "Важно отметить, что риски мошенничества требуют комплексного подхода"
    gateway, _ = fake_gateway([_judge_response(quote)])
    result = judge.analyse(gateway, [Artifact(path="doc.md", text=DOC)])

    assert result.score == 0.8
    span = result.spans[0]
    assert DOC[span.start:span.end] == quote
    assert span.start_line == 3


def test_judge_matches_quote_across_line_breaks():
    """Модель переносит строки иначе, чем файл, — цитата всё равно должна найтись."""
    quote = "риски мошенничества требуют комплексного подхода и системного анализа"
    gateway, _ = fake_gateway([_judge_response(quote)])
    result = judge.analyse(gateway, [Artifact(path="doc.md", text=DOC)])
    assert result.spans and result.spans[0].start is not None


def test_judge_discards_findings_without_a_real_quote():
    """Без подтверждённой цитаты показывать ревьюеру нечего."""
    gateway, _ = fake_gateway([
        _judge_response("этого текста в работе нет и никогда не было, выдумка целиком")
    ])
    result = judge.analyse(gateway, [Artifact(path="doc.md", text=DOC)])
    assert result.spans == []
    assert result.score < 0.1


def test_judge_ignores_too_short_quotes():
    gateway, _ = fake_gateway([_judge_response("Важно отметить")])
    assert judge.analyse(gateway, [Artifact(path="doc.md", text=DOC)]).spans == []


def test_template_files_are_excluded():
    """Без allowlist детектор уверенно ловит go.sum, то есть самого себя."""
    artifacts = [
        Artifact(path="go.sum", text="module x\n" * 200),
        Artifact(path="migrations/001_init.sql", text="CREATE TABLE x();\n" * 50),
    ]
    result = judge.analyse(fake_gateway()[0], artifacts)
    assert result.status is SignalStatus.UNAVAILABLE
    assert judge.is_template("go.sum") and judge.is_template("api/x.pb.go")


def test_judge_failure_does_not_break_the_pipeline():
    from llm.providers import LLMUnavailable

    gateway, _ = fake_gateway([LLMUnavailable("нет сети")] * 3)
    result = judge.analyse(gateway, [Artifact(path="doc.md", text=DOC)])
    assert result.status is SignalStatus.FAILED
    assert result.score == 0.0


# --------------------------------------------------------------------------- #
# ансамбль
# --------------------------------------------------------------------------- #

def test_weights_are_renormalised_when_a_signal_is_missing():
    """Молчащий сигнал не должен читаться как «признаков нет»."""
    signals = [
        SignalResult(kind=SignalKind.FORENSICS, status=SignalStatus.UNAVAILABLE,
                     weight=0.35, note="нет истории"),
        SignalResult(kind=SignalKind.STYLOMETRY, score=0.8, weight=0.15),
        SignalResult(kind=SignalKind.JUDGE, score=0.8, weight=0.25),
    ]
    report = combine(signals)
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
    spans = [
        Span(artifact="a.go", start=0, end=100, score=0.6,
             signals=[SignalKind.PERPLEXITY], reason="ровная перплексия"),
        Span(artifact="a.go", start=50, end=180, score=0.7,
             signals=[SignalKind.JUDGE], reason="клише"),
    ]
    merged = merge_spans(spans)
    assert len(merged) == 1
    assert set(merged[0].signals) == {SignalKind.PERPLEXITY, SignalKind.JUDGE}
    assert merged[0].score > 0.7  # совпадение двух сигналов усиливает вывод
    assert "ровная перплексия" in merged[0].reason and "клише" in merged[0].reason


def test_distant_spans_do_not_merge():
    spans = [
        Span(artifact="a.go", start=0, end=50, score=0.6, signals=[SignalKind.JUDGE]),
        Span(artifact="a.go", start=500, end=600, score=0.6, signals=[SignalKind.JUDGE]),
    ]
    assert len(merge_spans(spans)) == 2


def test_ai_sensitive_spans_come_first():
    signals = [
        SignalResult(kind=SignalKind.JUDGE, score=0.6, weight=0.25, spans=[
            Span(artifact="docker-compose.yml", start=0, end=10, score=0.9,
                 signals=[SignalKind.JUDGE]),
            Span(artifact="risks.md", start=0, end=10, score=0.5,
                 signals=[SignalKind.JUDGE]),
        ]),
    ]
    report = combine(signals, ai_sensitive_paths={"risks.md"})
    assert report.spans[0].artifact == "risks.md"
    assert report.spans[0].ai_sensitive is True


# --------------------------------------------------------------------------- #
# сервис целиком
# --------------------------------------------------------------------------- #

def _bundle_with_signals() -> Bundle:
    return Bundle(
        files=[Artifact(path="doc.md", text=DOC, id="d1")],
        history=[
            HistoryEvent(at=BASE, added=8, touched_paths=["README.md"]),
            HistoryEvent(at=BASE + timedelta(minutes=2), added=700, touched_paths=["doc.md"]),
        ],
    )


def test_report_is_advisory_and_carries_limitations():
    gateway, _ = fake_gateway([_judge_response(
        "Важно отметить, что риски мошенничества требуют комплексного подхода"
    )])
    report = DetectionService(gateway).analyse(_bundle_with_signals())

    assert report.advisory is True
    assert "не влияет на балл автоматически" in report.advisory_note
    assert report.limitations
    assert 0.0 <= report.confidence_low <= report.overall_score <= report.confidence_high <= 1.0


def test_missing_declaration_with_signals_is_the_headline():
    """По условию запрещено не использование ИИ, а несогласованное использование."""
    gateway, _ = fake_gateway([_judge_response(
        "Важно отметить, что риски мошенничества требуют комплексного подхода"
    )])
    report = DetectionService(gateway).analyse(_bundle_with_signals())

    assert report.declared_ai_usage is False
    assert report.mismatch is True
    assert "расхождение" in report.declaration_note


def test_declaration_is_found_and_quoted():
    bundle = Bundle(
        files=[Artifact(
            path="doc.md",
            text=DOC + "\n\nПри подготовке работы я использовал ChatGPT для проверки формулировок.\n",
        )],
        history=[HistoryEvent(at=BASE, added=10, touched_paths=["doc.md"])],
    )
    gateway, _ = fake_gateway(['{"findings": []}'])
    report = DetectionService(gateway).analyse(bundle)

    assert report.declared_ai_usage is True
    assert "ChatGPT" in report.declaration_note
    assert report.mismatch is False


def test_perplexity_absence_is_reported_not_hidden():
    gateway, _ = fake_gateway(['{"findings": []}'])
    report = DetectionService(gateway).analyse(_bundle_with_signals())
    signal = report.signal(SignalKind.PERPLEXITY)
    assert signal.status is SignalStatus.UNAVAILABLE
    assert any("Перплексия" in limit or "перплексия" in limit for limit in report.limitations)


def test_detection_works_without_a_gateway_at_all():
    """Форензика и стилометрия не нуждаются в модели — детектор обязан работать без неё."""
    report = DetectionService(None, DetectionConfig(use_judge=False)).analyse(
        _bundle_with_signals()
    )
    assert report.overall_score > 0.3
    assert report.signal(SignalKind.FORENSICS).status is SignalStatus.OK
