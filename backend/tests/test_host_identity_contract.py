# -*- coding: utf-8 -*-
"""What any future host identity implementation has to satisfy.

WHY THIS EXISTS BEFORE THE IMPLEMENTATION DOES
The BAMBO integration kit excludes the session mechanism on purpose -- storage, token
format, cookie value and lookup are all the host's to decide. So Finance cannot test the
host's implementation, and must not invent one to test against.

What Finance *can* do is pin the seam: state exactly what `identity(request)` must return,
what happens when it returns something else, and prove that the chain behind it already
works. Then the host writes one function, runs these tests, and knows whether it is done.

WHAT THE DOUBLES STAND FOR
The only thing faked here is the trusted identity -- the one thing the host owns. Everything
downstream is the real `coreint` code reading real SQL shapes through a recording
connection, so a passing test says something about the code that will actually run.

Nothing here implements authentication. There is no cookie, no token, no header, and no
fallback. A test that needed one would be testing a mechanism this repository is not
allowed to choose.
"""

import inspect
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from fastapi import HTTPException

from app.finance.security.guards import authorize_finance_request
from coreint.security import (CoreAuthContextAssembler, CoreRbacPermissionAuthorizer,
                              CoreScopeAuthorizer)

ORG = UUID("11111111-1111-4111-8111-111111111111")
OTHER_ORG = UUID("22222222-2222-4222-8222-222222222222")
USER = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
PROJECT = "sample_site_01"

#: The four permissions Core actually defines. `finance_report.issue` is deliberately not
#: among them -- see docs/CORE_PERMISSION_REQUIREMENTS_FA.md.
CORE_PERMISSIONS = ("finance.view", "finance.edit",
                    "finance_report.view", "finance_report.export")


# --------------------------------------------------------------------------- test doubles
class Cursor:
    def __init__(self, answer, log):
        self._answer, self._log, self._rows = answer, log, []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, sql, params=None):
        self._log.append((str(sql), params or {}))
        self._rows = self._answer(str(sql), params or {})

    async def fetchall(self):
        return list(self._rows)

    async def fetchone(self):
        return self._rows[0] if self._rows else None


class CoreDouble:
    """Stands in for the Core database, answering by query shape.

    Not a stub of `coreint`: the real queries run against it, so the WHERE clauses and the
    deny-wins arithmetic are exercised rather than assumed.
    """

    def __init__(self, *, member_of=(ORG,), in_projects=(PROJECT,),
                 roles=("org_chief",), granted=CORE_PERMISSIONS, denied=()):
        self.member_of, self.in_projects = set(member_of), set(in_projects)
        self.roles, self.granted, self.denied = list(roles), set(granted), set(denied)
        self.log = []

    def cursor(self, **_kwargs):
        return Cursor(self._answer, self.log)

    def _answer(self, sql, params):
        if "FROM organization_memberships" in sql and "SELECT 1" in sql:
            return [{"?column?": 1}] if UUID(params["organization_id"]) in self.member_of else []
        if "FROM project_memberships AS membership" in sql:
            inside = (UUID(params["organization_id"]) in self.member_of
                      and params["project_id"] in self.in_projects)
            return [{"?column?": 1}] if inside else []
        if "WITH granted AS" in sql:
            # The real query already applied the scope predicates; the double answers for
            # the scope it was built for and nothing else.
            if UUID(params["organization_id"]) not in self.member_of:
                return []
            return [{"code": c} for c in sorted(self.granted - self.denied)]
        if "project_id IS NULL" in sql:
            return [{"code": r} for r in self.roles] if UUID(
                params["organization_id"]) in self.member_of else []
        if "assignment.project_id = %(project_id)s" in sql:
            return []
        if "organization_memberships" in sql and "project_memberships" in sql:
            return [{"organization_role": "org_admin", "project_role": "editor"}]
        return []


def identity_returning(*values):
    async def identity(_request):
        return values
    return identity


def identity_raising(error):
    async def identity(_request):
        raise error
    return identity


REQUEST = SimpleNamespace(headers={}, path_params={})


