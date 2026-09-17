"""Development stand-ins for the six ports the BAMBO host is supposed to provide.

DEVELOPMENT ONLY. The auth provider here trusts a static context and the scope and
permission gates only compare it against the seeded tenant. Nothing in this package
belongs in a deployed environment; the real host owns identity, membership and
permissions, and `backend/app` is written so it never has to know how.
"""

from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException

from app.finance.security.context import AuthContext

#: Every permission the router actually gates on, so the development operator can reach
#: every route. `finance.manage_invoice` was missing, and it is the one the whole invoice
#: pipeline hangs from: uploading a file, starting an extraction, retrying it, rejecting
#: it and confirming it all require it. Its absence meant the dev host answered 403 to the
#: FIRST step of that pipeline, so nobody could test it here at all -- and a 403 on upload
#: is indistinguishable, from the browser, from the extraction being broken.
#:
#: Derived from the router rather than remembered: `test_dev_permissions_cover_the_router`
#: greps the routes and fails if this list falls behind again.
ALL_FINANCE_PERMISSIONS = (
    "finance.view",
    "finance.edit",
    "finance.manage_invoice",
    "finance_report.view",
    "finance_report.issue",
    "finance_report.export",
)


class StaticAuthContextProvider:
    """Returns one signed-in operator. A real host derives this from its session."""

    def __init__(self, organization_id: UUID, project_id: str, user_id: UUID,
                 permission_codes=ALL_FINANCE_PERMISSIONS, organization_role="org_chief"):
        self._context = AuthContext(
            userId=user_id,
            organizationId=organization_id,
            projectId=project_id,
            organizationRole=organization_role,
            projectRole="finance_expert",
            permissionCodes=list(permission_codes),
            locale="fa",
            timezone="Asia/Tehran",
        )

    @property
    def context(self) -> AuthContext:
        return self._context

    async def current(self, _request) -> AuthContext:
        return self._context


class SingleTenantScopeAuthorizer:
    """Grants membership only for the seeded organization and project."""

    def __init__(self, organization_id: UUID, project_id: str):
        self._organization_id, self._project_id = str(organization_id), project_id

    async def require_organization(self, _context, organization_id) -> None:
        if str(organization_id) != self._organization_id:
            raise HTTPException(403, "organization membership is required")

    async def require_project(self, _context, organization_id, project_id) -> None:
        if str(organization_id) != self._organization_id or project_id != self._project_id:
            raise HTTPException(403, "project membership is required")


class ContextPermissionAuthorizer:
    """Checks the permission codes carried by the context, with no hidden fallback."""

    async def require(self, context, permission_code: str) -> None:
        if permission_code not in context.permission_codes:
            raise HTTPException(403, f"permission {permission_code} is required")


class LocalFileStorage:
    """Writes attachment bytes under a local directory keyed by a non-guessable name."""

    def __init__(self, root: Path):
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, organization_id, project_id, stored_name) -> Path:
        directory = self._root / str(organization_id) / str(project_id)
        directory.mkdir(parents=True, exist_ok=True)
        return directory / str(stored_name)

    async def put(self, metadata, content: bytes):
        stored = getattr(metadata, "stored_name", None) or str(uuid4())
        path = self._path(
            getattr(metadata, "organization_id", "org"),
            getattr(metadata, "project_id", "project"),
            stored,
        )
        path.write_bytes(content)
        return stored

    async def get(self, organization_id, project_id, file_id):
        path = self._path(organization_id, project_id, file_id)
        if not path.exists():
            raise FileNotFoundError(f"attachment {file_id} is not stored locally")
        return path.read_bytes()


