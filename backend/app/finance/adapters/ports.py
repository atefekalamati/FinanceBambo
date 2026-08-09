"""Provider-neutral host adapter interfaces from the Integration Kit."""

from typing import Protocol

from fastapi import Request

from ..security.context import AuthContext


class AuthContextProvider(Protocol):
    async def current(self, request: Request) -> AuthContext: ...


class FileStorage(Protocol):
    async def put(self, metadata: object, content: bytes) -> object: ...

    async def get(
        self, organization_id: str, project_id: str, file_id: str
    ) -> object: ...


class ProgressSnapshotProvider(Protocol):
    async def get_snapshot(
        self, organization_id: str, project_id: str, snapshot_id: str
    ) -> object: ...
