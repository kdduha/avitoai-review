"""chat message ordering

Revision ID: c3f1a7d20b45
Revises: a2928e3e641a
Create Date: 2026-09-05 23:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3f1a7d20b45'
down_revision: str | Sequence[str] | None = 'a2928e3e641a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Порядковый номер реплики внутри сдачи.

    Существующие строки нумеруются по `created_at`, а при совпадении метки —
    по `id`. Это не восстанавливает истинный порядок хода, записанного до
    миграции: метки там и совпадают, поэтому внутри одного хода строки
    получат произвольную, но с этого момента *устойчивую* нумерацию. Лучшего
    из имеющихся данных не извлечь, а стабильность важнее: транскрипт
    перестаёт меняться от запроса к запросу.
    """
    op.add_column(
        "chat_messages",
        sa.Column("seq", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute(
        """
        UPDATE chat_messages SET seq = numbered.rn - 1
        FROM (
            SELECT id, ROW_NUMBER() OVER (
                PARTITION BY submission_id ORDER BY created_at, id
            ) AS rn
            FROM chat_messages
        ) AS numbered
        WHERE chat_messages.id = numbered.id
        """
        if op.get_bind().dialect.name == "postgresql"
        else """
        UPDATE chat_messages SET seq = (
            SELECT COUNT(*) FROM chat_messages AS earlier
            WHERE earlier.submission_id = chat_messages.submission_id
              AND (earlier.created_at < chat_messages.created_at
                   OR (earlier.created_at = chat_messages.created_at
                       AND earlier.id < chat_messages.id))
        )
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("chat_messages", "seq")