class SeededProgressSnapshotProvider:
    """Serves the progress feed the host normally proxies from the progress module.

    The feed shape follows the Integration Kit: a snapshot header that must match the
    requested scope exactly, plus assignment rows keyed by assignmentExternalId. The
    header is built here rather than read from the finance-side ref row, because the
    feed response is assembled from whatever this provider returns.
    """

    def __init__(self, organization_id: UUID, project_id: str, snapshots, imported_by: UUID):
        self._organization_id, self._project_id = str(organization_id), project_id
        self._feeds = {}
        self._order = []
        self._aliases = {}
        for snapshot in snapshots:
            snapshot_id = str(snapshot["progress_snapshot_id"])
            self._order.append(snapshot_id)
            # Indexed by the host identifier as well, because that is what Finance asks
            # with once a reference records one. A real host only ever knows its own id;
            # the fixture answers to both so the seeded and ingested paths both work.
            if snapshot.get("host_snapshot_id") is not None:
                self._aliases[str(snapshot["host_snapshot_id"])] = snapshot_id
            self._feeds[snapshot_id] = {
                "snapshot": {
                    "organizationId": self._organization_id,
                    "projectId": self._project_id,
                    "progressSnapshotId": snapshot_id,
                    # Core identifies snapshots and schedule files with bigint, so the
                    # fixture does too. A mock that hands back a UUID here would let
                    # ingestion pass locally and fail against a real host.
                    "hostSnapshotId": snapshot.get("host_snapshot_id"),
                    "hostFileVersionId": snapshot.get("host_file_version_id"),
                    "sourceFileVersionId": str(snapshot["source_file_version_id"]),
                    "sourceFileNameSafe": snapshot["source_file_name_safe"],
                    "reportingDate": snapshot["reporting_date"].isoformat(),
                    "status": "ready",
                    "importedBy": str(imported_by),
                    "importedAt": snapshot["imported_at"].isoformat(),
                },
                "assignments": snapshot["assignments"],
            }

    async def current_snapshot(self, organization_id, project_id, as_of=None):
        """The newest snapshot this fixture holds for the scope, or None.

        Stands in for the host answering "which snapshot is current for this project". The
        newest is the last one seeded, mirroring a host that publishes in order. A scope it
        does not serve gets None, not an empty header -- see get_snapshot below for why.
        """
        if (str(organization_id) != self._organization_id or project_id != self._project_id
                or not self._order):
            return None
        return await self.get_snapshot(organization_id, project_id, self._order[-1])

    async def get_snapshot(self, organization_id, project_id, snapshot_id):
        key = str(snapshot_id)
        feed = self._feeds.get(self._aliases.get(key, key))
        if (feed is None
                or str(organization_id) != self._organization_id
                or project_id != self._project_id):
            # None, not a header with nothing in it. An empty header claims "here is the
            # snapshot you asked for" and then describes no snapshot at all, which is how
            # a scope miss used to reach the caller as a 500 instead of a 404. Finance
            # rejects both shapes now, but a development host should not model the wrong
            # one for a production provider to copy.
            return None
        # Echo back the identifier the caller asked with. Finance verifies the header
        # against what it sent, and it sends the Core bigint whenever the reference row
        # records one -- so answering with the Finance UUID makes a valid request look like
        # a snapshot that does not exist. A real provider only ever knows its own id and
        # therefore cannot make this mistake; the fixture has to imitate that rather than
        # quietly being more forgiving than production.
        return {"snapshot": {**feed["snapshot"], "progressSnapshotId": key},
                "assignments": [dict(row) for row in feed["assignments"]]}


class SeededActivityProvider:
    """Stands in for the host's WBS/activity registry."""

    def __init__(self, activities):
        self._activities = {row["activityExternalId"]: dict(row) for row in activities}

    async def list_activities(self, _organization_id, _project_id, query=None, status=None,
                              page=1, page_size=50):
        rows = list(self._activities.values())
        if query:
            term = query.casefold()
            rows = [r for r in rows if term in r["title"].casefold()
                    or term in r["activityExternalId"].casefold()]
        if status:
            rows = [r for r in rows if r.get("status", "active") == status]
        start = (page - 1) * page_size
        return rows[start:start + page_size], len(rows)

    async def get_activity(self, _organization_id, _project_id, activity_external_id):
        return self._activities.get(activity_external_id)

    async def create_activity(self, _organization_id, _project_id, title,
                              wbs_code=None, parent_task_external_id=None):
        external_id = f"ACT-{len(self._activities) + 1:03d}"
        row = {"activityExternalId": external_id, "taskExternalId": external_id,
               "title": title, "wbsCode": wbs_code, "status": "active",
               "parentTaskExternalId": parent_task_external_id}
        self._activities[external_id] = row
        return row


class UnavailableExtractor:
    """AI extraction needs a real provider; fail loudly rather than invent invoice data."""

    def __init__(self, adapter_name: str):
        self.adapter_name = adapter_name

    async def extract(self, _file, _hints):
        from app.finance.services.extractions import AIExtractionFailed

        raise AIExtractionFailed(
            f"{self.adapter_name} is not configured in the development host"
        )
