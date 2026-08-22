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

ALL_FINANCE_PERMISSIONS = (
    "finance.view",
    "finance.edit",
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
    requested scope exactly, plus assignment rows keyed by assignmentExternalId.
    """

    def __init__(self, organization_id: UUID, project_id: str, snapshot_id: UUID, assignments):
        self._organization_id, self._project_id = str(organization_id), project_id
        self._snapshot_id, self._assignments = str(snapshot_id), list(assignments)

    async def get_snapshot(self, organization_id, project_id, snapshot_id):
        if (str(organization_id) != self._organization_id
                or project_id != self._project_id
                or str(snapshot_id) != self._snapshot_id):
            return {"snapshot": {}, "assignments": []}
        return {
            "snapshot": {
                "organizationId": self._organization_id,
                "projectId": self._project_id,
                "progressSnapshotId": self._snapshot_id,
            },
            "assignments": [dict(row) for row in self._assignments],
        }


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
