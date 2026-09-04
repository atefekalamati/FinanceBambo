"""What the Core alignment work must guarantee.

Phase 1 found that `progress_snapshot_refs` was written only by the development seed. With
seed data correctly forbidden in production, that table stayed empty, every live report
answered 404, and no report could ever be issued -- the whole reporting half of Finance was
unreachable on a real database. These tests pin the fix and the boundaries it must respect.

The boundary that matters most: Finance stores Core *references*, never Core *records*, and
never a physical foreign key to a Core table. Core deletes MSP snapshots when a project is
deleted, so a RESTRICT key would block Core and a CASCADE key would destroy financial
history. Neither is acceptable, so validation lives at the adapter instead.
"""

import importlib.util
import re
import sys
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.finance.adapters.ports import supports_current_snapshot
from app.finance.domain.progress import (HostReferenceInvalid, ProgressReference,
                                         host_reference)
from app.finance.schemas.progress import ProgressSnapshotResponse
from app.finance.services.progress import ProgressService
from app.finance.services.reports import FinanceLiveReportService

ORG = UUID("11111111-1111-4111-8111-111111111111")
PROJECT = "sample_site_01"
ACTOR = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
SCOPE = SimpleNamespace(organization_id=ORG, project_id=PROJECT, actor_user_id=ACTOR)
AT = datetime(2026, 8, 2, tzinfo=timezone.utc)


def header(host_snapshot_id=9001, host_file_version_id=1001, organization_id=ORG,
           project_id=PROJECT):
    """A host feed header of the shape the adapter contract now carries."""
    return {"organizationId": str(organization_id), "projectId": project_id,
            "progressSnapshotId": str(UUID(int=7)), "hostSnapshotId": host_snapshot_id,
            "hostFileVersionId": host_file_version_id,
            "sourceFileNameSafe": "plan.mpp", "reportingDate": "2026-08-02",
            "status": "ready", "importedBy": str(ACTOR), "importedAt": "2026-08-02T00:00:00Z"}


class RecordingRepository:
    """Stands in for the database, and counts what would have been written.

    The uniqueness the real table enforces is modelled here by keying on
    `(organization_id, project_id, host_snapshot_id)` -- the same key as the partial unique
    index revision 0006 creates.
    """

    def __init__(self):
        self.rows = {}
        self.inserts = 0

    async def ensure_reference(self, scope, value):
        return await self._ensure(scope, value)

    async def ensure_progress_reference(self, scope, value):
        return await self._ensure(scope, value)

    async def _ensure(self, scope, value):
        key = (str(scope.organization_id), scope.project_id, value.host_snapshot_id)
        if key not in self.rows:
            self.inserts += 1
            self.rows[key] = {
                "id": value.id, "organization_id": value.organization_id,
                "project_id": value.project_id,
                "progress_snapshot_id": value.progress_snapshot_id,
                "source_file_version_id": value.source_file_version_id,
                "source_file_name_safe": value.source_file_name_safe,
                "reporting_date": value.reporting_date,
                "snapshot_status": value.snapshot_status,
                "imported_by": value.imported_by, "imported_at": value.imported_at,
                "source_type": value.source_type,
                "host_snapshot_id": value.host_snapshot_id,
                "host_file_version_id": value.host_file_version_id}
        return self.rows[key]


#: So a test can say "the host replied with nothing" and be distinguished from "the test
#: did not specify a reply". Using None for both is how the first version of this file
#: silently tested the default header instead of the absent one.
UNSET = object()


class Provider:
    def __init__(self, reply=UNSET):
        self.reply = {"snapshot": header(), "assignments": []} if reply is UNSET else reply
        self.calls = 0

    async def get_snapshot(self, organization_id, project_id, snapshot_id):
        # A host echoes the identifier it was asked with. Finance validates the reply
        # against what it requested, so a fixture that echoed something else would be
        # testing a host that does not exist.
        if not isinstance(self.reply, dict) or not isinstance(self.reply.get("snapshot"), dict):
            return self.reply
        echoed = dict(self.reply["snapshot"], progressSnapshotId=str(snapshot_id))
        return dict(self.reply, snapshot=echoed)

    async def current_snapshot(self, organization_id, project_id, as_of=None):
        self.calls += 1
        return self.reply


class ProviderWithoutCurrent:
    """A host that predates the contract extension. It must keep working."""
    async def get_snapshot(self, organization_id, project_id, snapshot_id):
        return {"snapshot": header(), "assignments": []}


def service(repository, provider, ids=None):
    counter = iter([UUID(int=n) for n in range(100, 200)])
    return ProgressService(repository, provider,
                           id_factory=ids or (lambda: next(counter)), clock=lambda: AT)


class HostReferenceReadingTests(unittest.TestCase):
    """Core identifiers are bigint. Reading one must not accept something else."""

    def test_an_integer_identifier_is_read_as_it_is(self):
        self.assertEqual((9001, 1001), host_reference(header()))

    def test_a_json_string_identifier_is_accepted(self):
        # A host crossing a JSON boundary may well send "9001" rather than 9001.
        self.assertEqual((9001, 1001), host_reference(header(host_snapshot_id="9001",
                                                             host_file_version_id="1001")))

    def test_an_absent_identifier_is_absent_not_zero(self):
        self.assertEqual((None, None), host_reference({"organizationId": str(ORG)}))
        self.assertEqual((9001, None), host_reference(header(host_file_version_id=None)))

    def test_values_that_are_not_core_identifiers_are_refused(self):
        for value in (True, False, 0, -1, "abc", "", 3.5, [], {}):
            with self.subTest(value=repr(value)):
                with self.assertRaises(HostReferenceInvalid):
                    host_reference(header(host_snapshot_id=value))

    def test_a_boolean_is_refused_even_though_it_is_an_integer(self):
        # bool is an int subclass, so True would otherwise become snapshot 1.
        with self.assertRaises(HostReferenceInvalid):
            host_reference(header(host_snapshot_id=True))


