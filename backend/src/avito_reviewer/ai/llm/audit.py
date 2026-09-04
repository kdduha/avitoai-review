"""Журнал обращений к моделям.

Хранится то, чем можно отчитаться перед безопасностью и перед финансами:
маршрут, модель, число обезличенных фрагментов, хэш промпта, токены, цена.
Сам промпт не хранится — иначе журнал станет тем самым местом, где утекут
персональные данные, от которых мы их защищали.
"""

from __future__ import annotations

import json
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


@dataclass
class AuditLog:
    records: list[AuditRecord] = field(default_factory=list)

    def add(self, record: AuditRecord) -> None:
        self.records.append(record)

    # ------------------------------------------------------------------ #

    def checkpoint(self) -> int:
        """Mark the current end of the journal to summarise one run against.

        The journal is per-application, not per-request: it has to be, because the
        cost of a course run is the sum over its submissions. So a single review
        reports its own tokens by taking a checkpoint first and summarising the
        tail — otherwise every draft would claim the whole day's spend.
        """
        return len(self.records)

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

    def summary(self, since: int = 0) -> dict[str, object]:
        """Counters over the records added after ``since`` (a :meth:`checkpoint`)."""
        window = self.records[since:]
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
