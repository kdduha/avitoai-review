from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from avito_reviewer.db import Role


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=4, description="Хранится только хэшем (PBKDF2), см. app/auth.py")
    role: Role
    display_name: str = ""


class UpdateUserRequest(BaseModel):
    """Все поля необязательные — правится только то, что указано."""

    role: Role | None = None
    display_name: str | None = None
    password: str | None = Field(default=None, min_length=4)


class UserOut(BaseModel):
    id: UUID
    username: str
    role: Role
    display_name: str
    created_at: datetime
