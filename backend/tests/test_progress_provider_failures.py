"""A host provider that cannot answer must produce 404, never 500.

`ProgressSnapshotProvider` is implemented by the BAMBO host and its port constrains
nothing about the reply. Finance used to read `feed["snapshot"]["organizationId"]`
straight through, so a provider that returned a header with nothing in it -- which is
exactly what the development host returned for any scope it did not recognise -- raised
KeyError and left the caller with a 500. A 500 says "this service is broken" about a
request that simply asked for something the provider does not have, and it is the wrong
answer for a caller who is not allowed to see the snapshot either.

Every test here goes through the real router and the real exception handlers, because the
guarantee is about the response a client receives, not about which exception a service
raises internally.
"""

import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.main import create_app
from app.finance.security.context import AuthContext
from app.finance.services.progress import ProgressService

ORG = UUID("11111111-1111-4111-8111-111111111111")
OTHER_ORG = UUID("22222222-2222-4222-8222-222222222222")
ACTOR = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
PROJECT = "sample_site_01"
SNAPSHOT = UUID("30000000-0000-4000-8000-000000000001")
REF = UUID("30000000-0000-4000-8000-0000000001ff")
LINE = UUID("10000000-0000-4000-8000-000000000001")


class AuthProvider:
    def __init__(self, project_id=PROJECT):
        self.project_id = project_id

    async def current(self, _request):
        return AuthContext(userId=ACTOR, organizationId=ORG, projectId=self.project_id,
                           organizationRole="finance_manager", projectRole="manager",
                           permissionCodes=("finance.view", "finance.edit"),
                           locale="fa-IR", timezone="Asia/Tehran")


class ScopeAuthorizer:
    """Mirrors the host's scope gate: it authorises, it does not decide existence."""

    def __init__(self, project_id=PROJECT):
        self.project_id = project_id

    async def require_organization(self, _context, organization_id):
        if organization_id != str(ORG):
            raise HTTPException(403, "organization denied")

    async def require_project(self, _context, organization_id, project_id):
        if organization_id != str(ORG) or project_id != self.project_id:
            raise HTTPException(403, "project denied")


class PermissionAuthorizer:
    async def require(self, context, permission_code):
        if permission_code not in context.permission_codes:
            raise HTTPException(403, "permission denied")


class Repository:
    """Knows one snapshot. Returning a ref is what lets the provider be reached at all."""

    def __init__(self, known=True):
        self.known = known

    async def list_snapshots(self, _scope):
        if not self.known:
            return []
        # Exactly the columns the real SELECT lists -- no "id", which the list query does
        # not return and the response model would reject as an extra.
        return [{"progress_snapshot_id": SNAPSHOT,
                 "organization_id": ORG, "project_id": PROJECT,
                 "source_file_version_id": UUID(int=7), "source_file_name_safe": "plan.mpp",
                 "imported_at": datetime(2026, 8, 2, tzinfo=timezone.utc), "imported_by": ACTOR,
                 "status": "ready", "reporting_date": date(2026, 8, 2)}]

    async def get_snapshot(self, _scope, snapshot_id):
        if not self.known or str(snapshot_id) != str(SNAPSHOT):
            return None
        return {"id": REF, "progress_snapshot_id": SNAPSHOT}

    async def latest_overrides(self, _scope, _ref_id):
        return []

    async def get_line_mapping(self, _scope, _line_id):
        return {"id": LINE, "activity_external_id": "ACT-1", "assignment_external_id": "AS1"}

    async def list_overrides(self, _scope, _line_id):
        return []

    async def append_override(self, _scope, value, _audit_id):
        return value


class Provider:
    """Returns whatever it was told to, including shapes a real host might produce."""

    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    async def get_snapshot(self, organization_id, project_id, snapshot_id):
        self.calls.append((organization_id, project_id, snapshot_id))
        return self.reply(organization_id, project_id, snapshot_id) if callable(self.reply) else self.reply


def header(organization_id=ORG, project_id=PROJECT, snapshot_id=SNAPSHOT):
    return {"organizationId": str(organization_id), "projectId": project_id,
            "progressSnapshotId": str(snapshot_id), "sourceFileVersionId": str(UUID(int=7)),
            "sourceFileNameSafe": "plan.mpp", "reportingDate": "2026-08-02",
            "status": "ready", "importedBy": str(ACTOR), "importedAt": "2026-08-02T00:00:00Z"}


