# -*- coding: utf-8 -*-
"""Invoice work is its own permission, and neither side implies the other.

WHAT CHANGED AND WHY IT NEEDED A TEST OF ITS OWN

Every invoice mutation used to cost `finance.edit` -- the same permission that adds a
resource or revises an estimate line. So anybody trusted to maintain the cost breakdown was
also, silently, able to confirm a supplier's invoice and to open the photograph of it. Those
are different jobs, and in most organizations they are deliberately different people.

The separation is only real if it holds in BOTH directions, which is the part that is easy
to get wrong and impossible to see by reading one route at a time:

  * `finance.edit` must not open an invoice route -- otherwise nothing changed;
  * `finance.manage_invoice` must not open a settings or estimate route -- otherwise the
    new permission is quietly the old one plus more.

The tempting shortcut during a rollout is `manage_invoice OR edit`, so that invoice work
keeps functioning while the host catches up. It is not implemented and these tests are what
keep it from being reintroduced: they assert the ordinary editor is refused, so a fallback
would turn them red rather than pass unnoticed.

HOW THIS TEST PROVES A DENIAL HAD NO EFFECT

The application services are replaced with recorders that raise `ReachedTheService` the
moment they are called. A permitted request therefore ends in a recognisable 409, proving
the gate opened AND the work was reached; a refused one must end in 403/404 with the
recorder still empty, proving nothing was created, queued, or written on the way to being
refused. Building faithful domain objects for every route would test serialization, which
other suites already do, and would hide the one thing this suite is about.

Every principal here is synthetic and lives only inside this module. No real user, role,
permission assignment, or database row is involved.
"""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from fastapi import HTTPException
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.main import create_app
from app.finance.domain.errors import FinanceDomainError
from app.finance.security.context import AuthContext

ORG = UUID("11111111-1111-4111-8111-111111111111")
OTHER_ORG = UUID("22222222-2222-4222-8222-222222222222")
ACTOR = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
PROJECT = "sample_site_01"
OTHER_PROJECT = "annex_site_02"
FILE_ID = "33333333-3333-4333-8333-333333333331"
INVOICE_ID = "44444444-4444-4444-8444-444444444441"
DRAFT_ID = "55555555-5555-4555-8555-555555555551"
ORIGINAL_BYTES = b"\xff\xd8\xff-pretend-this-is-the-supplier-invoice-photograph"

VIEW = ("finance.view",)
VIEW_EDIT = ("finance.view", "finance.edit")
VIEW_MANAGE = ("finance.view", "finance.manage_invoice")
MANAGE_ONLY = ("finance.manage_invoice",)


class ReachedTheService(FinanceDomainError):
    """Raised by every recorder: the gate opened and the work began."""

    status = 409
    code = "REACHED_SERVICE"


class Recorder:
    """Stands in for an application service and remembers being asked to do anything."""

    def __init__(self, calls):
        self.calls = calls

    def __getattr__(self, name):
        async def called(*args, **kwargs):
            self.calls.append(name)
            raise ReachedTheService("reached %s" % name)
        return called


class Attachments(Recorder):
    """The one service with a real answer, because the bytes are the subject here."""

    METADATA = SimpleNamespace(mime_type="image/jpeg", original_name_safe="invoice-1.jpg")

    async def content(self, _scope, file_id):
        self.calls.append("content")
        return self.METADATA, ORIGINAL_BYTES


class AuthProvider:
    def __init__(self, permission_codes, organization_role="guest", project_id=PROJECT,
                 organization_id=ORG):
        self.permission_codes = permission_codes
        self.organization_role = organization_role
        self.project_id = project_id
        self.organization_id = organization_id

    async def current(self, _request):
        return AuthContext(
            userId=ACTOR, organizationId=self.organization_id, projectId=self.project_id,
            organizationRole=self.organization_role, projectRole="editor",
            permissionCodes=self.permission_codes, locale="fa-IR", timezone="Asia/Tehran")


