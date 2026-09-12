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
    """Read access to the host's published progress snapshots.

    `current_snapshot` was added so Finance can pin a financial figure to a Core snapshot
    without a user first creating a Finance-side record by hand. Before it existed, the only
    way a `progress_snapshot_refs` row came into being was the development seed, so a
    production database had none and every live report answered 404.

    It is deliberately optional. A host that does not implement it keeps the previous
    behaviour exactly -- Finance uses whatever references already exist and reports honestly
    when there are none. `supports_current_snapshot` is how a caller asks, rather than
    catching AttributeError and hoping that is what it meant.
    """

    async def get_snapshot(
        self, organization_id: str, project_id: str, snapshot_id: str
    ) -> object: ...

    async def current_snapshot(
        self, organization_id: str, project_id: str, as_of: object
    ) -> object: ...


def supports_current_snapshot(provider: object) -> bool:
    """Whether this provider can answer "which snapshot is current for this project"."""
    return callable(getattr(provider, "current_snapshot", None))


class ActorDirectory(Protocol):
    """Names for the user ids Finance stores but does not own.

    Finance records an actor as a bare UUID and keeps it that way -- the people belong to the
    host, and a Finance-side copy of them would be a second source of truth. This port is the
    read path that was missing: it turns the ids in a response into names at the boundary,
    without any Finance table learning what a person is called.

    `names` takes every id in one response and answers in one call, because a list of fifty
    invoices written by three people is three names and fifty lookups would be an N+1 built
    into the contract. Ids it cannot resolve are simply absent from the answer -- an unknown
    user is not an error, and the caller shows the id.
    """

    async def names(self, user_ids: object) -> Mapping[str, str]: ...


def supports_actor_names(directory: object) -> bool:
    """Whether this host can say what its people are called.

    Asked rather than assumed, exactly as `supports_current_snapshot` is: a deployment with
    no Core directory keeps the previous behaviour -- every id renders as an id -- instead of
    catching AttributeError somewhere and hoping that is what it meant.
    """
    return callable(getattr(directory, "names", None))


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
