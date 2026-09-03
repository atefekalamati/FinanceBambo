"""The demo project: a mid-rise residential building at roughly 30% completion.

WHY THE NUMBERS LOOK LIKE THIS
Every figure below was chosen so that the *calculations* land on a coherent construction
scenario. Nothing is a stored result: the dashboard has no summary rows to read, so each
headline number is produced by `domain/reports.py` from these quantities, prices, revisions,
progress rows and invoices. Change one line here and the dashboard moves accordingly, which
is the property that makes this a demo of the system rather than a picture of one.

MONEY IS IRR EVERYWHERE
The database stores integer rial. The interface shows toman. `T` below multiplies by ten so
the numbers in this file can be read in the same unit the client speaks, and stored in the
unit the schema requires.

THE SCENARIO, IN TOMAN
    original estimate      68,000,000,000        16,000,000 / m2
    revised estimate       72,248,000,000        17,000,000 / m2
    executed to date       21,960,000,000        ~30% of the work, by value
    confirmed actual       22,982,000,000
    remaining at today's prices   50,920,000,000
    still to procure       48,512,000,000
    forecast final         71,493,000,000        16,822,000 / m2

The story those numbers tell: quantities grew about 6% at revision, and market prices have
risen since the estimate was priced -- rebar 18%, crane hire 30%. Against that, a large part
of the material was procured early, below today's market. The two effects nearly cancel, so
the forecast lands 5.1% above the original estimate and 1.0% *below* the revised one. That is
a project running slightly better than its own revision, and it is the kind of result a
finance module exists to show.

PROGRESS IS 30% BY VALUE, NOT BY LINE
Executed value / (executed + remaining) = 30.1%. Individual lines differ, as they do on a
real site: equipment and formwork labour are consumed early, material installation lags
behind procurement. The percentages per line are not padded to look uniform.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

ORGANIZATION_ID = UUID("11111111-1111-4111-8111-111111111111")
PROJECT_ID = "sample_site_01"
ACTOR_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
IMPORTER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3")


def T(toman) -> Decimal:
    """Toman as the integer rial the schema stores. Ten rial to the toman."""
    return Decimal(toman) * 10


# Master data is created before the first progress snapshot. The live report filters
# estimate lines and revisions by created_at <= reportingDate, so a later timestamp would
# make the whole estimate invisible to the report.
NOW = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)

SETTINGS_ID = UUID("10000000-0000-4000-8000-000000000001")
GROSS_BUILT_AREA = Decimal("4250.0000")
SETTINGS_REASON = "ثبت زیربنای کل بر اساس پروانه ساختمانی"
SETTINGS_EFFECTIVE_FROM = date(2026, 6, 1)

# id, type, code, title, base_unit, dimension, external_resource_id
RESOURCES = [
    (UUID("20000000-0000-4000-8000-000000000001"), "material", "MAT-REBAR",
     "میلگرد آجدار A3", "kg", "mass", "res-rebar"),
    (UUID("20000000-0000-4000-8000-000000000002"), "material", "MAT-CONCRETE",
     "بتن آماده C30", "m3", "volume", "res-concrete"),
    (UUID("20000000-0000-4000-8000-000000000003"), "material", "MAT-BLOCK",
     "بلوک سفالی دیوارچینی", "each", "count", "res-block"),
    (UUID("20000000-0000-4000-8000-000000000004"), "material", "MAT-CEMENT",
     "سیمان تیپ ۲", "ton", "mass", "res-cement"),
    (UUID("20000000-0000-4000-8000-000000000005"), "labor", "LAB-FORM",
     "اکیپ قالب‌بندی", "person_hour", "labor_time", "res-formwork-team"),
    (UUID("20000000-0000-4000-8000-000000000006"), "labor", "LAB-REBAR",
     "اکیپ آرماتوربندی", "person_hour", "labor_time", "res-rebar-team"),
    (UUID("20000000-0000-4000-8000-000000000007"), "equipment", "EQ-CRANE",
     "جرثقیل برجی", "hour", "time", "res-crane"),
    (UUID("20000000-0000-4000-8000-000000000008"), "equipment", "EQ-EXCAV",
     "بیل مکانیکی", "hour", "time", "res-excavator"),
    (UUID("20000000-0000-4000-8000-000000000009"), "general_cost", "GEN-PERMIT",
     "مجوز و عوارض شهرداری", None, None, "res-permit"),
    (UUID("20000000-0000-4000-8000-000000000010"), "general_cost", "GEN-INSURANCE",
     "بیمه و تضامین پروژه", None, None, "res-insurance"),
]
(REBAR, CONCRETE, BLOCK, CEMENT, FORMWORK, REBAR_TEAM,
 CRANE, EXCAVATOR, PERMIT, INSURANCE) = (row[0] for row in RESOURCES)

ACTIVITIES = [
    {"activityExternalId": "ACT-002", "taskExternalId": "task-permits",
     "title": "مجوزها و بیمه پروژه", "wbsCode": "0.2", "status": "active"},
    {"activityExternalId": "ACT-101", "taskExternalId": "task-earthworks",
     "title": "تجهیز کارگاه و خاکبرداری", "wbsCode": "1.1", "status": "active"},
    {"activityExternalId": "ACT-102", "taskExternalId": "task-foundation",
     "title": "اجرای فونداسیون", "wbsCode": "1.2", "status": "active"},
    {"activityExternalId": "ACT-201", "taskExternalId": "task-floor1-slab",
     "title": "سقف طبقه اول", "wbsCode": "2.1", "status": "active"},
    {"activityExternalId": "ACT-202", "taskExternalId": "task-formwork",
     "title": "قالب‌بندی", "wbsCode": "2.2", "status": "active"},
    # Rebar fixing is its own activity, not a sub-task of formwork.
    #
    # It has to be, and the reason is worth recording: pairing a progress row to an estimate
    # line falls back to the activity code when the assignment id does not match, so two
    # lines sharing an activity both match anything recorded against it. With both labour
    # lines on ACT-202 a manual override entered for formwork silently applied to rebar
    # fixing as well, and the labour forecast came out 2.1 billion toman high. Splitting the
    # activity is the correct modelling either way; the pairing rule's behaviour when an
    # activity is genuinely shared is a separate, open question.
    {"activityExternalId": "ACT-203", "taskExternalId": "task-rebar-fixing",
     "title": "آرماتوربندی", "wbsCode": "2.3", "status": "active"},
    {"activityExternalId": "ACT-301", "taskExternalId": "task-walls",
     "title": "دیوارچینی", "wbsCode": "3.1", "status": "active"},
]

# id, resource, activity, assignment, original_quantity, original_unit_price_irr, source
#
# A quantified line carries a quantity and a unit price. A general-cost line is
# amount-based: no quantity, and its approved amount sits in original_unit_price_irr.
#
# Original totals by category, in toman:
#   material 36,000,000,000 · labour 15,000,000,000 · equipment 8,000,000,000
#   general 9,000,000,000  ->  68,000,000,000
ESTIMATE_LINES = [
    # Rebar appears on two activities, as it does on a real bill of quantities: the
    # foundation cage and the first-floor slab are separate pieces of work bought and
    # installed at different times, even though the material is one resource.
    (UUID("30000000-0000-4000-8000-000000000001"), REBAR, "ACT-102", "asg-foundation-rebar",
     Decimal("380000.0000"), T(29_000), "progress_feed"),
    (UUID("30000000-0000-4000-8000-000000000002"), CONCRETE, "ACT-201", "asg-floor1-concrete",
     Decimal("8600.0000"), T(1_450_000), "progress_feed"),
    (UUID("30000000-0000-4000-8000-000000000003"), BLOCK, "ACT-301", "asg-walls-block",
     Decimal("95000.0000"), T(42_000), "progress_feed"),
    (UUID("30000000-0000-4000-8000-000000000004"), CEMENT, "ACT-102", "asg-foundation-cement",
     Decimal("1200.0000"), T(1_300_000), "progress_feed"),
    (UUID("30000000-0000-4000-8000-000000000005"), FORMWORK, "ACT-202", "asg-labor-formwork",
     Decimal("240000.0000"), T(37_500), "progress_feed"),
    (UUID("30000000-0000-4000-8000-000000000006"), REBAR_TEAM, "ACT-203", "asg-labor-rebar",
     Decimal("150000.0000"), T(40_000), "progress_feed"),
    (UUID("30000000-0000-4000-8000-000000000007"), CRANE, "ACT-201", "asg-crane-floor1",
     Decimal("4000.0000"), T(1_250_000), "progress_feed"),
    (UUID("30000000-0000-4000-8000-000000000008"), EXCAVATOR, "ACT-101", "asg-excavation",
     Decimal("2500.0000"), T(1_200_000), "progress_feed"),
    (UUID("30000000-0000-4000-8000-000000000009"), PERMIT, "ACT-002", "asg-permit",
     None, T(5_200_000_000), "manual_entry"),
    (UUID("30000000-0000-4000-8000-000000000010"), INSURANCE, "ACT-002", "asg-insurance",
     None, T(3_800_000_000), "manual_entry"),
    (UUID("30000000-0000-4000-8000-000000000011"), REBAR, "ACT-201", "asg-slab-rebar",
     Decimal("240000.0000"), T(29_000), "progress_feed"),
]
LINE = {index: row[0] for index, row in enumerate(ESTIMATE_LINES, 1)}

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
#
# Revised estimate = revised quantity x the ORIGINAL unit price, so a revision moves the
# estimate by quantity alone. Totals by category, in toman:
#   material 38,498,000,000 · labour 15,800,000,000 · equipment 8,400,000,000
#   general 9,550,000,000  ->  72,248,000,000
#
# A general-cost revision restates an amount rather than a quantity, which is why its
# numbers are money.
ESTIMATE_REVISIONS = [
    (LINE[1], 1, Decimal("380000.0000"), Decimal("410000.0000"),
     "افزایش وزن آرماتور فونداسیون طبق نقشه اجرایی"),
    (LINE[2], 1, Decimal("8600.0000"), Decimal("8900.0000"),
     "افزایش حجم بتن سقف طبق متره اجرایی"),
    (LINE[3], 1, Decimal("95000.0000"), Decimal("105000.0000"),
     "اصلاح متراژ دیوارچینی پس از تغییر پلان"),
    (LINE[4], 1, Decimal("1200.0000"), Decimal("1460.0000"),
     "افزایش مصرف سیمان به دلیل بتن‌ریزی تکمیلی"),
    (LINE[5], 1, Decimal("240000.0000"), Decimal("252000.0000"),
     "افزایش ساعت قالب‌بندی طبق صورت‌جلسه کارگاه"),
    (LINE[6], 1, Decimal("150000.0000"), Decimal("158750.0000"),
     "افزایش ساعت آرماتوربندی متناسب با افزایش وزن میلگرد"),
    (LINE[7], 1, Decimal("4000.0000"), Decimal("4200.0000"),
     "تمدید اجاره جرثقیل برجی"),
    (LINE[8], 1, Decimal("2500.0000"), Decimal("2625.0000"),
     "افزایش ساعت بیل مکانیکی در خاکبرداری"),
    (LINE[9], 1, T(5_200_000_000), T(5_500_000_000),
     "افزایش عوارض شهرداری طبق ابلاغیه جدید"),
    (LINE[10], 1, T(3_800_000_000), T(4_050_000_000),
     "افزایش حق بیمه بر اساس مبلغ قرارداد بازنگری‌شده"),
    (LINE[11], 1, Decimal("240000.0000"), Decimal("255000.0000"),
     "افزایش وزن آرماتور سقف طبقه اول"),
]

# id, resource, scope_kind, version, unit_price_irr, effective_from
#
# The current price a report uses is the newest PROJECT-scoped version on or before the
# reporting date; an organization price applies only where the project has none. Versions
# are numbered per resource and scope.
#
# Movements are deliberately mixed, because a price trend chart where everything rises by
# the same amount teaches nothing: rebar +18%, crane +30%, formwork +22%, blocks +5%,
# cement down 3% then flat against its estimate, and one resource priced only at
# organization level.
PRICE_VERSIONS = [
    (UUID("50000000-0000-4000-8000-000000000001"), REBAR, "organization", 1,
     T(29_000), date(2026, 4, 1)),
    (UUID("50000000-0000-4000-8000-000000000002"), REBAR, "organization", 2,
     T(31_300), date(2026, 6, 1)),
    (UUID("50000000-0000-4000-8000-000000000003"), REBAR, "project", 1,
     T(34_220), date(2026, 7, 15)),

    (UUID("50000000-0000-4000-8000-000000000004"), CONCRETE, "organization", 1,
     T(1_450_000), date(2026, 4, 1)),
    (UUID("50000000-0000-4000-8000-000000000005"), CONCRETE, "project", 1,
     T(1_566_000), date(2026, 7, 1)),

    # Blocks are priced at organization level only, so the report falls back to that scope.
    (UUID("50000000-0000-4000-8000-000000000006"), BLOCK, "organization", 1,
     T(42_000), date(2026, 4, 1)),
    (UUID("50000000-0000-4000-8000-000000000007"), BLOCK, "organization", 2,
     T(44_100), date(2026, 7, 10)),

    # Cement rose, then came back down to exactly its estimated price: a line with zero
    # price variance, so the variance table has something other than increases in it.
    (UUID("50000000-0000-4000-8000-000000000008"), CEMENT, "organization", 1,
     T(1_340_000), date(2026, 4, 1)),
    (UUID("50000000-0000-4000-8000-000000000009"), CEMENT, "project", 1,
     T(1_300_000), date(2026, 7, 20)),

    (UUID("50000000-0000-4000-8000-000000000010"), FORMWORK, "organization", 1,
     T(37_500), date(2026, 4, 1)),
    (UUID("50000000-0000-4000-8000-000000000011"), FORMWORK, "project", 1,
     T(42_000), date(2026, 6, 20)),
    (UUID("50000000-0000-4000-8000-000000000012"), FORMWORK, "project", 2,
     T(45_750), date(2026, 7, 25)),

    (UUID("50000000-0000-4000-8000-000000000013"), REBAR_TEAM, "organization", 1,
     T(40_000), date(2026, 4, 1)),
    (UUID("50000000-0000-4000-8000-000000000014"), REBAR_TEAM, "project", 1,
     T(47_200), date(2026, 7, 5)),

    (UUID("50000000-0000-4000-8000-000000000015"), CRANE, "organization", 1,
     T(1_250_000), date(2026, 4, 1)),
    (UUID("50000000-0000-4000-8000-000000000016"), CRANE, "organization", 2,
     T(1_450_000), date(2026, 6, 15)),
    (UUID("50000000-0000-4000-8000-000000000017"), CRANE, "project", 1,
     T(1_625_000), date(2026, 7, 30)),

    (UUID("50000000-0000-4000-8000-000000000018"), EXCAVATOR, "organization", 1,
     T(1_200_000), date(2026, 4, 1)),
    (UUID("50000000-0000-4000-8000-000000000019"), EXCAVATOR, "project", 1,
     T(1_452_000), date(2026, 7, 12)),
]

# id, scope, version, source_unit, target_unit, dimension, factor, effective_from
UNIT_CONVERSIONS = [
    (UUID("55555555-5555-4555-8555-555555555551"), "organization", 1,
     "ton", "kg", "mass", Decimal("1000.00000000"), date(2026, 1, 1)),
    (UUID("55555555-5555-4555-8555-555555555552"), "organization", 1,
     "day", "hour", "equipment_time", Decimal("8.00000000"), date(2026, 1, 1)),
    (UUID("55555555-5555-4555-8555-555555555553"), "project", 2,
     "day", "hour", "equipment_time", Decimal("10.00000000"), date(2026, 7, 1)),
]

# ---------------------------------------------------------------- progress
#
# assignment, resource external id, name, type, unit, revised quantity, executed quantity,
# task external id, task name, wbs, activity code, task percent
#
# Executed quantities are what the site reported, not a fraction applied uniformly.
# Equipment and formwork run ahead of material installation, which is what a project looks
# like at this stage: the earthworks and the frame consume hours before the material they
# support is in place.
_FEED = [
    ("asg-foundation-rebar", "res-rebar", "میلگرد آجدار A3", "material", "kg",
     "410000.0000", "92000.0000", "task-foundation", "اجرای فونداسیون", "1.2", "ACT-102", "22.4400"),
    ("asg-slab-rebar", "res-rebar", "میلگرد آجدار A3", "material", "kg",
     "255000.0000", "46000.0000", "task-floor1-slab", "سقف طبقه اول", "2.1", "ACT-201", "18.0400"),
    ("asg-floor1-concrete", "res-concrete", "بتن آماده C30", "material", "m3",
     "8900.0000", "1869.0000", "task-floor1-slab", "سقف طبقه اول", "2.1", "ACT-201", "21.0000"),
    ("asg-walls-block", "res-block", "بلوک سفالی دیوارچینی", "material", "each",
     "105000.0000", "21000.0000", "task-walls", "دیوارچینی", "3.1", "ACT-301", "20.0000"),
    ("asg-foundation-cement", "res-cement", "سیمان تیپ ۲", "material", "ton",
     "1460.0000", "380.0000", "task-foundation", "اجرای فونداسیون", "1.2", "ACT-102", "26.0300"),
    ("asg-labor-formwork", "res-formwork-team", "اکیپ قالب‌بندی", "labor", "person_hour",
     "252000.0000", "105000.0000", "task-formwork", "قالب‌بندی", "2.2", "ACT-202", "41.6700"),
    ("asg-labor-rebar", "res-rebar-team", "اکیپ آرماتوربندی", "labor", "person_hour",
     "158750.0000", "66675.0000", "task-rebar-fixing", "آرماتوربندی", "2.3", "ACT-203", "42.0000"),
    ("asg-crane-floor1", "res-crane", "جرثقیل برجی", "equipment", "hour",
     "4200.0000", "1890.0000", "task-floor1-slab", "سقف طبقه اول", "2.1", "ACT-201", "45.0000"),
    ("asg-excavation", "res-excavator", "بیل مکانیکی", "equipment", "hour",
     "2625.0000", "1102.0000", "task-earthworks", "تجهیز کارگاه و خاکبرداری", "1.1", "ACT-101", "41.9800"),
]


def _row(entry, ratio=Decimal("1")):
    """One assignment as the host's progress feed states it.

    `ratio` scales the executed quantity for the earlier snapshots, so the three snapshots
    read as one site progressing rather than three unrelated reports.
    """
    (assignment, external, name, kind, unit, planned, actual,
     task_id, task_name, wbs, activity, percent) = entry
    executed = (Decimal(actual) * ratio).quantize(Decimal("0.0001"))
    remaining = Decimal(planned) - executed
    task_percent = (Decimal(percent) * ratio).quantize(Decimal("0.0001"))
    return {
        "assignmentExternalId": assignment, "resourceExternalId": external,
        "resourceName": name, "resourceType": kind, "unit": unit,
        "plannedQuantity": planned, "actualQuantity": format(executed, "f"),
        "remainingQuantity": format(remaining, "f"),
        # Work is left unstated. The host reports quantity here, and inventing an effort
        # figure beside it would invite the work-as-quantity fallback that
        # `domain/progress.py` exists to warn about.
        "plannedWork": None, "actualWork": None, "remainingWork": None,
        "assignmentWorkCompletePercent": None,
        "task": {"taskExternalId": task_id, "taskName": task_name, "wbsCode": wbs,
                 "activityCode": activity, "parentTaskExternalId": None,
                 "taskProgressPercent": format(task_percent, "f"),
                 "taskStart": "2026-06-01", "taskFinish": "2026-11-30"},
        "manualOverride": None,
    }


PROGRESS_SNAPSHOTS = [
    {"ref_id": UUID("33333333-3333-4333-8333-3333333331ff"),
     "progress_snapshot_id": UUID("33333333-3333-4333-8333-333333333331"),
     "source_file_version_id": UUID("44444444-4444-4444-8444-444444444441"),
     "source_file_name_safe": "sample-progress-v1.mpp",
     "reporting_date": date(2026, 7, 31),
     "host_snapshot_id": 9001, "host_file_version_id": 1001,
     "imported_at": datetime(2026, 8, 1, 8, 30, tzinfo=timezone.utc),
     "assignments": [_row(entry, Decimal("0.72")) for entry in _FEED[:6]]},
    {"ref_id": UUID("33333333-3333-4333-8333-3333333332ff"),
     "progress_snapshot_id": UUID("33333333-3333-4333-8333-333333333332"),
     "source_file_version_id": UUID("44444444-4444-4444-8444-444444444442"),
     "source_file_name_safe": "sample-progress-v2.mpp",
     "reporting_date": date(2026, 8, 1),
     "host_snapshot_id": 9002, "host_file_version_id": 1002,
     "imported_at": datetime(2026, 8, 2, 8, 30, tzinfo=timezone.utc),
     "assignments": [_row(entry, Decimal("0.9")) for entry in _FEED[:7]]},
    {"ref_id": UUID("33333333-3333-4333-8333-3333333333ff"),
     "progress_snapshot_id": UUID("33333333-3333-4333-8333-333333333333"),
     "source_file_version_id": UUID("44444444-4444-4444-8444-444444444443"),
     "source_file_name_safe": "sample-progress-v3.mpp",
     "reporting_date": date(2026, 8, 2),
     "host_snapshot_id": 9003, "host_file_version_id": 1003,
     "imported_at": datetime(2026, 8, 3, 8, 30, tzinfo=timezone.utc),
     "assignments": [_row(entry) for entry in _FEED]},
]

LATEST_SNAPSHOT = PROGRESS_SNAPSHOTS[-1]
SNAPSHOT_ID = LATEST_SNAPSHOT["progress_snapshot_id"]
REPORTING_DATE = LATEST_SNAPSHOT["reporting_date"]

# A site correction on the formwork line: the feed reported 105,000 hours, the site meeting
# established 110,880. The report uses the corrected figure and records who changed it and
# why -- which is the whole point of the override, and why it is not simply edited into the
# feed above.
PROGRESS_OVERRIDE = {
    "id": UUID("66666666-6666-4666-8666-666666666661"),
    "estimate_line_id": LINE[5],
    "progress_snapshot_ref_id": LATEST_SNAPSHOT["ref_id"],
    "computed_value": Decimal("105000.0000"),
    "override_value": Decimal("110880.0000"),
    "reason": "اصلاح ساعت قالب‌بندی طبق صورت‌جلسه شماره ۱۴ کارگاه",
    "created_by": UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2"),
    "created_at": datetime(2026, 8, 3, 9, 0, tzinfo=timezone.utc),
}

# ---------------------------------------------------------------- invoices
#
# Only `confirmed`, `voided` and `corrected` invoices reach the actual-cost figure, and a
# voided one carries a negative sign. So the batches below are what the report adds up:
#
#   material  13,181,532,000 toman     labour   4,800,000,000
#   equipment  2,300,000,000           general  2,700,000,000
#   total     22,981,532,000
#
# Material quantities matter twice. They are money, and they are also *stock*: a material
# line's remaining budget is what is left to buy, not what is left to install, so 400 tonnes
# of rebar already on site reduces the money still required even though it is not yet in the
# structure. That is the 2.5 billion difference between "remaining work" and "budget still
# required" on the dashboard.
#
# The purchase prices are below today's market on purpose -- rebar at 24,600 against a
# current 34,220. The project bought early, which is exactly why its forecast lands under
# its own revised estimate.
#
# resource, estimate line, count, quantity each, unit, final amount each (toman), vendor, note
INVOICE_BATCHES = [
    (REBAR, LINE[1], 5, "50000.0000", "kg", 1_230_000_000,
     "فولاد گستر نمونه", "تحویل میلگرد فونداسیون"),
    (REBAR, LINE[11], 3, "50000.0000", "kg", 1_230_000_000,
     "فولاد گستر نمونه", "تحویل میلگرد سقف"),
    (CONCRETE, LINE[2], 7, "267.0000", "m3", 301_176_000,
     "بتن آماده پایدار نمونه", "بتن‌ریزی سقف طبقه اول"),
    (BLOCK, LINE[3], 5, "6000.0000", "each", 190_500_000,
     "سفال و بلوک نمونه", "تحویل بلوک دیوارچینی"),
    (CEMENT, LINE[4], 3, "100.0000", "ton", 93_600_000,
     "سیمان پخش نمونه", "تحویل سیمان تیپ ۲"),
    (FORMWORK, LINE[5], 4, "15850.0000", "person_hour", 725_000_000,
     "پیمانکار قالب‌بندی نمونه", "صورت‌وضعیت قالب‌بندی"),
    (REBAR_TEAM, LINE[6], 2, "20000.0000", "person_hour", 950_000_000,
     "پیمانکار آرماتوربندی نمونه", "صورت‌وضعیت آرماتوربندی"),
    (CRANE, LINE[7], 2, "446.0000", "hour", 725_000_000,
     "اجاره ماشین‌آلات نمونه", "اجاره جرثقیل برجی"),
    (EXCAVATOR, LINE[8], 2, "293.0000", "hour", 425_000_000,
     "خاکبرداری نمونه", "اجاره بیل مکانیکی"),
    (PERMIT, LINE[9], 2, None, None, 800_000_000,
     "شهرداری منطقه نمونه", "پرداخت عوارض شهرداری"),
    (INSURANCE, LINE[10], 2, None, None, 550_000_000,
     "بیمه ساختمانی نمونه", "حق بیمه دوره‌ای پروژه"),
]

#: A reversal and its replacement, at the same amount, so the pair nets to nothing. The
#: lifecycle is real -- a voided document and the corrected one that replaced it -- and the
#: actual-cost figure is untouched by it, which is what a correct reversal should do.
REVERSAL_PAIRS = 4
REVERSAL_AMOUNT = 175_000_000
REVERSAL_QUANTITY = "5000.0000"

#: Neither status reaches the actual-cost figure. They exist so the invoice list has
#: something to filter, sort and page through.
DRAFT_COUNT = 5
AWAITING_COUNT = 3
PENDING_AMOUNT = 320_000_000
PENDING_QUANTITY = "9000.0000"
