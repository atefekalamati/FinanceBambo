# -*- coding: utf-8 -*-
"""The two MPP mapping routes, on the production router rather than the development host.

WHY THESE EXIST

The mapping has been able to turn a schedule's fixed costs into estimate lines since 0012,
and the only way to ask it to was `devhost/app.py` -- a host that is not what runs in
production. So a deployed Finance had the code, the tables and the data, and no route to
the operation: the fixed-cost lines appeared when a developer remembered to call the
mapper after an import, and did not when nobody did.

These pin the two things that makes safe to publish: the guards are the ordinary Finance
ones, and the write is repeatable. A remap somebody runs twice because they were not sure
the first one took must not double the project's estimate.
"""

import sys
import unittest
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.main import create_app
from app.finance.security.context import AuthContext

ORG = UUID("11111111-1111-4111-8111-111111111111")
ACTOR = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
PROJECT = "sample_site_01"
BASE = "/api/projects/%s/finance" % PROJECT
VERSION = UUID("afe50159-86e5-4e65-9f31-e0fd01ef29e7")


class AuthProvider:
    def __init__(self, permissions):
        self.permissions = tuple(permissions)

    async def current(self, _request):
        return AuthContext(userId=ACTOR, organizationId=ORG, projectId=PROJECT,
                           permissionCodes=list(self.permissions),
                           organizationRole="finance_expert",
                           projectRole="finance_expert",
                           timezone="Asia/Tehran", locale="fa")


class ScopeAuthorizer:
    async def require_organization(self, _context, organization_id):
        if organization_id != str(ORG):
            raise HTTPException(403, "organization denied")

    async def require_project(self, _context, organization_id, project_id):
        if organization_id != str(ORG) or project_id != PROJECT:
            raise HTTPException(403, "project denied")


class PermissionAuthorizer:
    async def require(self, context, permission_code):
        if permission_code not in context.permission_codes:
            raise HTTPException(403, "permission denied")


class Mapping:
    """A mapping service with the real one's identity rule and none of its SQL.

    `lines` is the book the real match-or-insert keeps in the database: a line per task,
    created once. That is what makes the second remap here report `matched` for the same
    reason the real one does, rather than because this fake was told to.
    """

    def __init__(self, version=VERSION, detail=None, tasks=(1227, 1229, 1231, 0)):
        self.version = version
        self._detail = detail
        self._tasks = tuple(tasks)
        self.lines = {}
        self.calls = []

    async def current_version_id(self, _organization_id, _project_id):
        return self.version

    async def current_version_detail(self, _organization_id, _project_id):
        if self.version is None:
            return None
        return self._detail or {
            "id": self.version, "source_file_name_safe": "terrace.mpp",
            "imported_at": "2026-09-20T04:12:00+00:00",
            "reporting_date": "2026-09-19", "row_count": 835}

    async def mapping_status(self, _organization_id, _project_id):
        if self.version is None:
            return {"sourceVersionId": None, "total": 0, "assignmentMapped": 0,
                    "activityOnly": 0, "unclassified": 0,
                    "activityOnlyDetail": {"stageLabelRows": 0,
                                           "assignmentsWithoutResource": 0},
                    "unclassifiedRows": []}
        return {"sourceVersionId": str(self.version), "total": 835,
                "assignmentMapped": 715, "activityOnly": 120, "unclassified": 0,
                "activityOnlyDetail": {"stageLabelRows": 118,
                                       "assignmentsWithoutResource": 2},
                "unclassifiedRows": []}

    async def map_source_version(self, organization_id, project_id, version_id,
                                 actor_user_id=None):
        self.calls.append((organization_id, project_id, version_id, actor_user_id))
        created = matched = 0
        for task in self._tasks:
            if task in self.lines:
                matched += 1
                continue
            self.lines[task] = uuid4()
            created += 1
        return {"sourceVersionId": str(version_id),
                "resourcesCreated": 0, "resourcesMatched": 0,
                "linesCreated": 0, "linesMatched": 0, "linesWithEstimate": 0,
                "fixedCostLinesCreated": created, "fixedCostLinesMatched": matched,
                "fixedCostIrr": "51484880064" if created else "0",
                "fixedCostResidueRows": 21, "fixedCostResidueFileUnits": "5.9",
                "unmappedRows": 0, "unclassifiedResources": []}


def client(permissions=("finance.view", "finance.edit"), mapping=None, configured=True):
    app = create_app()
    app.state.auth_context_provider = AuthProvider(permissions)
    app.state.scope_authorizer = ScopeAuthorizer()
    app.state.permission_authorizer = PermissionAuthorizer()
    if configured:
        app.state.finance_mpp_mapping_service = mapping or Mapping()
    return TestClient(app, raise_server_exceptions=False)


