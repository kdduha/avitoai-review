"""Run Alembic migrations from inside the app, not a separate manual step.

`alembic upgrade head` is itself a blocking call (it drives its own event
loop inside `migrations/env.py`'s `asyncio.run`) — calling it directly from
an already-running async lifespan would hit "asyncio.run() cannot be called
from a running event loop". `run_migrations` is meant to be awaited through
`starlette.concurrency.run_in_threadpool`, the same escape hatch the review
pipeline already uses for its own blocking work (see `app/routers/review.py`).
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

_BACKEND_ROOT = Path(__file__).resolve().parents[3]


def run_migrations() -> None:
    cfg = Config(str(_BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_ROOT / "migrations"))
    command.upgrade(cfg, "head")