class ReferenceIngestionTests(unittest.IsolatedAsyncioTestCase):
    """B-01: a financial operation can pin to a Core snapshot without a manual step."""

    async def test_the_same_core_snapshot_never_produces_a_second_reference(self):
        repository = RecordingRepository()
        provider = Provider()
        first = await service(repository, provider).current_reference(SCOPE, date(2026, 8, 2))
        second = await service(repository, provider).current_reference(SCOPE, date(2026, 8, 2))
        third = await service(repository, provider).current_reference(SCOPE, date(2026, 8, 3))
        self.assertEqual(1, repository.inserts, "one Core snapshot, one Finance reference")
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["id"], third["id"])

    async def test_the_reference_records_the_core_identity(self):
        repository = RecordingRepository()
        row = await service(repository, Provider()).current_reference(SCOPE, date(2026, 8, 2))
        self.assertEqual(9001, row["host_snapshot_id"])
        self.assertEqual(1001, row["host_file_version_id"])

    async def test_finance_owns_the_row_and_public_identifiers(self):
        # The Core bigint is a reference. It never becomes Finance's row identity, and the
        # UUID in URLs stays Finance's own.
        repository = RecordingRepository()
        row = await service(repository, Provider()).current_reference(SCOPE, date(2026, 8, 2))
        self.assertIsInstance(row["id"], UUID)
        self.assertIsInstance(row["progress_snapshot_id"], UUID)
        self.assertNotEqual(row["id"], row["progress_snapshot_id"])

    async def test_an_ingested_reference_invents_no_file_version_uuid(self):
        # There is no Finance-side file identifier for a Core reference, and a generated
        # UUID would look like a Host reference while being nothing of the kind.
        repository = RecordingRepository()
        row = await service(repository, Provider()).current_reference(SCOPE, date(2026, 8, 2))
        self.assertIsNone(row["source_file_version_id"])

    async def test_a_host_that_cannot_name_a_snapshot_produces_nothing(self):
        for label, reply in {"no reply": None, "no header": {"assignments": []},
                             "header without Core ids": {"snapshot": header(host_snapshot_id=None)},
                             }.items():
            with self.subTest(label):
                repository = RecordingRepository()
                row = await service(repository, Provider(reply=reply)).current_reference(
                    SCOPE, date(2026, 8, 2))
                self.assertIsNone(row)
                self.assertEqual(0, repository.inserts, "nothing may be invented")

    async def test_another_tenants_snapshot_is_never_recorded(self):
        other = {"snapshot": header(organization_id=UUID(int=99)), "assignments": []}
        repository = RecordingRepository()
        row = await service(repository, Provider(reply=other)).current_reference(
            SCOPE, date(2026, 8, 2))
        self.assertIsNone(row)
        self.assertEqual(0, repository.inserts)

    async def test_a_host_without_the_new_method_still_works(self):
        # The contract extension is optional. A host that predates it keeps the previous
        # behaviour: no reference, and the report says so through its warnings.
        repository = RecordingRepository()
        provider = ProviderWithoutCurrent()
        self.assertFalse(supports_current_snapshot(provider))
        self.assertIsNone(await service(repository, provider).current_reference(
            SCOPE, date(2026, 8, 2)))
        self.assertEqual(0, repository.inserts)