class ScopeAuthorizer:
    """The tenant gates, refusing anything but the one organization and project."""

    async def require_organization(self, _context, organization_id):
        if organization_id != str(ORG):
            raise HTTPException(403, "organization membership is required")

    async def require_project(self, _context, organization_id, project_id):
        if organization_id != str(ORG) or project_id != PROJECT:
            raise HTTPException(403, "project membership is required")


class PermissionAuthorizer:
    """Fail-closed: only what the principal actually carries, with no implications."""

    async def require(self, context, permission_code):
        if permission_code not in context.permission_codes:
            raise HTTPException(403, "permission %s is required" % permission_code)


def api(permission_codes, organization_role="guest", project_id=PROJECT, organization_id=ORG):
    """A client for one synthetic principal, with every service replaced by a recorder."""
    calls = []
    application = create_app()
    application.state.auth_context_provider = AuthProvider(
        permission_codes, organization_role, project_id, organization_id)
    application.state.scope_authorizer = ScopeAuthorizer()
    application.state.permission_authorizer = PermissionAuthorizer()
    application.state.invoice_service = Recorder(calls)
    application.state.finance_attachment_service = Attachments(calls)
    application.state.finance_extraction_service = Recorder(calls)
    # Production requires a host-owned durable executor before async work can return 202.
    # This permission test only needs the submission seam to exist; the recorder raises
    # before any work is enqueued.
    application.state.finance_background_executor = SimpleNamespace(submit=lambda run: None)
    application.state.finance_settings_service = Recorder(calls)
    application.state.finance_resources_service = Recorder(calls)
    application.state.finance_live_report_service = Recorder(calls)
    return TestClient(application, raise_server_exceptions=False), calls


BASE = "/api/projects/%s/finance" % PROJECT
OTHER_BASE = "/api/projects/%s/finance" % OTHER_PROJECT

#: One valid invoice line, reused by every payload that needs one.
LINE = {"resourceId": str(ORG), "quantity": "1", "unit": "kg", "unitPriceIrr": "100"}

#: Every mutation that must now cost `finance.manage_invoice`, with a minimal VALID body.
#: The bodies have to validate: FastAPI answers 422 before the gate runs, so an invalid one
#: would make this suite measure the schema rather than the permission.
MUTATIONS = (
    ("post", "/invoices", {"invoiceDate": "2026-08-08", "vendorName": "V",
                           "source": "manual", "idempotencyKey": "k", "lines": [LINE]}),
    ("patch", "/invoices/%s" % INVOICE_ID, {"expectedVersion": 1, "description": "x"}),
    ("post", "/invoices/%s/confirm" % INVOICE_ID,
     {"expectedVersion": 1, "idempotencyKey": "k"}),
    ("post", "/invoices/%s/void" % INVOICE_ID,
     {"expectedVersion": 1, "idempotencyKey": "k", "reason": "duplicate"}),
    ("post", "/invoices/%s/corrective" % INVOICE_ID,
     {"idempotencyKey": "k", "reason": "correction", "financialEffectSign": 1,
      "invoiceDate": "2026-08-08", "vendorName": "V", "lines": [LINE]}),
    ("post", "/files/%s/extractions" % FILE_ID, {}),
    ("post", "/files/%s/extractions/async" % FILE_ID, {}),
    ("post", "/extractions/%s/reject" % DRAFT_ID, {"expectedVersion": 1, "reason": "unreadable"}),
    ("post", "/extractions/%s/retry" % DRAFT_ID, {}),
    ("post", "/extractions/%s/confirm" % DRAFT_ID,
     {"expectedVersion": 1, "idempotencyKey": "k",
      "invoice": {"invoiceDate": "2026-08-08", "vendorName": "V", "lines": [LINE]}}),
)

#: Non-invoice edits, used from both sides: an ordinary editor must keep them, and an
#: invoice manager must not gain them.
NON_INVOICE_EDITS = (
    ("/resources", {"type": "material", "code": "C1", "title": "T", "baseUnit": "kg"}),
    ("/estimate-lines", {"resourceId": str(ORG), "source": "progress_feed"}),
)

