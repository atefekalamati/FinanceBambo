# -*- coding: utf-8 -*-
"""Every route reaches the four-gate guard, and asks for the right permission.

WHY A TEST AND NOT A REVIEW
A route is added by writing one decorated function. Nothing in the framework requires that
function to authorize anything, so an unguarded endpoint looks exactly like a guarded one
until somebody reads it. Reviews catch that until the day they do not.

WHY IT FOLLOWS DELEGATION
The obvious version of this test -- look for a permission string inside each handler --
reports four false failures on this router, because the import endpoints are one-line
delegations to a shared helper that does the authorizing. A check that cannot tell a
delegation from an omission is worse than none: it trains the reader to ignore it. So this
resolves calls to module-level helpers and reports what the route actually reaches.
"""

import ast
import re
import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

ROUTER = BACKEND_ROOT / "app" / "finance" / "router.py"

#: The complete permission vocabulary Finance may ask Core for. A route naming anything
#: outside this list is either a typo or a permission nobody has agreed to create.
KNOWN_PERMISSIONS = frozenset({
    "finance.view", "finance.edit",
    "finance_report.view", "finance_report.issue", "finance_report.export",
})

#: Permissions Core does not currently define. Routes needing them must fail closed rather
#: than fall back to a weaker one -- see docs/CORE_PERMISSION_REQUIREMENTS_FA.md.
ABSENT_IN_CORE = frozenset({"finance_report.issue"})

#: The function every gated route must reach, however many helpers deep.
GUARD = "authorize_finance_request"

#: A module that finishes a WHERE clause outside the SQL literal, by either syntax.
COMPOSES = re.compile(r'{where}|WHERE\s*"\s*\+\s*where|" AND ".join\(clauses\)')