def client(provider_reply, known=True, project_id=PROJECT):
    app = create_app()
    app.state.auth_context_provider = AuthProvider(project_id)
    app.state.scope_authorizer = ScopeAuthorizer(project_id)
    app.state.permission_authorizer = PermissionAuthorizer()
    app.state.progress_service = ProgressService(Repository(known), Provider(provider_reply),
                                                 id_factory=uuid4,
                                                 clock=lambda: datetime(2026, 8, 2, tzinfo=timezone.utc))
    return TestClient(app)


#: Replies a provider can produce that used to end as an unhandled exception. The empty
#: header is the one the development host actually returned for every scope miss.
HOSTILE_REPLIES = {
    "no reply at all": None,
    "an empty mapping": {},
    "a header that is missing": {"assignments": []},
    "a header with nothing in it": {"snapshot": {}, "assignments": []},
    "a null header": {"snapshot": None, "assignments": []},
    "a header that is not a mapping": {"snapshot": "ready", "assignments": []},
    "a reply that is not a mapping": ["snapshot"],
    "another organisation's snapshot": {"snapshot": header(organization_id=OTHER_ORG), "assignments": []},
    "another project's snapshot": {"snapshot": header(project_id="other_site"), "assignments": []},
    "a different snapshot than the one asked for": {"snapshot": header(snapshot_id=UUID(int=99)), "assignments": []},
}


class FeedFailureTests(unittest.TestCase):
    def test_every_unusable_reply_is_a_404_and_never_a_500(self):
        for label, reply in HOSTILE_REPLIES.items():
            with self.subTest(label), client(reply) as api:
                response = api.get(f"/api/projects/{PROJECT}/finance/progress-snapshots/{SNAPSHOT}/feed")
                self.assertEqual(404, response.status_code, response.text)

    def test_the_404_uses_the_error_envelope_the_project_already_has(self):
        with client({"snapshot": {}, "assignments": []}) as api:
            body = api.get(f"/api/projects/{PROJECT}/finance/progress-snapshots/{SNAPSHOT}/feed").json()
        # Same envelope as every other finance error: no new shape was invented for this.
        self.assertEqual({"error"}, set(body))
        self.assertEqual({"code", "message", "details", "requestId"}, set(body["error"]))
        self.assertEqual("FINANCE_NOT_FOUND", body["error"]["code"])
        self.assertEqual([], body["error"]["details"])
        self.assertIn("message", body["error"])

    def test_a_missing_snapshot_never_reaches_the_provider(self):
        # The finance-side ref is checked first, so an unknown id is answered without
        # asking the host about a snapshot it was never told exists.
        app_client = client({"snapshot": header(), "assignments": []}, known=False)
        with app_client as api:
            response = api.get(f"/api/projects/{PROJECT}/finance/progress-snapshots/{SNAPSHOT}/feed")
        self.assertEqual(404, response.status_code)
        self.assertEqual([], app_client.app.state.progress_service.provider.calls)

    def test_a_missing_project_is_refused_by_the_scope_gate(self):
        # The project the caller is scoped to is not the one in the path: that is an
        # authorisation answer, and it must not become a 500 further down either.
        with client({"snapshot": header(), "assignments": []}) as api:
            response = api.get("/api/projects/absent_project/finance/progress-snapshots/%s/feed" % SNAPSHOT)
        self.assertEqual(403, response.status_code)

    def test_a_snapshot_belonging_to_another_tenant_is_indistinguishable_from_an_absent_one(self):
        # Both answers are byte-identical, so the response cannot be used to learn that a
        # snapshot id exists in an organisation the caller may not see.
        with client({"snapshot": header(organization_id=OTHER_ORG), "assignments": []}) as foreign:
            foreign_body = foreign.get(f"/api/projects/{PROJECT}/finance/progress-snapshots/{SNAPSHOT}/feed").json()
        with client({"snapshot": {}, "assignments": []}) as absent:
            absent_body = absent.get(f"/api/projects/{PROJECT}/finance/progress-snapshots/{SNAPSHOT}/feed").json()
        # requestId is per request by design and is the only thing allowed to differ.
        for body in (foreign_body, absent_body):
            body["error"].pop("requestId")
        self.assertEqual(foreign_body, absent_body)

    def test_a_valid_reply_still_answers_200(self):
        # The guard must not have turned a working provider into a 404.
        reply = {"snapshot": header(),
                 "assignments": [{"assignmentExternalId": "AS1", "actualQuantity": "4",
                                  "manualOverride": None, "task": {"activityCode": "ACT-1"}}]}
        with client(reply) as api:
            response = api.get(f"/api/projects/{PROJECT}/finance/progress-snapshots/{SNAPSHOT}/feed")
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual("measured", response.json()["assignments"][0]["progressStatus"])