#: Metadata reads that must stay on `finance.view`. The originals are not among them.
READS = (
    "/invoices",
    "/invoices/%s" % INVOICE_ID,
    "/files",
    "/files/%s" % FILE_ID,
    "/extractions",
    "/extractions/%s" % DRAFT_ID,
)

CONTENT = "/files/%s/content" % FILE_ID


def send(client, method, path, body=None, base=BASE):
    if method == "post":
        return client.post(base + path, json=body if body is not None else {})
    if method == "patch":
        return client.patch(base + path, json=body if body is not None else {})
    return client.get(base + path)


def without_request_id(response):
    """The error body minus the one field that differs on every request."""
    return {key: value for key, value in response.json().get("error", {}).items()
            if key != "requestId"}


def refused(response):
    """A refusal, whatever shape: never the 409 that means the work was reached."""
    return response.status_code in (401, 403, 404, 422) and response.status_code != 409


class ViewerTests(unittest.TestCase):
    """A. `finance.view` alone: reads yes, mutations no, originals no."""

    def test_metadata_reads_are_allowed(self):
        client, calls = api(VIEW)
        with client:
            for path in READS:
                with self.subTest(path=path):
                    calls.clear()
                    response = send(client, "get", path)
                    self.assertEqual(409, response.status_code,
                                     "a viewer was refused a metadata read")
                    self.assertEqual("REACHED_SERVICE", response.json()["error"]["code"])

    def test_every_invoice_mutation_is_refused_and_nothing_happens(self):
        client, calls = api(VIEW)
        with client:
            for method, path, body in MUTATIONS:
                with self.subTest(route="%s %s" % (method.upper(), path)):
                    calls.clear()
                    response = send(client, method, path, body)
                    self.assertEqual(403, response.status_code)
                    self.assertEqual([], calls,
                                     "a refused mutation still reached the service")

    def test_the_original_file_is_concealed_rather_than_refused(self):
        """AT-09. A viewer asking for a real file id learns nothing about it."""
        client, calls = api(VIEW)
        with client:
            response = send(client, "get", CONTENT)
        self.assertEqual(404, response.status_code)
        self.assertNotIn(ORIGINAL_BYTES, response.content)
        self.assertEqual([], calls, "the attachment service was reached anyway")
        # Nothing that could be followed to the bytes by another route.
        body = response.text.lower()
        for leak in ("http://", "https://", "signature", "signed", "location", ".jpg"):
            self.assertNotIn(leak, body)
        self.assertNotIn("location", {key.lower() for key in response.headers})

    def test_an_unknown_file_id_looks_exactly_the_same(self):
        """Otherwise the difference between the two answers is the disclosure."""
        client, _calls = api(VIEW)
        with client:
            known = send(client, "get", CONTENT)
            unknown = send(client, "get",
                           "/files/99999999-9999-4999-8999-999999999999/content")
        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(without_request_id(known), without_request_id(unknown))


class OrdinaryEditorTests(unittest.TestCase):
    """B. `finance.edit` without `finance.manage_invoice` -- the fallback that must not exist."""

    def test_editing_still_works_where_it_always_did(self):
        client, _calls = api(VIEW_EDIT)
        with client:
            answers = [(path, client.post(BASE + path, json=body))
                       for path, body in NON_INVOICE_EDITS]
        for path, response in answers:
            with self.subTest(path=path):
                self.assertEqual(409, response.status_code,
                                 "an editor lost a non-invoice right")

    def test_finance_edit_opens_no_invoice_route(self):
        client, calls = api(VIEW_EDIT)
        with client:
            for method, path, body in MUTATIONS:
                with self.subTest(route="%s %s" % (method.upper(), path)):
                    calls.clear()
                    response = send(client, method, path, body)
                    self.assertEqual(403, response.status_code,
                                     "finance.edit still opens an invoice route")
                    self.assertEqual([], calls)

    def test_finance_edit_does_not_open_the_original_file(self):
        client, calls = api(VIEW_EDIT)
        with client:
            response = send(client, "get", CONTENT)
        self.assertEqual(404, response.status_code)
        self.assertNotIn(ORIGINAL_BYTES, response.content)
        self.assertEqual([], calls)