# --------------------------------------------------------------------------- the seam
class IdentitySeamTests(unittest.IsolatedAsyncioTestCase):
    """The shape `identity(request)` must have, and what happens when it does not."""

    def assembler(self, identity, core=None):
        return CoreAuthContextAssembler(core or CoreDouble(), identity)

    async def test_a_valid_identity_produces_a_finance_context(self):
        context = await self.assembler(identity_returning(USER, ORG, PROJECT)).current(REQUEST)
        self.assertEqual(USER, context.user_id)
        self.assertEqual(ORG, context.organization_id)
        self.assertEqual(PROJECT, context.project_id)
        self.assertEqual("Asia/Tehran", context.timezone)

    async def test_the_seam_takes_the_request_and_returns_three_values(self):
        """Documented here so the host has one place to read the signature from."""
        signature = inspect.signature(CoreAuthContextAssembler.__init__)
        self.assertIn("identity", signature.parameters)
        current = inspect.signature(CoreAuthContextAssembler.current)
        self.assertIn("request", current.parameters)
        self.assertTrue(inspect.iscoroutinefunction(CoreAuthContextAssembler.current))

    async def test_a_missing_identity_is_refused(self):
        """No fallback user. An identity provider that returns nothing means nobody is
        signed in, and Finance has no way to guess who.
        """
        for values in ((None, ORG, PROJECT), (USER, None, PROJECT), (USER, ORG, None)):
            with self.subTest(values=values):
                with self.assertRaises(Exception):
                    await self.assembler(identity_returning(*values)).current(REQUEST)

    async def test_a_malformed_user_identifier_is_refused(self):
        for bad in ("not-a-uuid", "", 12345, "aaaaaaaa-aaaa"):
            with self.subTest(bad=bad):
                with self.assertRaises(Exception):
                    await self.assembler(identity_returning(bad, ORG, PROJECT)).current(REQUEST)

    async def test_a_malformed_organization_identifier_is_refused(self):
        for bad in ("not-a-uuid", "", 0):
            with self.subTest(bad=bad):
                with self.assertRaises(Exception):
                    await self.assembler(identity_returning(USER, bad, PROJECT)).current(REQUEST)

    async def test_a_project_identifier_outside_the_contract_is_refused(self):
        """`^[A-Za-z0-9_-]+$`. The project id reaches SQL and route paths, so its shape is
        part of the contract rather than a convention.
        """
        for bad in ("", "has space", "semi;colon", "quote'mark", "../traversal", "a/b"):
            with self.subTest(bad=bad):
                with self.assertRaises(Exception):
                    await self.assembler(identity_returning(USER, ORG, bad)).current(REQUEST)

    async def test_an_identity_provider_that_raises_fails_closed(self):
        """The host raising is how it says "no valid session". It must not become a
        context: an exception that got swallowed here would be an anonymous request wearing
        somebody's scope.
        """
        for error in (RuntimeError("no session"), ValueError("expired"), KeyError("cookie")):
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(type(error)):
                    await self.assembler(identity_raising(error)).current(REQUEST)

    async def test_nothing_on_the_request_can_replace_the_host_identity(self):
        """Headers, query and body are inputs, never authorization.

        The assembler is handed a request it does not read; only `identity` does. This
        passes a request carrying hostile values and proves none of them reach the context.
        """
        hostile = SimpleNamespace(
            headers={"X-Mock-User": str(uuid4()), "X-User-Id": str(uuid4()),
                     "Authorization": "Bearer forged", "X-Organization-Id": str(OTHER_ORG)},
            query_params={"organization_id": str(OTHER_ORG)},
            path_params={"projectId": "other_project"})
        context = await self.assembler(identity_returning(USER, ORG, PROJECT)).current(hostile)
        self.assertEqual(USER, context.user_id)
        self.assertEqual(ORG, context.organization_id)
        self.assertEqual(PROJECT, context.project_id)


class NoMockPathInProductionTests(unittest.TestCase):
    """The two shortcuts the kit's own checklist forbids."""

    def deployable(self):
        for root in ("app", "coreint"):
            for path in (BACKEND_ROOT / root).rglob("*.py"):
                if "__pycache__" not in path.parts:
                    yield path

    def test_no_mock_header_exists_in_deployable_code(self):
        for path in self.deployable():
            text = path.read_text(encoding="utf-8")
            for header in ("X-Mock-User", "X-Demo-User"):
                with self.subTest(path=path.name, header=header):
                    self.assertNotIn(header, text)

    def test_the_development_provider_is_not_reachable_from_deployable_code(self):
        import ast
        for path in self.deployable():
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                         else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
                for name in names:
                    with self.subTest(path=path.name, name=name):
                        self.assertNotEqual("devhost", name.split(".")[0])

    def test_the_assembler_has_no_default_identity(self):
        """A default would be an anonymous fallback with a name."""
        signature = inspect.signature(CoreAuthContextAssembler.__init__)
        self.assertIs(inspect.Parameter.empty, signature.parameters["identity"].default)


