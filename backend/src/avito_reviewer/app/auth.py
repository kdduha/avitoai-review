"""JWT auth + RBAC on top of the four roles in `docs/architecture.md` §2.

The hackathon reduction the doc itself calls out ("аутентификация — один
хардкод-логин на роль", §15) is implemented literally: `seed_users` creates
one account per :class:`~avito_reviewer.db.Role`, sharing one password from
config. A real deployment swaps the seed step for actual user records; the
token and dependency plumbing below does not change.

Password hashing uses stdlib PBKDF2 rather than a third-party hasher — the
credentials it protects are, by design, not secrets (`AuthConfig.seed_password`
is dev-only and documented as such), so the extra dependency would buy nothing.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from avito_reviewer.config import AuthConfig
from avito_reviewer.db import Role, User, session_dependency
from avito_reviewer.distribution import ReviewerStore

log = logging.getLogger(__name__)

_PBKDF2_ITERATIONS = 260_000
_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        salt_hex, _ = encoded.split("$", 1)
    except ValueError:
        return False
    expected = hash_password(password, salt=bytes.fromhex(salt_hex))
    return hmac.compare_digest(expected, encoded)


def create_access_token(user: User, config: AuthConfig) -> str:
    now = datetime.now(tz=UTC)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": str(user.role),
        "iat": now,
        "exp": now + timedelta(minutes=config.access_token_ttl_minutes),
    }
    return jwt.encode(payload, config.jwt_secret.get_secret_value(), algorithm=config.jwt_algorithm)


def decode_access_token(token: str, config: AuthConfig) -> dict:
    try:
        return jwt.decode(token, config.jwt_secret.get_secret_value(), algorithms=[config.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="токен недействителен") from exc


SEED_USERS: dict[Role, str] = {
    Role.STUDENT: "student",
    Role.REVIEWER: "reviewer",
    Role.METHODIST: "methodist",
    Role.ADMIN: "admin",
}


async def seed_users(session: AsyncSession, config: AuthConfig) -> None:
    """Create the four hardcoded accounts if the table is empty.

    Idempotent by presence, so restarting the app never duplicates or resets
    them — only an empty `users` table gets seeded.
    """
    existing = (await session.execute(select(User.username))).scalars().all()
    if existing:
        return
    password_hash = hash_password(config.seed_password)
    for role, username in SEED_USERS.items():
        session.add(
            User(
                username=username,
                password_hash=password_hash,
                role=role,
                display_name=username.capitalize(),
            )
        )
    await session.commit()
    log.info("auth: seeded %d accounts (%s)", len(SEED_USERS), ", ".join(SEED_USERS.values()))


async def seed_roster_reviewers(
    session: AsyncSession, config: AuthConfig, reviewers: ReviewerStore
) -> int:
    """Аккаунт на каждую карточку каталога `backend/reviewers/`.

    Каталог ревьюеров — десять настоящих карточек с навыками, ёмкостью и
    курсами; на них и держится демонстрация распределения. Без аккаунтов они
    оставались данными, которые некуда приложить: назначить на поток можно
    только строку `users`, поэтому в интерфейсе было два ревьюера с ёмкостью
    по умолчанию вместо десяти с разными.

    Идемпотентно по логину, а не по пустоте таблицы: правило каталога —
    «добавить ревьюера значит добавить JSON» — должно продолжать работать и
    после того, как база завелась. Уже существующий аккаунт не трогается:
    пароль и роль могли поменять руками, и перезапись стёрла бы это молча.
    """
    known = set((await session.execute(select(User.username))).scalars().all())
    password_hash = hash_password(config.seed_password)
    added = [card for card in reviewers.all() if card.id not in known]
    for card in added:
        session.add(
            User(
                username=card.id,
                password_hash=password_hash,
                role=Role.REVIEWER,
                display_name=card.name,
            )
        )
    if added:
        await session.commit()
        log.info("auth: seeded %d reviewer accounts from the roster", len(added))
    return len(added)


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(session_dependency)],
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="нужен Bearer-токен")

    config: AuthConfig = request.app.state.auth_config
    payload = decode_access_token(credentials.credentials, config)
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="токен повреждён") from exc

    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="пользователь не найден")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]

_RANK: dict[str, int] = {
    Role.STUDENT.value: 0,
    Role.REVIEWER.value: 1,
    Role.METHODIST.value: 2,
    Role.ADMIN.value: 3,
}


def require_role(minimum: Role):
    """Dependency factory: at least `minimum` on the
    student < reviewer < methodist < admin ladder."""

    async def _check(user: CurrentUser) -> User:
        if _RANK[str(user.role)] < _RANK[minimum.value]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"нужна роль не ниже {minimum.value}",
            )
        return user

    return _check


RequireReviewer = Annotated[User, Depends(require_role(Role.REVIEWER))]
RequireMethodist = Annotated[User, Depends(require_role(Role.METHODIST))]
"""Кто задаёт, против чего оценивают: рубрики, задания, дедлайны."""
RequireAdmin = Annotated[User, Depends(require_role(Role.ADMIN))]
