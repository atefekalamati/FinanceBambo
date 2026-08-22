"""Realistic development data for a single construction project.

Figures are chosen so every screen has something meaningful to render: prices that
moved after the estimate was approved, quantities executed beyond and below plan,
a general cost that overran, invoices in several states, and one estimate line
deliberately left without a current price so the incomplete-calculation path is
visible rather than theoretical.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

ORGANIZATION_ID = UUID("11111111-1111-4111-8111-111111111111")
PROJECT_ID = "sample_site_01"
ACTOR_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
SNAPSHOT_ID = UUID("70000000-0000-4000-8000-000000000001")
SNAPSHOT_REF_ID = UUID("70000000-0000-4000-8000-0000000000ff")

REPORTING_DATE = date(2026, 8, 20)
NOW = datetime(2026, 8, 20, 8, 0, tzinfo=timezone.utc)


def _uuid(prefix: str, index: int) -> UUID:
    return UUID(f"{prefix}-0000-4000-8000-{index:012d}")


RESOURCES = [
    # id, type, code, title, base_unit, dimension
    (_uuid("20000000", 1), "material", "MAT-CEM", "سیمان تیپ ۲", "kg", "mass"),
    (_uuid("20000000", 2), "material", "MAT-REB", "میلگرد آجدار A3", "kg", "mass"),
    (_uuid("20000000", 3), "material", "MAT-BLK", "بلوک سبک دیواری", "each", "count"),
    (_uuid("20000000", 4), "labor", "LAB-MAS", "بنّای ماهر", "hour", "time"),
    (_uuid("20000000", 5), "labor", "LAB-HLP", "کارگر ساده", "hour", "time"),
    (_uuid("20000000", 6), "equipment", "EQP-CRN", "جرثقیل برجی", "hour", "time"),
    (_uuid("20000000", 7), "general_cost", "GEN-INS", "بیمه کارگاه", None, None),
    (_uuid("20000000", 8), "general_cost", "GEN-PRM", "عوارض و مجوز شهرداری", None, None),
]

ACTIVITIES = [
    {"activityExternalId": "ACT-001", "taskExternalId": "ACT-001",
     "title": "اسکلت بتنی طبقات", "wbsCode": "1.2.1", "status": "active"},
    {"activityExternalId": "ACT-002", "taskExternalId": "ACT-002",
     "title": "دیوارچینی داخلی", "wbsCode": "1.3.2", "status": "active"},
    {"activityExternalId": "ACT-003", "taskExternalId": "ACT-003",
     "title": "تجهیز و پشتیبانی کارگاه", "wbsCode": "1.1.4", "status": "active"},
]

# id, resource, activity, assignment, original_quantity, original_unit_price_irr
ESTIMATE_LINES = [
    (_uuid("30000000", 1), RESOURCES[0][0], "ACT-001", "ASG-001", Decimal("420000"), Decimal("4200")),
    (_uuid("30000000", 2), RESOURCES[1][0], "ACT-001", "ASG-002", Decimal("96000"), Decimal("38000")),
    (_uuid("30000000", 3), RESOURCES[2][0], "ACT-002", "ASG-003", Decimal("18500"), Decimal("62000")),
    (_uuid("30000000", 4), RESOURCES[3][0], "ACT-001", "ASG-004", Decimal("7200"), Decimal("950000")),
    (_uuid("30000000", 5), RESOURCES[4][0], "ACT-002", "ASG-005", Decimal("5400"), Decimal("520000")),
    # No current price is seeded for the crane, so the report must report itself incomplete.
    (_uuid("30000000", 6), RESOURCES[5][0], "ACT-001", "ASG-006", Decimal("1400"), Decimal("2800000")),
    (_uuid("30000000", 7), RESOURCES[6][0], "ACT-003", None, None, Decimal("1850000000")),
    (_uuid("30000000", 8), RESOURCES[7][0], "ACT-003", None, None, Decimal("940000000")),
]

# resource, scope, version, price, effective_from  (latest effective row wins)
PRICE_VERSIONS = [
    (RESOURCES[0][0], "organization", 1, Decimal("4200"), date(2026, 3, 1)),
    (RESOURCES[0][0], "organization", 2, Decimal("4850"), date(2026, 6, 1)),
    (RESOURCES[0][0], "project", 3, Decimal("5100"), date(2026, 7, 15)),
    (RESOURCES[1][0], "organization", 1, Decimal("38000"), date(2026, 3, 1)),
    (RESOURCES[1][0], "organization", 2, Decimal("44500"), date(2026, 7, 1)),
    (RESOURCES[2][0], "organization", 1, Decimal("62000"), date(2026, 3, 1)),
    (RESOURCES[2][0], "project", 2, Decimal("59000"), date(2026, 6, 20)),
    (RESOURCES[3][0], "organization", 1, Decimal("950000"), date(2026, 3, 1)),
    (RESOURCES[3][0], "organization", 2, Decimal("1120000"), date(2026, 7, 1)),
    (RESOURCES[4][0], "organization", 1, Decimal("520000"), date(2026, 3, 1)),
    (RESOURCES[4][0], "organization", 2, Decimal("610000"), date(2026, 7, 1)),
]

# source_unit, target_unit, dimension, factor
UNIT_CONVERSIONS = [
    ("ton", "kg", "mass", Decimal("1000")),
    ("bag", "kg", "mass", Decimal("50")),
    ("pallet", "each", "count", Decimal("120")),
]

# Assignment feed: quantities the progress module reports for this snapshot.
PROGRESS_ASSIGNMENTS = [
    {"assignmentExternalId": "ASG-001", "plannedQuantity": "420000", "actualQuantity": "268000",
     "manualOverride": None, "task": {"activityCode": "ACT-001", "taskProgressPercent": "64"}},
    {"assignmentExternalId": "ASG-002", "plannedQuantity": "96000", "actualQuantity": "71500",
     "manualOverride": None, "task": {"activityCode": "ACT-001", "taskProgressPercent": "74"}},
    # Executed beyond the approved quantity: drives the overrun warning.
    {"assignmentExternalId": "ASG-003", "plannedQuantity": "18500", "actualQuantity": "19240",
     "manualOverride": None, "task": {"activityCode": "ACT-002", "taskProgressPercent": "104"}},
    {"assignmentExternalId": "ASG-004", "plannedQuantity": "7200", "actualQuantity": "4980",
     "manualOverride": None, "task": {"activityCode": "ACT-001", "taskProgressPercent": "69"}},
    # No actual reported: resolution falls back to the task percentage.
    {"assignmentExternalId": "ASG-005", "plannedQuantity": "5400", "actualQuantity": None,
     "manualOverride": None, "task": {"activityCode": "ACT-002", "taskProgressPercent": "55"}},
    {"assignmentExternalId": "ASG-006", "plannedQuantity": "1400", "actualQuantity": "860",
     "manualOverride": None, "task": {"activityCode": "ACT-001", "taskProgressPercent": "61"}},
]

# invoice_id, number, date, vendor, source, status, discount, tax, shipping, other, sign
INVOICES = [
    (_uuid("40000000", 1), "INV-1405-0121", date(2026, 5, 12), "سیمان آبیک", "manual", "confirmed",
     Decimal("0"), Decimal("84000000"), Decimal("12000000"), Decimal("0"), 1),
    (_uuid("40000000", 2), "INV-1405-0163", date(2026, 6, 3), "فولاد کاوه", "manual", "confirmed",
     Decimal("55000000"), Decimal("196000000"), Decimal("0"), Decimal("0"), 1),
    (_uuid("40000000", 3), "INV-1405-0188", date(2026, 6, 28), "بلوک سازان پارس", "manual", "confirmed",
     Decimal("0"), Decimal("41000000"), Decimal("8000000"), Decimal("0"), 1),
    (_uuid("40000000", 4), "INV-1405-0201", date(2026, 7, 6), "پیمانکار نیروی انسانی البرز", "manual", "confirmed",
     Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), 1),
    (_uuid("40000000", 5), "INV-1405-0233", date(2026, 7, 19), "بیمه ایران", "manual", "confirmed",
     Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), 1),
    # General cost booked above its revised estimate: drives GENERAL_COST_OVERRUN.
    (_uuid("40000000", 6), "INV-1405-0244", date(2026, 7, 30), "شهرداری منطقه ۵", "manual", "confirmed",
     Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), 1),
    (_uuid("40000000", 7), "INV-1405-0250", date(2026, 8, 2), "سیمان آبیک", "manual", "awaitingConfirmation",
     Decimal("0"), Decimal("9000000"), Decimal("0"), Decimal("0"), 1),
    (_uuid("40000000", 8), "INV-1405-0207", date(2026, 7, 9), "فولاد کاوه", "manual", "draft",
     Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), 1),
]

# invoice, estimate_line, resource, quantity, unit, unit_price, raw_amount
INVOICE_LINES = [
    (INVOICES[0][0], ESTIMATE_LINES[0][0], RESOURCES[0][0], Decimal("240"), "bag", Decimal("242500"), Decimal("58200000")),
    (INVOICES[1][0], ESTIMATE_LINES[1][0], RESOURCES[1][0], Decimal("62"), "ton", Decimal("44500000"), Decimal("2759000000")),
    (INVOICES[2][0], ESTIMATE_LINES[2][0], RESOURCES[2][0], Decimal("11200"), "each", Decimal("59000"), Decimal("660800000")),
    (INVOICES[3][0], ESTIMATE_LINES[3][0], RESOURCES[3][0], Decimal("4980"), "hour", Decimal("1120000"), Decimal("5577600000")),
    (INVOICES[4][0], ESTIMATE_LINES[6][0], RESOURCES[6][0], None, None, None, Decimal("1420000000")),
    (INVOICES[5][0], ESTIMATE_LINES[7][0], RESOURCES[7][0], None, None, None, Decimal("1080000000")),
    (INVOICES[6][0], ESTIMATE_LINES[0][0], RESOURCES[0][0], Decimal("40"), "bag", Decimal("242500"), Decimal("9700000")),
    (INVOICES[7][0], ESTIMATE_LINES[1][0], RESOURCES[1][0], Decimal("5"), "ton", Decimal("44500000"), Decimal("222500000")),
]

GROSS_BUILT_AREA = Decimal("14250.0000")
