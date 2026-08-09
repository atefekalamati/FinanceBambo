"""Validated context supplied by the BAMBO host adapter."""

import re
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from ..schemas.base import ApiModel


class AuthContext(ApiModel):
    user_id: UUID
    organization_id: UUID
    project_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    organization_role: str = Field(min_length=1)
    project_role: str = Field(min_length=1)
    permission_codes: tuple[str, ...]
    locale: Literal["fa-IR"]
    timezone: Literal["Asia/Tehran"]

    @field_validator("permission_codes")
    @classmethod
    def validate_permission_codes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("permission codes must be unique")
        pattern = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
        if any(pattern.fullmatch(code) is None for code in value):
            raise ValueError("invalid permission code")
        return value
