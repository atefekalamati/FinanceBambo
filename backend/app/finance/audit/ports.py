"""Audit interface kept independent from its final BAMBO persistence adapter."""

from typing import Mapping, Protocol


class AuditWriter(Protocol):
    async def append(self, event: Mapping[str, object]) -> None: ...
