from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from avito_reviewer.db import Role


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Role
    display_name: str


class MeResponse(BaseModel):
    id: UUID
    username: str
    role: Role
    display_name: str