class LiveReportWithoutSeedTests(unittest.IsolatedAsyncioTestCase):
    """Requirement 10: production reporting must not depend on a seeded reference."""

    class Repository(RecordingRepository):
        """A database with no progress references at all -- a real, unseeded project."""

        async def load(self, scope, reporting_date):
            return {"snapshot": None, "estimates": [], "invoices": [], "conversions": [],
                    "gross_area": None, "settings_id": UUID(int=5)}

        async def snapshot(self, scope, snapshot_id):
            return None

        async def latest_overrides(self, scope, ref_id):
            return []

    def service(self, repository, provider):
        counter = iter([UUID(int=n) for n in range(300, 400)])
        return FinanceLiveReportService(repository, provider,
                                        id_factory=lambda: next(counter), clock=lambda: AT)

    async def test_a_report_works_on_a_database_with_no_seeded_reference(self):
        """The original B-01 property, now without the write.

        A real project with no seeded reference used to answer 404. It now calculates -- and
        since reading may not write, it does so without creating anything. The Core snapshot
        it used is still named, through hostSnapshotId.
        """
        repository = self.Repository()
        report = await self.service(repository, Provider()).live(SCOPE, date(2026, 8, 2))
        self.assertEqual(0, repository.inserts, "a read creates nothing")
        self.assertEqual(9001, report["host_snapshot_id"])
        self.assertIsNotNone(report["metrics"])

    async def test_repeating_the_report_does_not_multiply_references(self):
        repository = self.Repository()
        provider = Provider()
        for _ in range(3):
            await self.service(repository, provider).live(SCOPE, date(2026, 8, 2))
        self.assertEqual(0, repository.inserts)

    async def test_a_host_with_no_snapshot_still_answers_not_found(self):
        # Honest absence. Finance does not invent a snapshot to make the report succeed.
        from app.finance.domain.resources import FinanceRecordNotFound
        repository = self.Repository()
        with self.assertRaises(FinanceRecordNotFound):
            await self.service(repository, Provider(reply=None)).live(SCOPE, date(2026, 8, 2))

    async def test_missing_progress_is_still_missing_and_never_zero(self):
        """Requirement 9. The reference exists, but no assignment matches the line."""
        from app.finance.domain.reports import calculate_live_report
        line = {"id": UUID(int=11), "resource_id": UUID(int=12), "resource_type": "material",
                "resource_code": "mat", "resource_title": "material",
                "original_quantity": "10", "revised_quantity": "10",
                "original_unit_price_irr": "100", "current_unit_price_irr": "100",
                "assignment_external_id": None, "activity_external_id": None,
                "progress_snapshot_id": UUID(int=7)}
        report = calculate_live_report([line], [], [], [], "10")
        variance = report.quantity_variances[0]
        self.assertEqual(Decimal("0"), variance["executedQuantity"])
        self.assertEqual("unmapped_activity", variance["progressStatus"],
                         "zero with a status is an absence, not a measurement")
        self.assertFalse(report.progress_quality["complete"])


class HostOnlyKnowsItsOwnIdentifierTests(unittest.IsolatedAsyncioTestCase):
    """A real host has never heard of Finance's UUID.

    The other fixtures echo whichever identifier they are asked with, which is convenient
    but blind: it cannot tell a correct lookup from an incorrect one. This provider answers
    only to the Core identifier, the way `msp_snapshots` does, so asking with the Finance
    UUID fails here exactly as it would in production -- on the second report request, once
    the reference already exists and the pinning path is no longer involved.
    """

    class HostProvider:
        def __init__(self):
            self.asked = []

        async def get_snapshot(self, organization_id, project_id, snapshot_id):
            self.asked.append(str(snapshot_id))
            if str(snapshot_id) != "9001":
                return None          # a real host: unknown identifier, nothing to return
            return {"snapshot": dict(header(), progressSnapshotId="9001"), "assignments": []}

        async def current_snapshot(self, organization_id, project_id, as_of=None):
            return await self.get_snapshot(organization_id, project_id, "9001")

    class ExistingReferenceRepository(RecordingRepository):
        """A database where the reference was recorded on an earlier request."""

        def __init__(self):
            super().__init__()
            self.row = {"progress_snapshot_ref_id": UUID(int=42),
                        "progress_snapshot_id": UUID(int=43),
                        "host_snapshot_id": 9001,
                        "reporting_date": date(2026, 8, 2)}

        async def load(self, scope, reporting_date):
            return {"snapshot": self.row, "estimates": [], "invoices": [], "conversions": [],
                    "gross_area": None, "settings_id": UUID(int=5)}

        async def snapshot(self, scope, snapshot_id):
            return self.row

        async def latest_overrides(self, scope, ref_id):
            return []

    async def test_the_feed_is_requested_with_the_core_identifier(self):
        repository = self.ExistingReferenceRepository()
        provider = self.HostProvider()
        service = FinanceLiveReportService(repository, provider, id_factory=uuid4,
                                           clock=lambda: AT)
        await service.live(SCOPE, date(2026, 8, 2))
        # If Finance asked with its own UUID, this host would have answered nothing and the
        # report would have raised. The identifier it asked with is the Core one.
        self.assertEqual(["9001"], provider.asked)

    async def test_asking_with_the_finance_uuid_would_fail_against_a_real_host(self):
        # The counterpart, stated explicitly: the value Finance mints is meaningless to the
        # host, which is why the lookup key matters.
        provider = self.HostProvider()
        self.assertIsNone(await provider.get_snapshot(str(ORG), PROJECT, str(UUID(int=43))))