class StatusTests(unittest.TestCase):
    def test_it_reports_the_counts_and_the_file_they_were_taken_over(self):
        mapping = Mapping()
        with client(mapping=mapping) as api:
            response = api.get(BASE + "/mpp/status")
        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        self.assertEqual(835, body["total"])
        self.assertEqual(715, body["assignmentMapped"])
        self.assertEqual("terrace.mpp", body["sourceFileName"])
        self.assertEqual("2026-09-20T04:12:00+00:00", body["importedAt"])
        self.assertEqual("2026-09-19", body["reportingDate"])
        self.assertEqual(835, body["rowCount"])

    def test_a_project_that_imported_nothing_is_not_an_error(self):
        with client(mapping=Mapping(version=None)) as api:
            response = api.get(BASE + "/mpp/status")
        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        self.assertIsNone(body["sourceVersionId"])
        self.assertIsNone(body["sourceFileName"])
        self.assertEqual(0, body["total"])

    def test_reading_requires_finance_view(self):
        with client(permissions=("finance.edit",)) as api:
            response = api.get(BASE + "/mpp/status")
        self.assertEqual(403, response.status_code)

    def test_it_writes_nothing(self):
        mapping = Mapping()
        with client(mapping=mapping) as api:
            api.get(BASE + "/mpp/status")
        self.assertEqual([], mapping.calls, "a status must never run a mapping")

    def test_a_host_without_the_mapper_says_so_rather_than_failing(self):
        with client(configured=False) as api:
            response = api.get(BASE + "/mpp/status")
        self.assertEqual(503, response.status_code)


class RemapTests(unittest.TestCase):
    def test_it_maps_the_projects_own_active_version(self):
        mapping = Mapping()
        with client(mapping=mapping) as api:
            response = api.post(BASE + "/mpp/remap")
        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        self.assertEqual(4, body["fixedCostLinesCreated"])
        self.assertEqual(0, body["fixedCostLinesMatched"])
        self.assertEqual("51484880064", body["fixedCostIrr"])
        self.assertEqual(21, body["fixedCostResidueRows"])
        organization, project, version, actor = mapping.calls[0]
        self.assertEqual(str(ORG), organization)
        self.assertEqual(PROJECT, project)
        self.assertEqual(VERSION, version, "the project's own version, not a caller's")
        self.assertEqual(ACTOR, actor, "the financial record names who asked for it")

    def test_running_it_twice_matches_instead_of_duplicating(self):
        mapping = Mapping()
        with client(mapping=mapping) as api:
            first = api.post(BASE + "/mpp/remap").json()
            second = api.post(BASE + "/mpp/remap").json()
        self.assertEqual(4, first["fixedCostLinesCreated"])
        self.assertEqual(0, second["fixedCostLinesCreated"])
        self.assertEqual(4, second["fixedCostLinesMatched"])
        self.assertEqual(4, len(mapping.lines), "four lines exist, not eight")

    def test_a_project_with_no_ready_version_is_a_404_and_not_a_500(self):
        with client(mapping=Mapping(version=None)) as api:
            response = api.post(BASE + "/mpp/remap")
        self.assertEqual(404, response.status_code, response.text)
        self.assertEqual("FINANCE_NOT_FOUND", response.json()["error"]["code"])

    def test_writing_requires_finance_edit(self):
        mapping = Mapping()
        with client(permissions=("finance.view",), mapping=mapping) as api:
            response = api.post(BASE + "/mpp/remap")
        self.assertEqual(403, response.status_code)
        self.assertEqual([], mapping.calls, "refused before anything was written")

    def test_a_host_without_the_mapper_says_so_rather_than_failing(self):
        with client(configured=False) as api:
            response = api.post(BASE + "/mpp/remap")
        self.assertEqual(503, response.status_code)


class ContractTests(unittest.TestCase):
    """Both routes are in the exported contract, so the frontend is told before it breaks."""

    def setUp(self):
        import json
        self.contract = json.loads(
            (BACKEND_ROOT / "contracts" / "openapi.json").read_text(encoding="utf-8"))

    def test_both_routes_are_published(self):
        paths = self.contract["paths"]
        for path, method in (("/api/projects/{projectId}/finance/mpp/status", "get"),
                             ("/api/projects/{projectId}/finance/mpp/remap", "post")):
            with self.subTest(path=path):
                self.assertIn(path, paths)
                self.assertIn(method, paths[path])


if __name__ == "__main__":
    unittest.main()
