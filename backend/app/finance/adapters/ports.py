"""Provider-neutral host adapter interfaces from the Integration Kit."""

from typing import Mapping, Protocol

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


class ProjectActivityProvider(Protocol):
    async def list_activities(
        self,
        organization_id: str,
        project_id: str,
        query: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> object: ...

    async def get_activity(
        self, organization_id: str, project_id: str, activity_external_id: str
    ) -> object: ...

    async def create_activity(
        self,
        organization_id: str,
        project_id: str,
        title: str,
        wbs_code: str | None = None,
        parent_task_external_id: str | None = None,
    ) -> object: ...


class InvoiceImageExtractor(Protocol):
    adapter_name: str
    async def extract(self, file: object, hints: Mapping[str, object]) -> object: ...


class InvoiceVoiceExtractor(Protocol):
    adapter_name: str
    async def extract(self, file: object, hints: Mapping[str, object]) -> object: ...
