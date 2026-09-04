"""Журнал обращений к моделям.

Хранится то, чем можно отчитаться перед безопасностью и перед финансами:
маршрут, модель, число обезличенных фрагментов, хэш промпта, токены, цена.
Сам промпт не хранится — иначе журнал станет тем самым местом, где утекут
персональные данные, от которых мы их защищали.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Порядок цены для дешёвой модели через OpenRouter, ₽ за миллион токенов.
RUB_PER_MTOK_IN = 14.0
RUB_PER_MTOK_OUT = 56.0


@dataclass
class AuditRecord:
    request_id: str
    provider: str
    model: str
    task: str
    data_class: str
    route: str
    redactions: int
    prompt_sha256: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    error: str | None = None
    at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def cost_rub(self) -> float:
        return round(
            self.tokens_in / 1_000_000 * RUB_PER_MTOK_IN
            + self.tokens_out / 1_000_000 * RUB_PER_MTOK_OUT,
            4,
        )


# Прогоны, открытые в текущем контексте выполнения: пары (журнал, приёмник).
# Именно контекст, а не глобальный список: два запроса идут в разных потоках,
# и каждый должен видеть свои записи, а не записи соседа.
_open_runs: ContextVar[tuple[tuple[int, list["AuditRecord"]], ...]] = ContextVar(
    "avito_audit_runs", default=()
)


@dataclass
class AuditLog:
    records: list[AuditRecord] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def add(self, record: AuditRecord) -> None:
        with self._lock:
            self.records.append(record)
        for owner, sink in _open_runs.get():
            if owner == id(self):
                sink.append(record)

    # ------------------------------------------------------------------ #

    @contextmanager
    def collect(self) -> Iterator[list[AuditRecord]]:
        """Записи одного прогона, отдельно от общего журнала.

        Журнал один на приложение — иначе не сложить стоимость прогона курса.
        Но черновик обязан отчитаться о своих токенах, а не о чужих, и срезом
        по длине это не решается: `/review` уходит в поток, два запроса идут
        внахлёст, и «хвост журнала» первого включит записи второго.

        Приёмник живёт в контексте выполнения, а не в общем списке: подписка на
        всё подряд имела бы ровно тот же изъян, что и срез, — соседний прогон
        писал бы в чужой счёт. Вложенные прогоны считаются включительно: внешний
        видит и то, что сделал внутренний.
        """
        sink: list[AuditRecord] = []
        token = _open_runs.set((*_open_runs.get(), (id(self), sink)))
        try:
            yield sink
        finally:
            _open_runs.reset(token)

    @property
    def total_cost_rub(self) -> float:
        # Округление до копеек съедало бы стоимость коротких вызовов, а из
        # них и складывается счёт за поток работ.
        return round(sum(r.cost_rub for r in self.records), 4)

    @property
    def total_tokens(self) -> tuple[int, int]:
        return (
            sum(r.tokens_in for r in self.records),
            sum(r.tokens_out for r in self.records),
        )

    @property
    def external_calls(self) -> list[AuditRecord]:
        return [r for r in self.records if r.route != "local_only"]

    def summary(self, records: Sequence[AuditRecord] | None = None) -> dict[str, object]:
        """Counters over ``records``, or over the whole journal when omitted."""
        window = list(self.records if records is None else records)
        return {
            "calls": len(window),
            "external_calls": sum(1 for r in window if r.route != "local_only"),
            "errors": sum(1 for r in window if r.error),
            "tokens_in": sum(r.tokens_in for r in window),
            "tokens_out": sum(r.tokens_out for r in window),
            "redactions": sum(r.redactions for r in window),
            "cost_rub": round(sum(r.cost_rub for r in window), 4),
        }

    def dump(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps([asdict(r) for r in self.records], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