# --------------------------------------------------------------------------- the chain
class AuthorizationChainTests(unittest.IsolatedAsyncioTestCase):
    """Host identity -> membership -> role -> permissions -> gate.

    Only the first link is a double. The rest is the code that will run in production.
    """

    async def context(self, core, user=USER, organization=ORG, project=PROJECT):
        return await CoreAuthContextAssembler(
            core, identity_returning(user, organization, project)).current(REQUEST)

    async def test_a_member_passes_both_scope_gates(self):
        core = CoreDouble()
        context = await self.context(core)
        gate = CoreScopeAuthorizer(core)
        await gate.require_organization(context, str(ORG))
        await gate.require_project(context, str(ORG), PROJECT)

    async def test_another_organization_is_refused(self):
        core = CoreDouble(member_of=(OTHER_ORG,))
        context = await self.context(core, organization=OTHER_ORG)
        gate = CoreScopeAuthorizer(core)
        with self.assertRaises(Exception) as caught:
            await gate.require_organization(context, str(ORG))
        self.assertEqual(403, caught.exception.status_code)

    async def test_another_project_in_the_same_organization_is_refused(self):
        core = CoreDouble(in_projects=("someone_elses_project",))
        context = await self.context(core)
        with self.assertRaises(Exception) as caught:
            await CoreScopeAuthorizer(core).require_project(context, str(ORG), PROJECT)
        self.assertEqual(403, caught.exception.status_code)

    async def test_a_role_held_in_another_organization_grants_nothing_here(self):
        core = CoreDouble(member_of=(OTHER_ORG,))
        context = await self.context(core, organization=OTHER_ORG)
        with self.assertRaises(Exception):
            await CoreScopeAuthorizer(core).require_organization(context, str(ORG))

    async def test_org_chief_resolves_from_the_rbac_role_code(self):
        """Not from `organization_memberships.role`, which is a separate, coarser
        vocabulary. The settings policy compares against this exact string.
        """
        context = await self.context(CoreDouble(roles=("org_chief",)))
        self.assertEqual("org_chief", context.organization_role)

    async def test_a_role_grant_reaches_the_permission_gate(self):
        core = CoreDouble()
        context = await self.context(core)
        await CoreRbacPermissionAuthorizer(core).require(context, "finance.edit")

    async def test_an_explicit_denial_beats_the_role_grant(self):
        core = CoreDouble(denied={"finance.edit"})
        context = await self.context(core)
        self.assertIn("finance.view", context.permission_codes)
        self.assertNotIn("finance.edit", context.permission_codes)
        with self.assertRaises(Exception) as caught:
            await CoreRbacPermissionAuthorizer(core).require(context, "finance.edit")
        self.assertEqual(403, caught.exception.status_code)

    async def test_issuing_a_report_stays_denied_because_core_has_no_such_permission(self):
        """The kit lists finance_report.issue as proposed, not existing, and records "no
        existing decision" for a fallback. So this is not a gap to work around.
        """
        core = CoreDouble()
        context = await self.context(core)
        self.assertNotIn("finance_report.issue", context.permission_codes)
        with self.assertRaises(Exception) as caught:
            await CoreRbacPermissionAuthorizer(core).require(context, "finance_report.issue")
        self.assertEqual(403, caught.exception.status_code)
        self.assertIn("finance_report.issue", caught.exception.detail)

    async def test_the_permission_gate_re_reads_core_rather_than_trusting_the_context(self):
        """Two ports, two independent gates. A context is assembled once; the gate asks the
        database, so a permission revoked in Core stops working without waiting for a
        session to expire.
        """
        core = CoreDouble()
        context = await self.context(core)
        core.granted = set()                       # revoked after the context was built
        with self.assertRaises(Exception):
            await CoreRbacPermissionAuthorizer(core).require(context, "finance.view")