class RouterModel:
    """Routes, the helpers they call, and the permissions those helpers name."""

    def __init__(self):
        source = ROUTER.read_text(encoding="utf-8")
        self.tree = ast.parse(source)
        self.lines = source.split("\n")
        self.functions = {node.name: node for node in ast.walk(self.tree)
                          if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}

    def body(self, node):
        return "\n".join(self.lines[node.lineno - 1: node.end_lineno])

    def resolve(self, node, seen=None):
        """Permissions and guard reachability for a handler, following local calls.

        Returns `(permissions, reaches_guard, dynamic)`. `dynamic` marks a route whose
        permission is decided at request time from the caller's role -- the settings policy
        -- where a literal string would be the wrong thing to assert.
        """
        seen = seen or set()
        if node.name in seen:
            return set(), False, False
        seen.add(node.name)

        text = self.body(node)
        permissions = set(re.findall(r'"(finance[a-z_]*\.[a-z_]+)"', text))
        reaches = GUARD in text
        dynamic = "settings_edit_permission" in text

        for called in ast.walk(node):
            if not isinstance(called, ast.Call):
                continue
            name = (called.func.id if isinstance(called.func, ast.Name)
                    else called.func.attr if isinstance(called.func, ast.Attribute) else None)
            target = self.functions.get(name)
            if target is not None and target is not node:
                more, deeper, deeper_dynamic = self.resolve(target, seen)
                permissions |= more
                reaches = reaches or deeper
                dynamic = dynamic or deeper_dynamic
        return permissions, reaches, dynamic

    def routes(self):
        for node in ast.walk(self.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if (isinstance(decorator, ast.Call)
                        and isinstance(decorator.func, ast.Attribute)
                        and isinstance(decorator.func.value, ast.Name)
                        and decorator.func.value.id == "router"
                        and decorator.args):
                    method = decorator.func.attr.upper()
                    path = ast.literal_eval(decorator.args[0])
                    permissions, reaches, dynamic = self.resolve(node)
                    yield method, path, permissions, reaches, dynamic


MODEL = RouterModel()
ROUTES = list(MODEL.routes())


class RouteGateTests(unittest.TestCase):
    def test_the_router_actually_has_routes(self):
        """A parser that silently found nothing would make every test below vacuous."""
        self.assertGreaterEqual(len(ROUTES), 50)

    def test_every_route_reaches_the_authorization_guard(self):
        for method, path, _permissions, reaches, _dynamic in ROUTES:
            with self.subTest(route=f"{method} {path}"):
                self.assertTrue(reaches, "route does not reach authorize_finance_request")

    def test_every_route_names_a_permission(self):
        for method, path, permissions, _reaches, dynamic in ROUTES:
            with self.subTest(route=f"{method} {path}"):
                self.assertTrue(permissions or dynamic, "route names no permission")

    def test_no_route_invents_a_permission_code(self):
        """Anything outside the agreed vocabulary is a typo or an unapproved permission.

        A typo is the dangerous case: Core would not grant a code it does not have, so the
        route would fail closed and look like a configuration problem for as long as it took
        somebody to compare two strings.
        """
        for method, path, permissions, _reaches, _dynamic in ROUTES:
            for code in permissions:
                with self.subTest(route=f"{method} {path}", code=code):
                    self.assertIn(code, KNOWN_PERMISSIONS)

    def test_reading_never_costs_more_than_viewing_and_writing_never_less_than_editing(self):
        """The tier has to match the verb, or the gate is decorative.

        A POST asking only for `finance.view` would let a read-only member write; a GET
        demanding `finance.edit` would hide data from someone entitled to see it. Both are
        the kind of mistake that survives review because the line still *has* a permission
        on it.
        """
        read_only = {"finance.view", "finance_report.view", "finance_report.export"}
        for method, path, permissions, _reaches, dynamic in ROUTES:
            if dynamic:
                continue
            with self.subTest(route=f"{method} {path}"):
                if method == "GET":
                    self.assertTrue(permissions <= read_only,
                                    f"a read asks for a write permission: {sorted(permissions)}")
                else:
                    self.assertFalse(permissions <= read_only,
                                     f"a write asks only for read permissions: {sorted(permissions)}")

    def test_issuing_a_report_is_the_only_route_needing_a_permission_core_lacks(self):
        """Fail-closed, and narrowly. If a second route started demanding an absent
        permission, that is a new production blocker and should be noticed here first.
        """
        blocked = {f"{m} {p}" for m, p, permissions, _r, _d in ROUTES
                   if permissions & ABSENT_IN_CORE}
        self.assertEqual({"POST /report-snapshots"}, blocked)

    def test_the_settings_policy_is_the_only_dynamic_permission(self):
        dynamic = {f"{m} {p}" for m, p, _perm, _r, d in ROUTES if d}
        self.assertEqual({"PATCH /settings"}, dynamic)


class GuardShapeTests(unittest.TestCase):
    """What the guard itself must do, asserted where it is defined."""

    GUARD_SOURCE = (BACKEND_ROOT / "app" / "finance" / "security" / "guards.py").read_text(
        encoding="utf-8")

    def test_the_guard_applies_all_four_gates_in_order(self):
        """Order matters: a permission check that ran before the scope check would answer
        "forbidden" for a project the caller may not even know exists, which is a different
        statement from "not found" and leaks that it exists.
        """
        source = self.GUARD_SOURCE
        positions = [source.index(step) for step in (
            "auth_provider.current(request)",
            "scope_authorizer.require_organization",
            "scope_authorizer.require_project",
            "permission_authorizer.require",
        )]
        self.assertEqual(positions, sorted(positions))

    def test_the_scope_is_built_from_the_context_not_from_the_request(self):
        """The organization can only come from the authenticated context.

        Taking it from a path or body parameter is the whole IDOR class: the caller would
        name the tenant they wanted to read.
        """
        source = self.GUARD_SOURCE
        self.assertIn("organization_id = str(context.organization_id)", source)
        self.assertIn("organization_id=context.organization_id", source)

    def test_a_record_outside_the_scope_is_concealed_rather_than_refused(self):
        """404, not 403. Answering "forbidden" confirms the row exists."""
        source = self.GUARD_SOURCE
        self.assertIn("raise FinanceNotFound()", source)
        self.assertIn('str(record.get("organization_id")) != str(scope.organization_id)', source)
        self.assertIn('record.get("project_id") != scope.project_id', source)

    def test_the_project_id_never_reaches_sql_unvalidated(self):
        from app.finance.security.context import AuthContext
        field = AuthContext.model_fields["project_id"]
        pattern = next((m.pattern for m in field.metadata if hasattr(m, "pattern")), None)
        self.assertEqual(r"^[A-Za-z0-9_-]+$", pattern)


class ScopedQueryTests(unittest.TestCase):
    """Every repository statement filters on both tenant keys.

    One key is not enough. `project_id` is text the host chooses and could repeat across
    organizations, so an organization filter alone returns every project in it and a project
    filter alone could match somebody else's project of the same name.

    Two ways a query gets scoped, and both are accepted because both are used:

      * the tenant keys are written into the SQL literally;
      * the WHERE clause is composed from a list that is *seeded* with them before any
        optional filter is appended, which is what the list endpoints do.

    The second is the one a naive check gets wrong -- it sees `WHERE {where}` and reports a
    missing scope on a query that is scoped. So a composed statement is verified against the
    builder that produced it instead.
    """

    TABLES = re.compile(
        r"\b(finance_[a-z_]+|estimate_lines|estimate_revisions|price_versions|invoices|"
        r"invoice_lines|progress_snapshot_refs|progress_overrides|report_snapshots|"
        r"unit_conversions|extraction_drafts)\b")
    STATEMENT = re.compile(r"\b(SELECT|UPDATE|DELETE\s+FROM|INSERT\s+INTO)\b", re.I)

    #: How a composed WHERE has to start: both tenant keys, before anything optional.
    #: The alias prefix is permitted because a joined query qualifies its columns.
    SEEDED = re.compile(r'\[\s*"(?:[a-z]\.)?organization_id=%s"\s*,\s*"(?:[a-z]\.)?project_id=%s"')

    def repositories(self):
        for path in sorted((BACKEND_ROOT / "app" / "finance" / "repositories").glob("*.py")):
            if path.name != "ports.py" and "__pycache__" not in path.parts:
                yield path

    def statements(self, tree):
        """Every SQL string in the module, whole, with whether it was composed.

        Taken from the syntax tree rather than by matching quotes: a regex over the source
        chops multi-line SQL at the first embedded quote and then reports the fragments as
        separate, unscoped statements.
        """
        # An f-string's literal halves are Constant nodes inside the JoinedStr, and
        # `ast.walk` visits them on their own. Yielding those as well reports each
        # fragment of a composed statement as a separate query with no scope in it --
        # which is how the first version of this test produced eight failures about SQL
        # that was correctly scoped all along.
        inside_fstring = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                inside_fstring.update(id(part) for part in node.values)
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                text = "".join(part.value for part in node.values
                               if isinstance(part, ast.Constant)
                               and isinstance(part.value, str))
                yield text, True
            elif (isinstance(node, ast.Constant) and isinstance(node.value, str)
                  and id(node) not in inside_fstring):
                yield node.value, False

    def test_every_statement_naming_a_finance_table_is_scoped_to_one_tenant(self):
        unscoped, checked, composed_seen = [], 0, 0
        for path in self.repositories():
            source = path.read_text(encoding="utf-8")
            seeded = bool(self.SEEDED.search(source))
            for sql, composed in self.statements(ast.parse(source)):
                if not (self.TABLES.search(sql) and self.STATEMENT.search(sql)):
                    continue
                checked += 1
                # A statement ending in WHERE is completed by concatenation rather than
                # by an f-string. Both are composition; only the syntax differs, and a
                # check that recognised one but not the other would report the list
                # endpoints in `invoices.py` as unscoped when they are seeded correctly.
                composed = composed or bool(re.search(r"WHERE\s*$", sql))
                if composed:
                    composed_seen += 1
                    if not seeded:
                        unscoped.append(f"{path.name}: composed WHERE with no seeded scope")
                elif "organization_id" not in sql:
                    unscoped.append(f"{path.name}: {' '.join(sql.split())[:100]}")
        self.assertEqual([], sorted(set(unscoped)), "statements that name no organization")
        # Guards against the extraction quietly finding nothing, and against the composed
        # branch being dead code that never proves anything.
        self.assertGreater(checked, 60, "almost no SQL was examined")
        self.assertGreater(composed_seen, 0, "the composed-WHERE branch never ran")

    def test_a_composed_where_seeds_both_keys_before_any_optional_filter(self):
        """Asserted on the builder, because that is where the ordering lives.

        Appending the tenant keys after the optional filters would still work; seeding with
        them means a filter cannot be added *before* the scope by someone editing quickly.
        """
        builders = [p for p in self.repositories()
                    if COMPOSES.search(p.read_text(encoding="utf-8"))]
        self.assertGreater(len(builders), 0)
        for path in builders:
            with self.subTest(path=path.name):
                # A boolean rather than assertRegex: the failure message would otherwise
                # print the whole repository module, which buries the one line at fault.
                self.assertTrue(
                    self.SEEDED.search(path.read_text(encoding="utf-8")),
                    "the WHERE is composed without seeding both tenant keys first")

    def test_no_repository_builds_sql_from_a_value(self):
        """Clause fragments may be interpolated; values never may.

        Every f-string in these modules must interpolate only a WHERE built from fixed
        fragments -- anything else is a value reaching the statement text.
        """
        for path in self.repositories():
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.JoinedStr):
                    continue
                text = "".join(part.value for part in node.values
                               if isinstance(part, ast.Constant) and isinstance(part.value, str))
                if not self.STATEMENT.search(text):
                    continue
                names = [ast.unparse(part.value) for part in node.values
                         if isinstance(part, ast.FormattedValue)]
                with self.subTest(path=path.name, sql=" ".join(text.split())[:60]):
                    self.assertTrue(set(names) <= {"where"},
                                    f"SQL interpolates {names}, not just a composed WHERE")


if __name__ == "__main__":
    unittest.main()
