from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from avito_reviewer.app.auth import CurrentUser, create_access_token, verify_password
from avito_reviewer.app.schemas.auth import LoginRequest, MeResponse, TokenResponse
from avito_reviewer.config import AuthConfig
from avito_reviewer.db import User, session_dependency

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


@router.get("/me", summary="Who the bearer token belongs to")
async def me(user: CurrentUser) -> MeResponse:
    return MeResponse(id=user.id, username=user.username, role=user.role, display_name=user.display_name)
