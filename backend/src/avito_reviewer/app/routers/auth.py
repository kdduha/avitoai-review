from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from avito_reviewer.app.auth import SEED_USERS, CurrentUser, create_access_token, verify_password
from avito_reviewer.app.schemas.auth import LoginRequest, MeResponse, TokenResponse
from avito_reviewer.config import AuthConfig
from avito_reviewer.db import Role, User, session_dependency

router = APIRouter(tags=["auth"])


@router.post("/auth/login", summary="Exchange a seeded login for a JWT")
async def login(
    body: LoginRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(session_dependency)],
) -> TokenResponse:
    """Hackathon-variant auth: three accounts seeded at startup, one per role
    (`student` / `reviewer` / `admin`), sharing one password — see
    `AuthConfig.seed_password`. Returns a bearer JWT good for
    `AuthConfig.access_token_ttl_minutes`.

    ``401`` — unknown username or wrong password.
    """
    user = (
        await session.execute(select(User).where(User.username == body.username))
    ).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="неверный логин или пароль")

    config: AuthConfig = request.app.state.auth_config
    token = create_access_token(user, config)
    return TokenResponse(access_token=token, role=user.role, display_name=user.display_name)


@router.post("/auth/demo", summary="Sign in as the seeded reviewer, no password")
async def demo_login(
    request: Request,
    session: Annotated[AsyncSession, Depends(session_dependency)],
) -> TokenResponse:
    """Вход одной кнопкой для записи скринкаста: пароля не спрашиваем, чтобы
    он не попал ни в кадр, ни в сборку фронта. Роль всегда `reviewer` — на
    демо показывают работу проверяющего, а раздавать `admin` без пароля
    незачем.

    ``404`` — демо-вход выключен (`AUTH_DEMO_LOGIN=false`) или сеяного
    ревьюера в базе нет: его могли переименовать или удалить через `/users`.
    """
    config: AuthConfig = request.app.state.auth_config
    if not config.demo_login:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="демо-вход выключен")

    username = SEED_USERS[Role.REVIEWER]
    user = (
        await session.execute(select(User).where(User.username == username))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="демо-аккаунт не заведён")

    token = create_access_token(user, config)
    return TokenResponse(access_token=token, role=user.role, display_name=user.display_name)


@router.get("/me", summary="Who the bearer token belongs to")
async def me(user: CurrentUser) -> MeResponse:
    return MeResponse(id=user.id, username=user.username, role=user.role, display_name=user.display_name)