class InvoiceManagerTests(unittest.TestCase):
    """C. `finance.manage_invoice` without `finance.edit` -- and no further."""

    def test_every_invoice_mutation_is_reached(self):
        client, calls = api(VIEW_MANAGE)
        with client:
            for method, path, body in MUTATIONS:
                with self.subTest(route="%s %s" % (method.upper(), path)):
                    calls.clear()
                    response = send(client, method, path, body)
                    self.assertEqual(409, response.status_code,
                                     "an invoice manager was refused")
                    self.assertEqual(1, len(calls))

    def test_the_original_file_is_served(self):
        client, _calls = api(VIEW_MANAGE)
        with client:
            response = send(client, "get", CONTENT)
        self.assertEqual(200, response.status_code)
        self.assertEqual(ORIGINAL_BYTES, response.content)
        self.assertEqual("image/jpeg", response.headers["content-type"])
        # Sensitive bytes must not be kept by a shared cache on the way back.
        self.assertIn("private", response.headers.get("cache-control", ""))
        self.assertIn("no-store", response.headers.get("cache-control", ""))

    def test_it_grants_nothing_outside_invoices(self):
        client, calls = api(MANAGE_ONLY + ("finance.view",))
        with client:
            settings = client.patch(BASE + "/settings",
                                    json={"grossBuiltArea": "1000.0000",
                                          "effectiveFrom": "2026-08-12",
                                          "reason": "x", "expectedRevision": 1})
            edits = [(path, client.post(BASE + path, json=body))
                     for path, body in NON_INVOICE_EDITS]
        for name, response in [("settings", settings)] + edits:
            with self.subTest(target=name):
                self.assertEqual(403, response.status_code,
                                 "manage_invoice granted a non-invoice edit")
        self.assertEqual([], calls)


class UnassignedPermissionTests(unittest.TestCase):
    """D. The host has not granted it yet: everything invoice stays shut."""

    def test_without_the_permission_there_is_no_fallback_at_all(self):
        client, calls = api(("finance.view", "finance.edit", "finance_report.view",
                             "finance_report.export"))
        with client:
            for method, path, body in MUTATIONS:
                with self.subTest(route="%s %s" % (method.upper(), path)):
                    calls.clear()
                    self.assertEqual(403, send(client, method, path, body).status_code)
                    self.assertEqual([], calls)

    def test_no_role_name_is_a_way_in(self):
        """Least of all the administrator-sounding one."""
        for role in ("org_chief", "bambo_admin", "project_manager", "support",
                     "finance_expert"):
            client, calls = api(VIEW_EDIT, organization_role=role)
            with client:
                for method, path, body in MUTATIONS[:4]:
                    with self.subTest(role=role, route=path):
                        calls.clear()
                        self.assertEqual(403, send(client, method, path, body).status_code)
                        self.assertEqual([], calls)
                self.assertEqual(404, send(client, "get", CONTENT).status_code)


class ScopeTests(unittest.TestCase):
    """F. The permission never travels across a tenant boundary."""

    def test_another_project_is_refused_even_holding_the_permission(self):
        """The permission is held in one project; the request names a different one."""
        client, calls = api(VIEW_MANAGE)
        with client:
            for method, path, body in MUTATIONS:
                with self.subTest(route="%s %s" % (method.upper(), path)):
                    calls.clear()
                    response = send(client, method, path, body, base=OTHER_BASE)
                    self.assertEqual(403, response.status_code)
                    self.assertEqual([], calls)

    def test_another_organization_is_refused(self):
        client, calls = api(VIEW_MANAGE, organization_id=OTHER_ORG)
        with client:
            method, path, body = MUTATIONS[0]
            response = send(client, method, path, body)
        self.assertEqual(403, response.status_code)
        self.assertEqual([], calls)

    def test_a_file_belonging_to_another_project_leaks_no_content(self):
        client, calls = api(VIEW_MANAGE)
        with client:
            response = send(client, "get", CONTENT, base=OTHER_BASE)
        self.assertEqual(404, response.status_code)
        self.assertNotIn(ORIGINAL_BYTES, response.content)
        self.assertEqual([], calls)