class SessionEndedIsNotPermissionDeniedTests(unittest.IsolatedAsyncioTestCase):
    """401 and 403 are different answers, and the frontend now acts on the difference.

    The host team settled it: "if the session has expired or is not valid, the API must
    return 401, not 302." The frontend reads a 401 as "your session ended" and replaces the
    whole page with a sign-in prompt. So a 403 arriving as a 401 would throw a colleague
    who merely lacks a permission out to the login screen, and a 401 arriving as a 403
    would show "no access" to somebody who is simply logged out.

    WHAT THIS MODULE OWES, AND WHAT IT DOES NOT
    It does not authenticate. `AuthContextProvider.current` is the host's one function, and
    what it raises when there is no session is the host's decision. What this module owes is
    to carry that answer out unchanged -- never to catch it, never to turn it into a
    permission refusal, and never to answer a redirect of its own.
    """

    def gates(self, auth):
        """The four gates with a given auth provider; the rest allow everything."""

        class AllowScope:
            async def require_organization(self, *_a, **_k):
                return None

            async def require_project(self, *_a, **_k):
                return None

        class AllowPermission:
            async def require(self, *_a, **_k):
                return None

        return auth, AllowScope(), AllowPermission()

    async def test_no_session_reaches_the_caller_as_401_and_is_not_caught(self):
        class NoSession:
            async def current(self, _request):
                raise HTTPException(401, "session has expired")

        auth, scope, permission = self.gates(NoSession())
        with self.assertRaises(HTTPException) as refused:
            await authorize_finance_request(object(), PROJECT, "finance.view",
                                            auth, scope, permission)
        self.assertEqual(401, refused.exception.status_code)

    async def test_a_valid_session_without_the_permission_is_403(self):
        class Session:
            async def current(self, _request):
                return SimpleNamespace(
                    organization_id=ORG, project_id=PROJECT, user_id=USER,
                    locale="fa", organization_role="member",
                    permission_codes=("finance.view",))

        class RefuseOnPermission:
            async def require(self, _context, code):
                raise HTTPException(403, "permission %s is required" % code)

        class AllowScope:
            async def require_organization(self, *_a, **_k):
                return None

            async def require_project(self, *_a, **_k):
                return None

        with self.assertRaises(HTTPException) as refused:
            await authorize_finance_request(object(), PROJECT, "finance.manage_invoice",
                                            Session(), AllowScope(), RefuseOnPermission())
        self.assertEqual(403, refused.exception.status_code)
        self.assertIn("finance.manage_invoice", str(refused.exception.detail))

    async def test_the_authentication_gate_runs_before_the_permission_gate(self):
        """A logged-out caller must not be told which permission they lack.

        Order is the whole guarantee: asking the permission first would answer 403 to
        somebody with no session at all, and the frontend would show "no access" instead
        of a sign-in prompt.
        """
        asked = []

        class NoSession:
            async def current(self, _request):
                asked.append("auth")
                raise HTTPException(401, "session has expired")

        class RecordingPermission:
            async def require(self, *_a, **_k):
                asked.append("permission")

        class AllowScope:
            async def require_organization(self, *_a, **_k):
                return None

            async def require_project(self, *_a, **_k):
                return None

        with self.assertRaises(HTTPException):
            await authorize_finance_request(object(), PROJECT, "finance.view",
                                            NoSession(), AllowScope(), RecordingPermission())
        self.assertEqual(["auth"], asked, "nothing may be asked after authentication fails")

    def test_the_module_never_answers_a_redirect(self):
        """302 is the answer the host team ruled out, and nothing here may produce one."""
        import re
        redirect = re.compile(r"RedirectResponse|status_code\s*=\s*30[0-9]|HTTPException\(\s*30[0-9]")
        for root in ("app", "coreint"):
            for path in (BACKEND_ROOT / root).rglob("*.py"):
                if "__pycache__" in path.parts:
                    continue
                with self.subTest(path=str(path.relative_to(BACKEND_ROOT))):
                    self.assertIsNone(redirect.search(path.read_text(encoding="utf-8")))

    #: The ONE file allowed to read a request header, and it is named here so the
    #: exception has to be argued for rather than acquired.
    #:
    #: A service key is a deliberate, approved departure from "Finance authenticates
    #: nobody": n8n triggers the daily price import and is not a person, so it presents a
    #: shared secret on one route instead of carrying a session it cannot have. What the
    #: exception must NOT become is a second identity system -- so the header it reads is
    #: its own, `Authorization` stays forbidden everywhere including here, and every other
    #: file in `app/` and `coreint/` still reads no header at all.
    HEADER_READING_ALLOWED = ("app/finance/security/service_key.py",)

    def test_the_session_is_the_hosts_cookie_and_this_module_reads_no_header(self):
        """Cookie-based, with no Authorization header and no CSRF token -- both confirmed
        by the host. `app/` and `coreint/` read no request header, so none can be expected
        by accident, with one named exception above.
        """
        for root in ("app", "coreint"):
            for path in (BACKEND_ROOT / root).rglob("*.py"):
                if "__pycache__" in path.parts:
                    continue
                relative = path.relative_to(BACKEND_ROOT).as_posix()
                text = path.read_text(encoding="utf-8")
                with self.subTest(path=relative):
                    if relative not in self.HEADER_READING_ALLOWED:
                        self.assertNotIn("request.headers", text)
                    # No exception, for any file. The host's session travels in its own
                    # cookie; a Finance module that read `Authorization` would be a second
                    # place identity could come from, which is the thing being prevented.
                    self.assertNotIn("Authorization", text)
                    self.assertNotIn("X-CSRF", text)

    def test_the_header_exception_is_exactly_one_file(self):
        """A carve-out that grows is a rule that was abandoned without anybody saying so."""
        self.assertEqual(1, len(self.HEADER_READING_ALLOWED))
        allowed = BACKEND_ROOT / self.HEADER_READING_ALLOWED[0]
        self.assertTrue(allowed.is_file(), "the named exception must exist")
        self.assertIn("X-FINANCE-SERVICE-KEY", allowed.read_text(encoding="utf-8"),
                      "the exception exists for the service key and nothing else")


if __name__ == "__main__":
    unittest.main()
