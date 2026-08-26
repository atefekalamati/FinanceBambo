"""Development data mirrored from the frontend's own reference dataset.

Every identifier, title, quantity, price and date here is copied from the mock adapters
under `frontend/src/adapters/mock/`, so the browser shows the same project whether it
runs in standalone (mock) or host (database) mode. When the mock data changes, this file
is what has to follow.

Two deliberate additions, because the mock keeps them implicit:

* Estimate lines carry `assignment_external_id`. The mock links lines to progress rows
  through the activity code alone, which is ambiguous here: ACT-201 covers both the rebar
  line and the crane line, so matching by activity would hand them the same assignment.
* The mock's 53 invoices are generated from an index rather than listed, and their ids are
  not UUIDs. `generate_seed_sql.py` reproduces that rule and writes them into `seed.sql`
  with deterministic UUIDs, pointing at the real estimate lines above.

Database rows are emitted to `seed.sql`. What stays here is what the host ports serve
rather than store: the progress feed and the activity list.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

ORGANIZATION_ID = UUID("11111111-1111-4111-8111-111111111111")
PROJECT_ID = "sample_site_01"
ACTOR_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
IMPORTER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3")

# Master data is created before the first progress snapshot. The live report filters
# estimate lines and revisions by created_at <= reportingDate, so a later timestamp would
# make the whole estimate invisible to the report.
NOW = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)

# frontend/src/adapters/mock/settings-adapter.js
SETTINGS_ID = UUID("10000000-0000-4000-8000-000000000001")
GROSS_BUILT_AREA = Decimal("4250.0000")
SETTINGS_REASON = "ثبت اولیه زیربنای کل پروژه"
# The mock dates this revision 2026-08-06, which is after its own newest snapshot
# (2026-08-02). Nothing in the mock computes from it, but here the report resolves the
# gross area with effective_from <= reportingDate, so keeping that date would leave every
# per-square-metre metric unresolved. The area and reason match the mock; only the
# effective date is pulled back so it actually applies.
SETTINGS_EFFECTIVE_FROM = date(2026, 6, 1)

# frontend/src/adapters/mock/financial-items-adapter.js
# id, type, code, title, base_unit, dimension, external_resource_id
RESOURCES = [
    (UUID("20000000-0000-4000-8000-000000000001"), "material", "MAT-REBAR", "میلگرد",
     "kg", "mass", "res-rebar"),
    (UUID("20000000-0000-4000-8000-000000000002"), "labor", "LAB-FORM", "اکیپ قالب‌بندی",
     "person_hour", "labor_time", "res-formwork-team"),
    (UUID("20000000-0000-4000-8000-000000000003"), "equipment", "EQ-CRANE", "جرثقیل",
     "hour", "time", "res-crane"),
    (UUID("20000000-0000-4000-8000-000000000004"), "general_cost", "GEN-PERMIT", "هزینه مجوز",
     None, None, "res-permit"),
]
REBAR, FORMWORK, CRANE, PERMIT = (row[0] for row in RESOURCES)

ACTIVITIES = [
    {"activityExternalId": "ACT-102", "taskExternalId": "task-foundation",
     "title": "اجرای فونداسیون", "wbsCode": "1.2", "status": "active"},
    {"activityExternalId": "ACT-201", "taskExternalId": "task-floor1-slab",
     "title": "سقف طبقه اول", "wbsCode": "2.1", "status": "active"},
    {"activityExternalId": "ACT-202", "taskExternalId": "task-formwork",
     "title": "قالب‌بندی", "wbsCode": "2.2", "status": "active"},
    {"activityExternalId": "ACT-002", "taskExternalId": "task-permit",
     "title": "مجوزهای پروژه", "wbsCode": "0.2", "status": "active"},
]

# id, resource, activity, assignment, original_quantity, original_unit_price_irr, source
# The mock's revisedQuantity becomes an estimate revision below: the backend keeps the
# original immutable and derives the revised value from the revision trail.
#
# A general-cost line is amount-based: it carries no quantity, and its approved amount
# lives in original_unit_price_irr. Quantified lines are the other way round.
ESTIMATE_LINES = [
    (UUID("30000000-0000-4000-8000-000000000001"), REBAR, "ACT-102", "asg-foundation-rebar",
     Decimal("10000.0000"), None, "progress_feed"),
    # The feed has no rebar assignment for ACT-201, so this line reports no progress.
    (UUID("30000000-0000-4000-8000-000000000002"), REBAR, "ACT-201", None,
     Decimal("8500.0000"), None, "progress_feed"),
    (UUID("30000000-0000-4000-8000-000000000003"), FORMWORK, "ACT-202", "asg-labor-formwork",
     Decimal("900.0000"), None, "progress_feed"),
    (UUID("30000000-0000-4000-8000-000000000004"), CRANE, "ACT-201", "asg-crane-floor1",
     Decimal("160.0000"), None, "progress_feed"),
    (UUID("30000000-0000-4000-8000-000000000005"), PERMIT, "ACT-002", "asg-permit-general",
     None, Decimal("250000000"), "manual_entry"),
]

# Every row this file writes takes its id from one of these families. Rows created through
# the API get a generated UUID instead, so the prefix is what separates a fixture from real
# activity - not the `source` column, which is itself part of the data being mirrored.
FIXTURE_ID_PREFIXES = (
    "10000000",  # finance_project_settings
    "20000000",  # finance_resources
    "30000000",  # estimate_lines
    "31000000",  # estimate_revisions
    "33333333",  # progress_snapshot_refs
    "40000000",  # invoices
    "41000000",  # invoice_lines
    "50000000",  # price_versions
    "55555555",  # unit_conversions
    "66666666",  # progress_overrides
    "90000000",  # finance_audit_events
)

# estimate_line, revision, previous_quantity, new_quantity, reason
# The line's reported revision is max(revision) + 1, so the first revision row is
# numbered 1 and the line then reads as revision 2, matching the mock.
ESTIMATE_REVISIONS = [
    (ESTIMATE_LINES[0][0], 1, Decimal("10000.0000"), Decimal("11250.0000"),
     "افزایش متره فونداسیون طبق نقشه اجرایی"),
    (ESTIMATE_LINES[2][0], 1, Decimal("900.0000"), Decimal("980.0000"),
     "افزایش ساعت قالب‌بندی طبق صورت‌جلسه"),
]

# frontend/src/adapters/mock/prices-adapter.js
# id, resource, scope, version, unit_price_irr, effective_from
PRICE_VERSIONS = [
    (UUID("50000000-0000-4000-8000-000000000001"), REBAR, "organization", 1,
     Decimal("285000"), date(2026, 7, 1)),
    (UUID("50000000-0000-4000-8000-000000000002"), REBAR, "project", 2,
     Decimal("302000"), date(2026, 8, 1)),
    (UUID("50000000-0000-4000-8000-000000000003"), FORMWORK, "organization", 3,
     Decimal("1850000"), date(2026, 7, 15)),
    (UUID("50000000-0000-4000-8000-000000000004"), CRANE, "organization", 4,
     Decimal("12500000"), date(2026, 6, 20)),
    (UUID("50000000-0000-4000-8000-000000000005"), CRANE, "project", 5,
     Decimal("13200000"), date(2026, 8, 3)),
    (UUID("50000000-0000-4000-8000-000000000006"), REBAR, "project", 6,
     Decimal("295000"), date(2026, 7, 15)),
]

# id, scope, version, source_unit, target_unit, dimension, factor, effective_from
UNIT_CONVERSIONS = [
    (UUID("55555555-5555-4555-8555-555555555551"), "organization", 1,
     "ton", "kg", "mass", Decimal("1000.00000000"), date(2026, 1, 1)),
    (UUID("55555555-5555-4555-8555-555555555552"), "organization", 1,
     "equipment_day", "hour", "time", Decimal("8.00000000"), date(2026, 1, 1)),
    (UUID("55555555-5555-4555-8555-555555555553"), "project", 2,
     "equipment_day", "hour", "time", Decimal("10.00000000"), date(2026, 7, 1)),
]

# frontend/src/adapters/mock/progress-adapter.js
_TASKS = {
    "asg-foundation-rebar": {"taskExternalId": "task-foundation", "taskName": "اجرای فونداسیون نمونه",
                             "wbsCode": "1.2", "activityCode": "ACT-102",
                             "parentTaskExternalId": "task-structure", "taskProgressPercent": "25.0000",
                             "taskStart": "2026-06-01", "taskFinish": "2026-08-30"},
    "asg-permit-general": {"taskExternalId": "task-permit", "taskName": "مجوزهای نمونه",
                           "wbsCode": "0.2", "activityCode": "ACT-002",
                           "parentTaskExternalId": None, "taskProgressPercent": None,
                           "taskStart": None, "taskFinish": None},
    "asg-crane-floor1": {"taskExternalId": "task-floor1-slab", "taskName": "سقف طبقه اول نمونه",
                         "wbsCode": "2.1", "activityCode": "ACT-201",
                         "parentTaskExternalId": "task-structure", "taskProgressPercent": "28.0000",
                         "taskStart": "2026-07-01", "taskFinish": "2026-09-15"},
    "asg-labor-formwork": {"taskExternalId": "task-formwork", "taskName": "قالب‌بندی نمونه",
                           "wbsCode": "2.2", "activityCode": "ACT-202",
                           "parentTaskExternalId": "task-structure", "taskProgressPercent": "30.0000",
                           "taskStart": "2026-07-10", "taskFinish": "2026-09-20"},
}

_REBAR_ROW = {"assignmentExternalId": "asg-foundation-rebar", "resourceExternalId": "res-rebar",
              "resourceName": "میلگرد نمونه", "resourceType": "material", "unit": "kg",
              "plannedQuantity": "10000.0000", "actualQuantity": "2500.0000",
              "remainingQuantity": "7500.0000", "plannedWork": None, "actualWork": None,
              "remainingWork": None, "assignmentWorkCompletePercent": None,
              "task": _TASKS["asg-foundation-rebar"], "manualOverride": None}

_PERMIT_ROW = {"assignmentExternalId": "asg-permit-general", "resourceExternalId": "res-permit",
               "resourceName": "هزینه مجوز نمونه", "resourceType": "general_cost", "unit": None,
               "plannedQuantity": None, "actualQuantity": None, "remainingQuantity": None,
               "plannedWork": None, "actualWork": None, "remainingWork": None,
               "assignmentWorkCompletePercent": None,
               "task": _TASKS["asg-permit-general"], "manualOverride": None}

_CRANE_ROW = {"assignmentExternalId": "asg-crane-floor1", "resourceExternalId": "res-crane",
              "resourceName": "جرثقیل نمونه", "resourceType": "equipment", "unit": "hour",
              "plannedQuantity": "160.0000", "actualQuantity": "48.0000",
              "remainingQuantity": "112.0000", "plannedWork": "160.0000", "actualWork": "48.0000",
              "remainingWork": "112.0000", "assignmentWorkCompletePercent": "30.0000",
              "task": _TASKS["asg-crane-floor1"], "manualOverride": None}

_FORMWORK_ROW = {"assignmentExternalId": "asg-labor-formwork",
                 "resourceExternalId": "res-formwork-team", "resourceName": "اکیپ قالب‌بندی نمونه",
                 "resourceType": "labor", "unit": "person_hour",
                 "plannedQuantity": "900.0000", "actualQuantity": "315.0000",
                 "remainingQuantity": "585.0000", "plannedWork": "900.0000", "actualWork": None,
                 "remainingWork": None, "assignmentWorkCompletePercent": None,
                 "task": _TASKS["asg-labor-formwork"], "manualOverride": None}

PROGRESS_SNAPSHOTS = [
    {"ref_id": UUID("33333333-3333-4333-8333-3333333331ff"),
     "progress_snapshot_id": UUID("33333333-3333-4333-8333-333333333331"),
     "source_file_version_id": UUID("44444444-4444-4444-8444-444444444441"),
     "source_file_name_safe": "sample-progress-v1.mpp",
     "reporting_date": date(2026, 7, 31),
     "host_snapshot_id": 9001, "host_file_version_id": 1001,
     "imported_at": datetime(2026, 8, 1, 8, 30, tzinfo=timezone.utc),
     "assignments": [_REBAR_ROW, _PERMIT_ROW]},
    {"ref_id": UUID("33333333-3333-4333-8333-3333333332ff"),
     "progress_snapshot_id": UUID("33333333-3333-4333-8333-333333333332"),
     "source_file_version_id": UUID("44444444-4444-4444-8444-444444444442"),
     "source_file_name_safe": "sample-resource-loaded-v2.mpp",
     "reporting_date": date(2026, 8, 1),
     "host_snapshot_id": 9002, "host_file_version_id": 1002,
     "imported_at": datetime(2026, 8, 2, 8, 30, tzinfo=timezone.utc),
     "assignments": [_REBAR_ROW, _PERMIT_ROW, _CRANE_ROW]},
    {"ref_id": UUID("33333333-3333-4333-8333-3333333333ff"),
     "progress_snapshot_id": UUID("33333333-3333-4333-8333-333333333333"),
     "source_file_version_id": UUID("44444444-4444-4444-8444-444444444443"),
     "source_file_name_safe": "sample-progress-v3.mpp",
     "reporting_date": date(2026, 8, 2),
     "host_snapshot_id": 9003, "host_file_version_id": 1003,
     "imported_at": datetime(2026, 8, 3, 8, 30, tzinfo=timezone.utc),
     "assignments": [_REBAR_ROW, _PERMIT_ROW, _CRANE_ROW, _FORMWORK_ROW]},
]

LATEST_SNAPSHOT = PROGRESS_SNAPSHOTS[-1]
SNAPSHOT_ID = LATEST_SNAPSHOT["progress_snapshot_id"]
REPORTING_DATE = LATEST_SNAPSHOT["reporting_date"]

# The mock records this override on the formwork assignment of the newest snapshot.
PROGRESS_OVERRIDE = {
    "id": UUID("66666666-6666-4666-8666-666666666661"),
    "estimate_line_id": ESTIMATE_LINES[2][0],
    "progress_snapshot_ref_id": LATEST_SNAPSHOT["ref_id"],
    "computed_value": Decimal("270.0000"),
    "override_value": Decimal("315.0000"),
    "reason": "اصلاح ساختگی بر اساس صورت‌جلسه نمونه",
    "created_by": UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2"),
    "created_at": datetime(2026, 8, 3, 9, 0, tzinfo=timezone.utc),
}