class ReportPermissionTests(unittest.TestCase):
    """H. The report tiers are untouched by any of this."""

    def test_view_export_and_issue_stay_where_they_were(self):
        client, _calls = api(("finance.view", "finance.manage_invoice"))
        with client:
            live = client.get(BASE + "/reports/live?reportingDate=2026-08-08")
            issue = client.post(BASE + "/report-snapshots",
                                json={"reportingDate": "2026-08-08"})
        self.assertEqual(403, live.status_code, "manage_invoice granted report reading")
        self.assertEqual(403, issue.status_code, "manage_invoice granted report issuing")

    def test_a_report_reader_still_cannot_issue(self):
        """`finance_report.issue` is not registered by Core, so this must fail closed."""
        client, _calls = api(("finance.view", "finance_report.view", "finance_report.export"))
        with client:
            live = client.get(BASE + "/reports/live?reportingDate=2026-08-08")
            issue = client.post(BASE + "/report-snapshots",
                                json={"reportingDate": "2026-08-08"})
        self.assertEqual(409, live.status_code, "a report reader was refused a report")
        self.assertEqual(403, issue.status_code, "issuing did not fail closed")


class ExtractionConfirmationTests(unittest.TestCase):
    """E. Two different confirmations, two different rules.

    Confirming an INVOICE is no longer personal: a colleague holding
    `finance.manage_invoice` may confirm one somebody else submitted, which is what
    `test_invoices.py` asserts at the service level.

    Confirming an EXTRACTION still is personal, and deliberately: FR-063 says only the
    person who uploaded the photograph may accept what the model read out of it, because
    they are the only one who can compare it against the paper in their hand. The permission
    is necessary and not sufficient -- `test_extractions.py` holds the uploader half.
    """

    def test_the_route_gate_and_the_uploader_rule_are_both_present(self):
        router = (BACKEND_ROOT / "app" / "finance" / "router.py").read_text(encoding="utf-8")
        confirm = router[router.index('@router.post("/extractions/{draftId}/confirm"'):]
        confirm = confirm[:confirm.index("@router", 10)]
        self.assertIn('"finance.manage_invoice"', confirm)

        service = (BACKEND_ROOT / "app" / "finance" / "services" / "extractions.py").read_text(
            encoding="utf-8")
        body = service[service.index("async def confirm(self, scope, draft_id, command):"):]
        self.assertIn("only the uploader can confirm this extraction", body[:600])

    def test_holding_the_permission_does_not_skip_the_uploader_rule(self):
        """The gate lets the request through; the service still refuses a stranger."""
        import asyncio
        from app.finance.security.guards import FinanceScope
        from app.finance.services.extractions import ExtractionForbidden

        stranger = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2")
        draft = SimpleNamespace(submitted_by=ACTOR, review_status="awaitingReview",
                                version=1, file=SimpleNamespace(invoice_id=None))

        class Service:
            invoices = object()

            async def get(self, _scope, _draft_id):
                return draft

        from app.finance.services.extractions import FinanceExtractionService
        confirm = FinanceExtractionService.confirm
        scope = FinanceScope(ORG, PROJECT, stranger,
                             permission_codes=("finance.view", "finance.manage_invoice"))
        with self.assertRaises(ExtractionForbidden):
            asyncio.run(confirm(Service(), scope, DRAFT_ID, SimpleNamespace()))


if __name__ == "__main__":
    unittest.main()