class NoCoreForeignKeyTests(unittest.TestCase):
    """Requirement 4: Finance stores Core references, never Core keys."""

    REVISIONS = BACKEND_ROOT / "alembic" / "versions"
    CORE_TABLES = ("msp_snapshots", "msp_file_versions", "msp_tasks", "projects",
                   "organizations", "users", "permissions", "roles", "media_files",
                   "audit_logs")

    def revision_sql(self):
        for path in sorted(self.REVISIONS.glob("*.py")):
            spec = importlib.util.spec_from_file_location("core_align_" + path.stem, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            yield path.name, module.UPGRADE_SQL + "\n" + module.DOWNGRADE_SQL

    #: The ONE sanctioned Core foreign key, decided by the project owner for the
    #: task-resource link table: 0009 references msp_tasks (id) ON DELETE CASCADE so
    #: a task Core deletes takes its mappings with it. The 0009 docstring records the
    #: operational precondition this reverses from 0007's day: the production
    #: migration role must first receive GRANT REFERENCES ON msp_tasks. Nothing else
    #: is sanctioned; a second entry in this set is a review decision, not a
    #: convenience.
    SANCTIONED_CORE_KEYS = {("0009_finance_task_resource_map.py", "msp_tasks")}

    def test_no_revision_references_a_core_table(self):
        """A Finance revision may not point a foreign key at a Core table -- except
        the one sanctioned 0009 link. Matched on the SQL that creates a reference,
        not on the table name appearing anywhere: `0007` explains at length why it
        does *not* reference msp_snapshots or msp_tasks, and a substring test failed
        it for saying so.
        """
        for name, sql in self.revision_sql():
            for table in self.CORE_TABLES:
                with self.subTest(revision=name, table=table):
                    if (name, table) not in self.SANCTIONED_CORE_KEYS:
                        self.assertNotRegex(
                            sql, r"REFERENCES\s+%s\b" % table,
                            "a Finance revision must not key into a Core-owned table")
                    self.assertNotRegex(
                        sql, r"ALTER\s+TABLE\s+(?:ONLY\s+)?%s\b" % table,
                        "a Finance revision must not alter a Core-owned table")

    def test_exactly_the_sanctioned_key_reaches_into_core(self):
        """One Core foreign key across the whole chain: 0009 -> msp_tasks (id).

        Until 0009 the count was zero and had to be: the production migration role
        had no REFERENCES privilege on Core tables. The project owner has since
        decided the task-resource link MUST be database-enforced, which turns the
        missing privilege into a deployment precondition (GRANT REFERENCES ON
        msp_tasks, recorded in 0009) instead of a design rule. This test pins the
        exception to exactly that one pair so the next Core key is a decision
        someone makes on purpose. The other logical relationships stay logical, and
        docs/sql/msp_resource_assignment_data_validation.sql counts their orphans.
        """
        found = {(name, table)
                 for name, sql in self.revision_sql()
                 for table in self.CORE_TABLES
                 if re.search(r"REFERENCES\s+%s\b" % table, sql)}
        self.assertEqual(self.SANCTIONED_CORE_KEYS, found)

    def test_no_revision_alters_an_existing_core_table(self):
        """The ownership line that did not move: Core tables are never modified here."""
        for name, sql in self.revision_sql():
            for table in self.CORE_TABLES:
                with self.subTest(revision=name, table=table):
                    self.assertNotRegex(sql, r"ALTER\s+TABLE\s+(?:ONLY\s+)?%s\b" % table)
                    self.assertNotRegex(sql, r"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?%s\b" % table)

    def test_no_revision_creates_a_core_owned_table(self):
        for name, sql in self.revision_sql():
            with self.subTest(name):
                for table in self.CORE_TABLES:
                    self.assertNotIn("CREATE TABLE IF NOT EXISTS %s" % table, sql)

    def test_the_host_reference_columns_are_bigint_and_nullable(self):
        """Requirement 3: Core identifiers are bigint, and absent means absent."""
        sql = dict(self.revision_sql())["0006_progress_snapshot_host_reference.py"]
        self.assertIn("ADD COLUMN IF NOT EXISTS host_snapshot_id bigint", sql)
        self.assertIn("ADD COLUMN IF NOT EXISTS host_file_version_id bigint", sql)
        # No NOT NULL and no DEFAULT: rows predating the integration keep NULL, which is
        # true of them, and the column is a catalog-only change so the table's immutability
        # trigger never fires.
        self.assertNotIn("host_snapshot_id bigint NOT NULL", sql)
        self.assertNotIn("host_snapshot_id bigint DEFAULT", sql)

    def test_the_idempotency_constraint_exists_and_is_tenant_scoped(self):
        """Requirement 5, at the database level rather than only in the service."""
        sql = dict(self.revision_sql())["0006_progress_snapshot_host_reference.py"]
        self.assertIn("CREATE UNIQUE INDEX IF NOT EXISTS ux_progress_snapshot_refs_host_snapshot", sql)
        self.assertIn("(organization_id, project_id, host_snapshot_id)", sql)
        self.assertIn("WHERE host_snapshot_id IS NOT NULL", sql)

    def test_the_legacy_uuid_columns_are_not_dropped(self):
        """Historical compatibility: staged migration, not destructive replacement."""
        sql = dict(self.revision_sql())["0006_progress_snapshot_host_reference.py"]
        self.assertNotIn("DROP COLUMN IF EXISTS progress_snapshot_id", sql)
        self.assertNotIn("DROP COLUMN IF EXISTS source_file_version_id", sql)


class AlembicOwnershipTests(unittest.TestCase):
    """Requirement 2: Finance owns its migration chain, not the shared database."""

    ENV = (BACKEND_ROOT / "alembic" / "env.py").read_text(encoding="utf-8")

    def test_a_finance_specific_version_table_is_configured(self):
        self.assertIn('VERSION_TABLE = "finance_alembic_version"', self.ENV)

    def test_it_applies_to_both_online_and_offline_modes(self):
        # An offline-only or online-only setting would put the version row in two different
        # tables depending on how the migration was run.
        self.assertEqual(2, self.ENV.count("version_table=VERSION_TABLE"))


class SnapshotResponseContractTests(unittest.TestCase):
    """The API carries the Core reference without breaking what was already there."""

    def test_the_host_reference_is_exposed_as_integers(self):
        for field in ("host_snapshot_id", "host_file_version_id"):
            with self.subTest(field):
                self.assertIn(field, ProgressSnapshotResponse.model_fields)
                self.assertFalse(ProgressSnapshotResponse.model_fields[field].is_required())

    def test_a_reference_ingested_from_core_serialises_without_a_file_version(self):
        payload = ProgressSnapshotResponse(
            organizationId=ORG, projectId=PROJECT, progressSnapshotId=UUID(int=7),
            sourceFileNameSafe="plan.mpp", importedAt=AT, importedBy=ACTOR, status="ready",
            reportingDate=date(2026, 8, 2), hostSnapshotId=9001, hostFileVersionId=1001
        ).model_dump(by_alias=True)
        self.assertIsNone(payload["sourceFileVersionId"])
        self.assertEqual(9001, payload["hostSnapshotId"])

    def test_a_row_from_before_the_integration_still_validates(self):
        # Every field added is optional, so a pre-0006 row parses unchanged.
        payload = ProgressSnapshotResponse(
            organizationId=ORG, projectId=PROJECT, progressSnapshotId=UUID(int=7),
            sourceFileVersionId=UUID(int=8), sourceFileNameSafe="plan.mpp", importedAt=AT,
            importedBy=ACTOR, status="ready", reportingDate=date(2026, 8, 2))
        self.assertIsNone(payload.host_snapshot_id)
        self.assertEqual(UUID(int=8), payload.source_file_version_id)


class FixtureShapeTests(unittest.TestCase):
    """Mock identifiers must behave like the Core types they stand in for."""

    def test_the_seeded_snapshots_carry_bigint_host_identifiers(self):
        from devhost import seed
        for snapshot in seed.PROGRESS_SNAPSHOTS:
            with self.subTest(snapshot["source_file_name_safe"]):
                self.assertIsInstance(snapshot["host_snapshot_id"], int)
                self.assertNotIsInstance(snapshot["host_snapshot_id"], bool)
                self.assertGreater(snapshot["host_snapshot_id"], 0)

    def test_the_generated_seed_sql_writes_them(self):
        sql = (BACKEND_ROOT / "devhost" / "seed.sql").read_text(encoding="utf-8")
        self.assertIn("host_snapshot_id,host_file_version_id", sql)

    def test_the_development_provider_can_name_its_current_snapshot(self):
        from devhost.ports import SeededProgressSnapshotProvider
        self.assertTrue(supports_current_snapshot(
            SeededProgressSnapshotProvider(ORG, PROJECT, [], ACTOR)))


if __name__ == "__main__":
    unittest.main()
class FirstRequestIdentityTests(unittest.IsolatedAsyncioTestCase):
    """The identity bug had a second hiding place: the request that creates the reference.

    `HostOnlyKnowsItsOwnIdentifierTests` covers the path where the reference already exists
    and is read back from the database, which supplies the Core identifier. On the *first*
    request the reference is minted in memory, and if that object omits host_snapshot_id
    Finance falls back to its own UUID -- a value the host has never heard of. A second
    request then works, so the bug is invisible unless a test looks at the first one.
    """

    class HostProvider:
        """Answers only to the Core identifier, as msp_snapshots does."""

        def __init__(self):
            self.asked = []

        async def get_snapshot(self, organization_id, project_id, snapshot_id):
            self.asked.append(str(snapshot_id))
            if str(snapshot_id) != "9001":
                return None
            return {"snapshot": dict(header(), progressSnapshotId="9001"), "assignments": []}

        async def current_snapshot(self, organization_id, project_id, as_of=None):
            return {"snapshot": header(), "assignments": []}

    class EmptyRepository(RecordingRepository):
        """A real project: no progress reference has ever been recorded."""

        def __init__(self):
            super().__init__()
            self.estimates = []
            self.issued = None

        def estimates_ready(self):
            """Issuing refuses without settings, resources and effective prices."""
            self.estimates = [{"id": UUID(int=21), "resource_id": UUID(int=22),
                               "resource_type": "material", "resource_code": "mat",
                               "resource_title": "material", "original_quantity": "10",
                               "revised_quantity": "10", "original_unit_price_irr": "100",
                               "current_unit_price_irr": "100", "assignment_external_id": None,
                               "activity_external_id": None, "estimate_version_id": UUID(int=23),
                               "price_version_id": UUID(int=24)}]

        async def load(self, scope, reporting_date):
            return {"snapshot": None, "estimates": self.estimates, "invoices": [],
                    "conversions": [], "gross_area": None, "settings_id": UUID(int=5)}

        async def snapshot(self, scope, snapshot_id):
            return None

        async def latest_overrides(self, scope, ref_id):
            return []

        async def issue(self, scope, value, payload, audit_id):
            self.issued = value
            return value

    async def issue(self, repository, provider):
        """Issuing is the operation that creates the reference, so identity matters here."""
        repository.estimates_ready()
        return await FinanceLiveReportService(repository, provider, id_factory=uuid4,
                                              clock=lambda: AT).issue(SCOPE, date(2026, 8, 2))

    async def test_the_creating_request_asks_the_host_with_the_core_identifier(self):
        repository = self.EmptyRepository()
        provider = self.HostProvider()
        await self.issue(repository, provider)
        self.assertEqual(1, repository.inserts, "the reference was created in this request")
        self.assertEqual(["9001"], provider.asked,
                         "the host must be asked with its own id, not the minted UUID")

    async def test_no_minted_uuid_is_ever_sent_to_the_host(self):
        repository = self.EmptyRepository()
        provider = self.HostProvider()
        await self.issue(repository, provider)
        minted = {str(row["progress_snapshot_id"]) for row in repository.rows.values()}
        self.assertTrue(minted, "a reference was created, so a UUID was minted")
        self.assertEqual(set(), minted & set(provider.asked),
                         "the value Finance minted is meaningless to the host")

    async def test_the_issued_report_pins_the_reference_it_created(self):
        repository = self.EmptyRepository()
        issued = await self.issue(repository, self.HostProvider())
        recorded = next(iter(repository.rows.values()))
        self.assertEqual(recorded["id"], repository.issued["progress_snapshot_ref_id"],
                         "the immutable report names the reference it used")
        self.assertEqual(recorded["progress_snapshot_id"], issued["progress_snapshot_id"])

    async def test_issuing_twice_against_one_core_snapshot_reuses_the_reference(self):
        repository, provider = self.EmptyRepository(), self.HostProvider()
        await self.issue(repository, provider)
        await self.issue(repository, provider)
        self.assertEqual(1, repository.inserts, "one Core snapshot, one Finance reference")


class OverrideIngestionTests(unittest.IsolatedAsyncioTestCase):
    """An override must be able to pin without the live report having run first."""

    class HostProvider:
        def __init__(self):
            self.asked = []

        async def get_snapshot(self, organization_id, project_id, snapshot_id):
            self.asked.append(str(snapshot_id))
            if str(snapshot_id) != "9001":
                return None
            return {"snapshot": dict(header(), progressSnapshotId="9001"),
                    "assignments": [{"assignmentExternalId": "AS1", "actualQuantity": "4",
                                     "manualOverride": None,
                                     "task": {"activityCode": "ACT-1"}}]}

        async def current_snapshot(self, organization_id, project_id, as_of=None):
            return {"snapshot": header(), "assignments": []}

    class Repository(RecordingRepository):
        """No seeded reference. Reads resolve against whatever ingestion recorded."""

        def __init__(self):
            super().__init__()
            self.appended = []

        async def get_snapshot(self, scope, snapshot_id):
            for row in self.rows.values():
                if str(row["progress_snapshot_id"]) == str(snapshot_id):
                    return row
            return None

        async def get_line_mapping(self, scope, line_id):
            return {"id": line_id, "activity_external_id": "ACT-1",
                    "assignment_external_id": "AS1"}

        async def append_override(self, scope, value, audit_id):
            self.appended.append(value)
            return value

    def service(self, repository, provider):
        return ProgressService(repository, provider, id_factory=uuid4, clock=lambda: AT)

    async def ensure_then_override(self, repository, provider, line=UUID(int=11)):
        """Pin first, then override with the identifier the client would have been given."""
        from app.finance.schemas.progress import ProgressOverrideCreate
        reference = await self.service(repository, provider).current_reference(
            SCOPE, date(2026, 8, 2))
        command = ProgressOverrideCreate(
            progressSnapshotId=reference["progress_snapshot_id"], overrideValue="9",
            reason="اصلاح معتبر")
        return reference, await self.service(repository, provider).override(SCOPE, line, command)

    async def test_an_override_pins_the_reference_and_records_it(self):
        repository, provider = self.Repository(), self.HostProvider()
        reference, override = await self.ensure_then_override(repository, provider)
        self.assertEqual(1, repository.inserts)
        self.assertEqual(reference["id"], override.progress_snapshot_ref_id,
                         "the override stores the Finance reference it pinned to")
        self.assertEqual(1, len(repository.appended))

    async def test_the_override_asks_the_host_with_the_core_identifier(self):
        repository, provider = self.Repository(), self.HostProvider()
        await self.ensure_then_override(repository, provider)
        # Overrides had the same identity bug as the report: they looked the feed up by the
        # client-supplied Finance UUID, which a real host cannot resolve.
        self.assertEqual(["9001"], provider.asked)

    async def test_repeating_the_override_reuses_the_same_reference(self):
        repository, provider = self.Repository(), self.HostProvider()
        first, _ = await self.ensure_then_override(repository, provider)
        second, _ = await self.ensure_then_override(repository, provider, line=UUID(int=12))
        self.assertEqual(1, repository.inserts, "one Core snapshot, one Finance reference")
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(2, len(repository.appended), "both overrides were recorded")

    async def test_the_override_itself_pins_when_nothing_has_been_recorded(self):
        """The path the other tests skip past.

        `ensure_then_override` pins first, the way a client that had opened the live report
        would, so it never exercises the ingestion inside `override()`. Here nothing has run
        beforehand: the override is the operation that creates the reference.

        The identifiers are predicted rather than fetched, because a client cannot be handed
        an identifier that does not exist yet. The service mints two per reference -- the row
        id, then the public id -- so a factory starting at 500 yields 500 and 501, and 501 is
        what the reference will be reachable by.
        """
        from app.finance.schemas.progress import ProgressOverrideCreate
        repository, provider = self.Repository(), self.HostProvider()
        counter = iter([UUID(int=n) for n in range(500, 600)])
        service = ProgressService(repository, provider, id_factory=lambda: next(counter),
                                  clock=lambda: AT)
        command = ProgressOverrideCreate(progressSnapshotId=UUID(int=501), overrideValue="9",
                                         reason="اصلاح معتبر")
        override = await service.override(SCOPE, UUID(int=11), command)
        self.assertEqual(1, repository.inserts, "the override created the reference itself")
        self.assertEqual(UUID(int=500), override.progress_snapshot_ref_id)
        self.assertEqual(["9001"], provider.asked, "and asked the host by its own id")

    async def test_an_override_naming_an_unknown_snapshot_is_still_refused(self):
        """Ingestion must not become a way to silently pin the wrong snapshot."""
        from app.finance.domain.resources import FinanceRecordNotFound
        from app.finance.schemas.progress import ProgressOverrideCreate
        repository, provider = self.Repository(), self.HostProvider()
        command = ProgressOverrideCreate(progressSnapshotId=UUID(int=999), overrideValue="9",
                                         reason="اصلاح معتبر")
        with self.assertRaises(FinanceRecordNotFound):
            await self.service(repository, provider).override(SCOPE, UUID(int=11), command)


class ImportedByInvariantTests(unittest.TestCase):
    """`progress_snapshot_refs.imported_by` is NOT NULL, so a reference needs an importer."""

    def test_the_router_path_always_supplies_an_actor(self):
        """Verified against the security contract rather than assumed.

        AuthContext.user_id is a required UUID, and the scope guard builds actor_user_id
        from it, so every request that reaches a service carries an actor.
        """
        from app.finance.security.context import AuthContext
        self.assertTrue(AuthContext.model_fields["user_id"].is_required())
        guards = (BACKEND_ROOT / "app" / "finance" / "security" / "guards.py").read_text(
            encoding="utf-8")
        self.assertIn("actor_user_id=context.user_id", guards)

    def test_a_header_without_an_importer_and_no_actor_builds_nothing(self):
        """Rather than an INSERT that fails at the database boundary."""
        from app.finance.domain.progress import reference_from_header
        anonymous = SimpleNamespace(organization_id=ORG, project_id=PROJECT,
                                    actor_user_id=None)
        without_importer = dict(header())
        without_importer.pop("importedBy")
        self.assertIsNone(reference_from_header(without_importer, anonymous,
                                                lambda: uuid4(), lambda: AT))

    def test_the_host_importer_is_used_when_present(self):
        from app.finance.domain.progress import reference_from_header
        anonymous = SimpleNamespace(organization_id=ORG, project_id=PROJECT,
                                    actor_user_id=None)
        reference = reference_from_header(header(), anonymous, lambda: uuid4(), lambda: AT)
        self.assertEqual(str(ACTOR), str(reference.imported_by))

    def test_the_actor_stands_in_when_the_host_names_no_importer(self):
        from app.finance.domain.progress import reference_from_header
        without_importer = dict(header())
        without_importer.pop("importedBy")
        reference = reference_from_header(without_importer, SCOPE, lambda: uuid4(),
                                          lambda: AT)
        self.assertEqual(ACTOR, reference.imported_by)

    def test_no_user_identifier_is_ever_invented(self):
        source = (BACKEND_ROOT / "app" / "finance" / "domain" / "progress.py").read_text(
            encoding="utf-8")
        for fabrication in ("uuid4()", "gen_random_uuid", "UUID(int="):
            with self.subTest(fabrication):
                self.assertNotIn(fabrication, source)


class ReadEndpointsNeverWriteTests(unittest.IsolatedAsyncioTestCase):
    """Reading a report must not create anything.

    `GET /reports/live` and `GET /overview` reach this path, and `/overview` is gated only by
    `finance.view`. A read permission that quietly performs an INSERT is a permission that
    does not mean what it says, and refreshing a page is not a financial event.

    The reference is created where something immutable is being written instead -- an issued
    report or an override -- because those are the things that must stay reproducible against
    one exact Core snapshot.
    """

    class Repository(RecordingRepository):
        def __init__(self, pinned=None):
            super().__init__()
            self.pinned = pinned
            self.host_lookups = 0

        async def load(self, scope, reporting_date):
            return {"snapshot": None, "estimates": [], "invoices": [], "conversions": [],
                    "gross_area": None, "settings_id": UUID(int=5)}

        async def snapshot(self, scope, snapshot_id):
            return None

        async def latest_overrides(self, scope, ref_id):
            return []

        async def progress_reference_for_host(self, scope, host_snapshot_id):
            self.host_lookups += 1
            return self.pinned

    def service(self, repository, provider):
        return FinanceLiveReportService(repository, provider, id_factory=uuid4,
                                        clock=lambda: AT)

    async def test_a_fresh_project_gets_a_report_and_no_write(self):
        repository, provider = self.Repository(), Provider()
        report = await self.service(repository, provider).live(SCOPE, date(2026, 8, 2))
        self.assertEqual(0, repository.inserts, "viewing a page must not insert a row")
        self.assertIsNotNone(report["metrics"], "the report is still calculated")

    async def test_repeated_reads_still_write_nothing(self):
        repository, provider = self.Repository(), Provider()
        for _ in range(5):
            await self.service(repository, provider).live(SCOPE, date(2026, 8, 2))
        self.assertEqual(0, repository.inserts)

    async def test_the_overview_projection_writes_nothing_either(self):
        # The one gated by finance.view, which is the reason this rule exists.
        repository, provider = self.Repository(), Provider()
        await self.service(repository, provider).overview(SCOPE, date(2026, 8, 2))
        self.assertEqual(0, repository.inserts)

    async def test_an_unpinned_read_has_no_finance_identifier_but_names_the_core_one(self):
        repository, provider = self.Repository(), Provider()
        report = await self.service(repository, provider).live(SCOPE, date(2026, 8, 2))
        self.assertIsNone(report["progress_snapshot_id"],
                          "no Finance reference exists, so there is no Finance UUID to give")
        self.assertEqual(9001, report["host_snapshot_id"])

    async def test_an_existing_reference_is_read_and_reused_without_writing(self):
        pinned = {"id": UUID(int=42), "progress_snapshot_id": UUID(int=43),
                  "host_snapshot_id": 9001, "reporting_date": date(2026, 8, 2)}
        repository = self.Repository(pinned=pinned)
        report = await self.service(repository, Provider()).live(SCOPE, date(2026, 8, 2))
        self.assertEqual(0, repository.inserts)
        self.assertEqual(1, repository.host_lookups)
        self.assertEqual(UUID(int=43), report["progress_snapshot_id"],
                         "a pinned project keeps showing its stable Finance identifier")

    async def test_the_core_identifier_is_never_returned_as_the_finance_one(self):
        repository, provider = self.Repository(), Provider()
        report = await self.service(repository, provider).live(SCOPE, date(2026, 8, 2))
        # One is a Finance UUID, the other a Core bigint. Substituting either for the other
        # is the identity confusion this whole design exists to remove.
        self.assertNotIsInstance(report["host_snapshot_id"], UUID)
        self.assertIsInstance(report["host_snapshot_id"], int)
        self.assertNotEqual(str(report["host_snapshot_id"]),
                            str(report["progress_snapshot_id"]))

    async def test_missing_progress_stays_missing_when_nothing_is_pinned(self):
        """An unpinned read means zero *overrides*, never zero progress."""
        from app.finance.domain.reports import calculate_live_report
        line = {"id": UUID(int=11), "resource_id": UUID(int=12), "resource_type": "material",
                "resource_code": "mat", "resource_title": "material",
                "original_quantity": "10", "revised_quantity": "10",
                "original_unit_price_irr": "100", "current_unit_price_irr": "100",
                "assignment_external_id": None, "activity_external_id": None,
                "progress_snapshot_id": None}
        report = calculate_live_report([line], [], [], [], "10")
        variance = report.quantity_variances[0]
        self.assertEqual(Decimal("0"), variance["executedQuantity"])
        self.assertEqual("unmapped_activity", variance["progressStatus"])
        self.assertFalse(report.progress_quality["complete"])

    async def test_nothing_is_written_when_there_is_no_core_snapshot_to_pin(self):
        from app.finance.domain.resources import FinanceRecordNotFound
        repository = self.Repository()
        with self.assertRaises(FinanceRecordNotFound):
            await self.service(repository, Provider(reply=None)).live(SCOPE, date(2026, 8, 2))
        self.assertEqual(0, repository.inserts)

    async def test_an_unpinned_response_survives_the_response_model(self):
        """Where a required field would actually break: the HTTP boundary.

        The route declares `response_model=LiveReportResponse`, so an unpinned project would
        fail response validation with a 500 rather than anywhere the service tests look. The
        service returns plain dicts, so nothing else in this file would notice.
        """
        from app.finance.schemas.reports import (LiveReportResponse,
                                                 OperationalOverviewResponse)
        repository, provider = self.Repository(), Provider()
        service = self.service(repository, provider)
        live = LiveReportResponse(**await service.live(SCOPE, date(2026, 8, 2)))
        payload = live.model_dump(by_alias=True)
        self.assertIsNone(payload["progressSnapshotId"], "null is a legitimate answer")
        self.assertEqual(9001, payload["hostSnapshotId"])

        overview = OperationalOverviewResponse(**await service.overview(SCOPE, date(2026, 8, 2)))
        self.assertIsNone(overview.model_dump(by_alias=True)["progressSnapshotId"])

    async def test_a_pinned_response_still_carries_its_finance_uuid(self):
        from app.finance.schemas.reports import LiveReportResponse
        pinned = {"id": UUID(int=42), "progress_snapshot_id": UUID(int=43),
                  "host_snapshot_id": 9001, "reporting_date": date(2026, 8, 2)}
        repository = self.Repository(pinned=pinned)
        live = LiveReportResponse(**await self.service(repository, Provider()).live(
            SCOPE, date(2026, 8, 2)))
        self.assertEqual(UUID(int=43), live.model_dump(by_alias=True)["progressSnapshotId"])

    def test_the_read_endpoints_really_are_GET(self):
        router = (BACKEND_ROOT / "app" / "finance" / "router.py").read_text(encoding="utf-8")
        self.assertIn('@router.get("/reports/live"', router)
        self.assertIn('@router.get("/overview"', router)

    def test_only_the_writing_operations_pin(self):
        """The rule, asserted against the service rather than only its behaviour."""
        source = (BACKEND_ROOT / "app" / "finance" / "services" / "reports.py").read_text(
            encoding="utf-8")
        # The call site, not the word: the docstrings explain pin=True more than once.
        self.assertEqual(1, source.count("progress_snapshot_id,pin=True"),
                         "issuing is the only caller that may create a reference")
        self.assertIn("async def issue(", source)
        self.assertIn("if pin else self._read_current_snapshot", source)