class AssignmentShapeTests(unittest.TestCase):
    """A header that checks out, with assignments the caller cannot iterate."""

    def test_absent_or_null_assignments_are_an_empty_feed_not_an_error(self):
        # A schedule can be imported before anyone reports against it, so "no assignments"
        # is a real answer. Only the header decides whether the snapshot exists.
        for label, reply in {"absent": {"snapshot": header()},
                             "null": {"snapshot": header(), "assignments": None},
                             "empty": {"snapshot": header(), "assignments": []}}.items():
            with self.subTest(label), client(reply) as api:
                response = api.get(f"/api/projects/{PROJECT}/finance/progress-snapshots/{SNAPSHOT}/feed")
                self.assertEqual(200, response.status_code, response.text)
                self.assertEqual([], response.json()["assignments"])

    def test_a_string_where_the_rows_should_be_is_not_iterated_into_characters(self):
        # Iterating a string succeeds and yields characters, which would reach the domain
        # as a feed of one-letter assignments rather than failing.
        with client({"snapshot": header(), "assignments": "AS1"}) as api:
            response = api.get(f"/api/projects/{PROJECT}/finance/progress-snapshots/{SNAPSHOT}/feed")
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual([], response.json()["assignments"])


class OverrideFailureTests(unittest.TestCase):
    """The override route reads the same feed and must answer the same way."""

    PAYLOAD = {"progressSnapshotId": str(SNAPSHOT), "overrideValue": "9", "reason": "اصلاح معتبر"}

    def test_every_unusable_reply_is_a_404_and_never_a_500(self):
        for label, reply in HOSTILE_REPLIES.items():
            with self.subTest(label), client(reply) as api:
                response = api.post(
                    f"/api/projects/{PROJECT}/finance/estimate-lines/{LINE}/progress-override",
                    json=self.PAYLOAD)
                self.assertEqual(404, response.status_code, response.text)

    def test_a_mapped_line_with_a_usable_feed_still_succeeds(self):
        reply = {"snapshot": header(),
                 "assignments": [{"assignmentExternalId": "AS1", "actualQuantity": "4",
                                  "manualOverride": None, "task": {"activityCode": "ACT-1"}}]}
        with client(reply) as api:
            response = api.post(
                f"/api/projects/{PROJECT}/finance/estimate-lines/{LINE}/progress-override",
                json=self.PAYLOAD)
        self.assertEqual(201, response.status_code, response.text)
        self.assertEqual("4", response.json()["computedValue"])

    def test_a_feed_without_the_line_is_a_mapping_error_not_a_crash(self):
        # Distinct from "the snapshot does not exist": the snapshot is right there, and
        # this line is not in it. 422 rather than 404, and its own code.
        with client({"snapshot": header(), "assignments": []}) as api:
            response = api.post(
                f"/api/projects/{PROJECT}/finance/estimate-lines/{LINE}/progress-override",
                json=self.PAYLOAD)
        self.assertEqual(422, response.status_code, response.text)
        self.assertEqual("PROGRESS_LINE_MAPPING_MISSING", response.json()["error"]["code"])


class NoUnhandledExceptionTests(unittest.TestCase):
    """The blunt version of the guarantee, stated once over every route and reply."""

    def test_no_progress_route_returns_a_server_error_for_any_reply(self):
        routes = (("GET", f"/api/projects/{PROJECT}/finance/progress-snapshots/{SNAPSHOT}/feed", None),
                  ("GET", f"/api/projects/{PROJECT}/finance/progress-snapshots/{SNAPSHOT}", None),
                  ("GET", f"/api/projects/{PROJECT}/finance/progress-snapshots", None),
                  ("POST", f"/api/projects/{PROJECT}/finance/estimate-lines/{LINE}/progress-override",
                   OverrideFailureTests.PAYLOAD))
        for label, reply in HOSTILE_REPLIES.items():
            for method, path, payload in routes:
                with self.subTest(reply=label, path=path), client(reply) as api:
                    response = api.request(method, path, json=payload)
                    self.assertLess(response.status_code, 500,
                                    "%s %s produced %d" % (method, path, response.status_code))


if __name__ == "__main__":
    unittest.main()
