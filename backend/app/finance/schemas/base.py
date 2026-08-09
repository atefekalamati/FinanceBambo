"""Shared JSON-boundary behavior for Finance DTOs."""

from pydantic import BaseModel, ConfigDict


def to_camel(name: str) -> str:
    head, *tail = name.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ApiModel(BaseModel):
    """Strict DTO base using the PRD's camelCase JSON contract."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )
