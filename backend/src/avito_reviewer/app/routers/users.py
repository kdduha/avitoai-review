"""Account management — the answer to "how do I get a second reviewer to test with".

Three accounts are seeded at startup (`app/auth.py`), one per role, sharing a
password: enough to exercise every RBAC path but not enough to model an
actual team. This router is real CRUD, not a stub: an admin can add
reviewers, rename them, change their role, or remove one — no direct DB
access needed to set up anything but the initial seed.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from avito_reviewer.app.auth import RequireAdmin, hash_password
from avito_reviewer.app.schemas.users import CreateUserRequest, UpdateUserRequest, UserOut
from avito_reviewer.db import Role, Submission, User, session_dependency

router = APIRouter(tags=["users"])

Session = Annotated[AsyncSession, Depends(session_dependency)]


def _out(user: User) -> UserOut:
    return UserOut(
        id=user.id, username=user.username, role=user.role,
        display_name=user.display_name, created_at=user.created_at,
    )


async def _get_or_404(session: AsyncSession, user_id: UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="пользователь не найден")
    return user


async def _require_another_admin(session: AsyncSession, user: User) -> None:
    """``409`` if removing/demoting `user` would leave zero admins.

    Seeding only ever fills an *empty* `users` table (`app/auth.py`), so
    losing the last admin this way is not a mistake a restart undoes — it is
    a permanent lockout that only direct DB access can fix.
    """
    if Role(user.role) is not Role.ADMIN:
        return
    count = (
        await session.execute(select(func.count()).select_from(User).where(User.role == Role.ADMIN))
    ).scalar_one()
    if count <= 1:
        raise HTTPException(status_code=409, detail="это последний admin — некому будет войти, если его не станет")


@router.get("/users", summary="List every account")
async def list_users(admin: RequireAdmin, session: Session) -> list[UserOut]:
    rows = (await session.execute(select(User).order_by(User.username))).scalars().all()
    return [_out(row) for row in rows]


@router.post("/users", summary="Create an account", status_code=201)
async def create_user(body: CreateUserRequest, admin: RequireAdmin, session: Session) -> UserOut:
    """``409`` — username already taken."""
    exists = (
        await session.execute(select(User).where(User.username == body.username))
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=409, detail=f"пользователь {body.username!r} уже существует")

    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        role=body.role,
        display_name=body.display_name,
    )
    session.add(user)
    await session.commit()
    return _out(user)


@router.get("/users/{user_id}", summary="One account")
async def get_user(user_id: UUID, admin: RequireAdmin, session: Session) -> UserOut:
    return _out(await _get_or_404(session, user_id))


@router.patch("/users/{user_id}", summary="Change role, display name or password")
async def update_user(
    user_id: UUID, body: UpdateUserRequest, admin: RequireAdmin, session: Session
) -> UserOut:
    """``409`` — this would demote the last admin, leaving nobody able to log
    in as one (see `_require_another_admin`)."""
    user = await _get_or_404(session, user_id)
    if body.role is not None and body.role is not Role(user.role):
        await _require_another_admin(session, user)
        user.role = body.role
    if body.display_name is not None:
        user.display_name = body.display_name
    if body.password is not None:
        user.password_hash = hash_password(body.password)
    await session.commit()
    return _out(user)


@router.delete("/users/{user_id}", summary="Remove an account", status_code=204)
async def delete_user(user_id: UUID, admin: RequireAdmin, session: Session) -> None:
    """``409`` — this account still owns or approved submissions; reassign
    those first (`POST /submissions/{id}/reassign`). Deleting it out from
    under them would turn `reviewer_username` into a name pointing at
    nothing — a card a reviewer can never load again is worse than a delete
    that asks you to clean up first. Also ``409`` if it's the last admin
    (see `_require_another_admin`).
    """
    user = await _get_or_404(session, user_id)
    await _require_another_admin(session, user)
    owns = (
        await session.execute(
            select(Submission.id).where(
                (Submission.reviewer_id == user_id) | (Submission.approved_by == user_id)
            ).limit(1)
        )
    ).first()
    if owns is not None:
        raise HTTPException(
            status_code=409,
            detail="за пользователем числятся сдачи — переназначьте их перед удалением",
        )
    await session.delete(user)
    await session.commit()
