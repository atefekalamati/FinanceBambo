# -*- coding: utf-8 -*-
"""The five things a daily price must state, and the specifications beside it.

Against a real PostgreSQL, because most of what is claimed here is a property of the
DATABASE -- a constraint refusing a weight with no basis, an immutability trigger refusing
to rewrite an old observation, a unique index refusing a duplicate. A test double would
only prove the double agreed with the test.

The database is the one `scripts/test_only/prepare_material_price_test_db.py` builds. Its
name is checked after connecting, so no environment variable can aim these at a database
that matters.
"""

import asyncio
import os
import sys
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

DATABASE = "bambo_material_price_test"
DSN = os.environ.get("FINANCE_MATERIAL_PRICE_DSN",
                     "postgresql://postgres@127.0.0.1:5432/" + DATABASE)
PREPARE = "python -m scripts.test_only.prepare_material_price_test_db"

ORG = UUID("11111111-1111-4111-8111-111111111111")
OTHER_ORG = UUID("22222222-2222-4222-8222-222222222222")
ACTOR = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")


def connect():
    try:
        db = psycopg.connect(DSN, row_factory=dict_row)
    except Exception as error:                                         # noqa: BLE001
        raise unittest.SkipTest("no disposable database; run %s (%s)" % (PREPARE, error))
    name = db.execute("select current_database() n").fetchone()["n"]
    if name != DATABASE:
        db.close()
        raise unittest.SkipTest("refusing to run against %r" % name)
    return db


class TypedAttributeTests(unittest.TestCase):
    """What provider_items will and will not accept."""

    @classmethod
    def setUpClass(cls):
        cls.db = connect()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def setUp(self):
        self.project = "spec-" + uuid4().hex[:8]
        self.provider = uuid4()
        self.db.execute(
            "insert into price_providers (id, organization_id, project_id, name, domain,"
            " provider_type, crawl_method, active, default_interval_minutes)"
            " values (%s,%s,%s,'AhanOnline','e.test','spreadsheet','google_sheet',true,1440)",
            (self.provider, ORG, self.project))
        self.db.commit()

    def tearDown(self):
        self.db.rollback()

    def item(self, **columns):
        """Insert one listing, returning it, or raise whatever the database raised."""
        base = {"id": uuid4(), "organization_id": ORG, "project_id": self.project,
                "provider_id": self.provider, "external_id": uuid4().hex[:10],
                "external_name": "a product", "category": "angle",
                "url": "https://e.test/p", "metadata": Jsonb({}), "active": True}
        base.update(columns)
        names = ", ".join(base)
        marks = ", ".join(["%s"] * len(base))
        row = self.db.execute(
            "insert into provider_items (%s) values (%s) returning *" % (names, marks),
            list(base.values())).fetchone()
        return row

    # ------------------------------------------------------------ 15, 16, 17, 18, 20

    def test_15_every_specification_may_be_null(self):
        row = self.item()
        for column in ("product_code", "manufacturer", "grade", "product_type",
                       "dimensions_text", "length_value", "length_m",
                       "width_value", "height_value", "thickness_value", "diameter_value",
                       "weight_kg", "weight_basis", "branch_count",
                       "pieces_per_package", "coverage_m2", "volume_m3"):
            self.assertIsNone(row[column], column)

    def test_16_17_18_a_weight_a_length_and_a_thickness_land_in_their_own_columns(self):
        row = self.item(weight_kg=Decimal("27"), weight_basis="branch",
                        length_value=Decimal("6"), length_m=Decimal("6"),
                        thickness_value=Decimal("4"))
        self.assertEqual(Decimal("27"), row["weight_kg"])
        self.assertEqual(Decimal("6"), row["length_m"])
        self.assertEqual(Decimal("4"), row["thickness_value"])

    def test_20_a_missing_specification_is_null_and_never_zero(self):
        row = self.item(weight_kg=Decimal("27"), weight_basis="unknown")
        self.assertIsNone(row["thickness_value"])
        self.assertIsNone(row["length_value"])
        self.assertNotEqual(Decimal("0"), row["thickness_value"])

    def test_19_a_weight_cannot_be_stored_without_a_basis(self):
        # An unknown basis is a value a conversion must refuse; NO basis is a number that
        # means nothing at all, and the database will not hold one.
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.item(weight_kg=Decimal("27"))
        self.db.rollback()

    def test_a_measurement_must_be_positive_and_finite(self):
        for columns in ({"weight_kg": Decimal("-1"), "weight_basis": "piece"},
                        {"weight_kg": Decimal("0"), "weight_basis": "piece"},
                        {"thickness_value": Decimal("0")},
                        {"branch_count": Decimal("0")},
                        {"weight_kg": Decimal("NaN"), "weight_basis": "piece"}):
            with self.assertRaises(psycopg.errors.CheckViolation, msg=str(columns)):
                self.item(**columns)
            self.db.rollback()

    def test_there_is_no_unit_column_left_to_disagree_with_the_value(self):
        """0034 removed the pair. These two tests used to guard `weight_unit` -- that a
        unit needed a value, and that it had to be a registry code -- and both questions
        stop existing once the only weight column IS its unit.

        What replaces them is stronger than either: a stored weight cannot be in the wrong
        unit, because there is nowhere to say a unit.
        """
        columns = [row["column_name"] for row in self.db.execute(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_name='provider_items' AND column_name LIKE 'weight%'"
            " ORDER BY 1").fetchall()]
        self.assertEqual(["weight_basis", "weight_kg"], columns)

    def test_an_unlisted_weight_basis_is_refused(self):
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.item(weight_kg=Decimal("5"), weight_basis="per-lorry")
        self.db.rollback()

    def test_21_an_unrecognised_attribute_stays_in_metadata(self):
        row = self.item(metadata=Jsonb({"چیز تازه": "۵", "قیمت در هر مترمربع": "526500"}))
        self.assertEqual({"چیز تازه": "۵", "قیمت در هر مترمربع": "526500"}, row["metadata"])

    def test_26_27_tenant_and_project_are_part_of_identity(self):
        external = uuid4().hex[:10]
        self.item(external_id=external)
        # The same external id in another project is a different listing, not a clash.
        other_project = self.project + "-b"
        other_provider = uuid4()
        self.db.execute(
            "insert into price_providers (id, organization_id, project_id, name, domain,"
            " provider_type, crawl_method, active, default_interval_minutes)"
            " values (%s,%s,%s,'AhanOnline','e.test','spreadsheet','google_sheet',true,1440)",
            (other_provider, ORG, other_project))
        other = self.item(external_id=external, project_id=other_project,
                          provider_id=other_provider)
        self.assertIsNotNone(other["id"])
        # ...and in the same project it is the same listing.
        with self.assertRaises(psycopg.errors.UniqueViolation):
            self.item(external_id=external)
        self.db.rollback()


class ObservationTests(unittest.TestCase):
    """What a price observation must state, and what may never be changed about it."""

    @classmethod
    def setUpClass(cls):
        cls.db = connect()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def setUp(self):
        self.project = "obs-" + uuid4().hex[:8]
        self.provider = uuid4()
        self.run = uuid4()
        self.db.execute(
            "insert into price_providers (id, organization_id, project_id, name, domain,"
            " provider_type, crawl_method, active, default_interval_minutes)"
            " values (%s,%s,%s,'AhanOnline','e.test','spreadsheet','google_sheet',true,1440)",
            (self.provider, ORG, self.project))
        self.item_id = uuid4()
        self.db.execute(
            "insert into provider_items (id, organization_id, project_id, provider_id,"
            " external_id, external_name, category, url, metadata, active)"
            " values (%s,%s,%s,%s,%s,'a product','angle','https://e.test/p','{}',true)",
            (self.item_id, ORG, self.project, self.provider, uuid4().hex[:10]))
        self.db.execute(
            "insert into price_collection_runs (id, organization_id, project_id,"
            " provider_id, status, started_at) values (%s,%s,%s,%s,'succeeded',now())",
            (self.run, ORG, self.project, self.provider))
        self.db.commit()

    def tearDown(self):
        self.db.rollback()

    def observe(self, **columns):
        base = {"id": uuid4(), "organization_id": ORG, "project_id": self.project,
                "provider_id": self.provider, "provider_item_id": self.item_id,
                "collection_run_id": self.run, "raw_price": "913600",
                "normalized_price_irr": Decimal("913600"), "source_currency": "TOMAN",
                "source_url": "https://e.test/p", "observed_at": datetime(2026, 9, 14, tzinfo=timezone.utc),
                "fetched_at": datetime(2026, 9, 16, tzinfo=timezone.utc),
                "availability": "unknown", "validation_status": "valid",
                "validation_reasons": Jsonb([]), "raw_data": Jsonb({}),
                "observed_at_source": "workflow_date",
                "workflow_date_raw": "1405/06/23", "workflow_date_jalali": "1405/06/23",
                "workflow_date_gregorian": date(2026, 9, 14),
                "product_external_id": "REBAR-1",
                "product_name_snapshot": "میلگرد آجدار ۱۰",
                "provider_name_snapshot": "AhanOnline",
                "row_fingerprint": uuid4().hex}
        base.update(columns)
        names = ", ".join(base)
        marks = ", ".join(["%s"] * len(base))
        return self.db.execute(
            "insert into price_observations (%s) values (%s) returning *" % (names, marks),
            list(base.values())).fetchone()

    # ------------------------------------------------------------- the mandatory five

    def test_1_a_row_stating_all_five_is_accepted(self):
        row = self.observe()
        self.assertEqual(Decimal("913600"), row["normalized_price_irr"])
        self.assertEqual(date(2026, 9, 14), row["workflow_date_gregorian"])
        self.assertEqual("REBAR-1", row["product_external_id"])
        self.assertEqual("میلگرد آجدار ۱۰", row["product_name_snapshot"])
        self.assertEqual("AhanOnline", row["provider_name_snapshot"])

    def test_2_a_row_with_no_provider_cannot_exist(self):
        with self.assertRaises(psycopg.errors.NotNullViolation):
            self.observe(provider_id=None)
        self.db.rollback()

    def test_3_4_a_valid_row_must_name_the_product_it_priced(self):
        for columns in ({"product_external_id": None}, {"product_external_id": "  "},
                        {"product_name_snapshot": None}, {"product_name_snapshot": ""},
                        {"provider_name_snapshot": None}):
            with self.assertRaises(psycopg.errors.CheckViolation, msg=str(columns)):
                self.observe(**columns)
            self.db.rollback()

    def test_5_6_a_valid_row_must_carry_a_usable_price(self):
        for columns in ({"normalized_price_irr": None},
                        {"normalized_price_irr": Decimal("-1")},
                        {"normalized_price_irr": Decimal("NaN")}):
            with self.assertRaises(psycopg.errors.CheckViolation, msg=str(columns)):
                self.observe(**columns)
            self.db.rollback()

    def test_11_a_zero_price_is_a_price_and_is_not_a_null(self):
        row = self.observe(normalized_price_irr=Decimal("0"), raw_price="0")
        self.assertEqual(Decimal("0"), row["normalized_price_irr"])
        self.assertIsNotNone(row["normalized_price_irr"])

    def test_7_a_valid_row_must_state_its_business_date(self):
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.observe(workflow_date_gregorian=None)
        self.db.rollback()

    def test_7b_a_rejected_row_keeps_its_unreadable_date_as_evidence(self):
        # The reason the rule is written against the status rather than as a column NOT
        # NULL: a row rejected BECAUSE its date could not be read has no date to store,
        # and refusing the row would push the importer into inventing one.
        row = self.observe(validation_status="rejected", workflow_date_gregorian=None,
                           workflow_date_jalali=None, workflow_date_raw="۱۴۰۵/۱۳/۴۵",
                           normalized_price_irr=None)
        self.assertEqual("۱۴۰۵/۱۳/۴۵", row["workflow_date_raw"])
        self.assertIsNone(row["workflow_date_gregorian"])

    def test_9_10_the_fetch_time_and_today_are_not_the_business_date(self):
        row = self.observe()
        self.assertNotEqual(row["fetched_at"].date(), row["workflow_date_gregorian"])
        self.assertNotEqual(date.today(), row["workflow_date_gregorian"])
        # And the column that says which one `observed_at` followed still says so.
        self.assertEqual("workflow_date", row["observed_at_source"])

    def test_12_the_jalali_and_gregorian_forms_are_the_same_day(self):
        from app.finance.domain.material_price_rows import parse_workflow_date
        raw, jalali, gregorian = parse_workflow_date("1405/06/23")
        self.assertEqual("1405/06/23", raw)
        self.assertEqual("1405/06/23", jalali)
        self.assertEqual(date(2026, 9, 14), gregorian)

    def test_13_persian_and_arabic_digits_are_read(self):
        from app.finance.domain.material_price_rows import parse_workflow_date
        # And the RAW text keeps the digits the sheet used, so the original is not lost.
        raw, jalali, gregorian = parse_workflow_date("۱۴۰۵/۰۶/۲۳")
        self.assertEqual("۱۴۰۵/۰۶/۲۳", raw)
        self.assertEqual("1405/06/23", jalali)
        self.assertEqual(date(2026, 9, 14), gregorian)
        self.assertEqual(date(2026, 9, 14), parse_workflow_date("١٤٠٥/٠٦/٢٣")[2])

    def test_14_an_impossible_jalali_date_yields_no_gregorian_date(self):
        from app.finance.domain.material_price_rows import parse_workflow_date
        # «۱۴۰۵/۰۶/۳۲» used to become 2026-09-23 by rolling over: Shahrivar has 31 days, and
        # a price dated to a day that does not exist was filed nine days late.
        for text in ("1405/13/01", "1405/06/32", "1405/07/31", "1405/12/30",
                     "1405/01/00", "not a date", ""):
            self.assertIsNone(parse_workflow_date(text)[2], text)

    def test_14b_the_unreadable_original_is_still_kept(self):
        from app.finance.domain.material_price_rows import parse_workflow_date
        raw, _jalali, gregorian = parse_workflow_date("۱۴۰۵/۰۶/۳۲")
        self.assertEqual("۱۴۰۵/۰۶/۳۲", raw)
        self.assertIsNone(gregorian)

    # --------------------------------------------------------- immutability and identity

    def test_22_the_same_row_cannot_be_observed_twice(self):
        fingerprint = uuid4().hex
        self.observe(row_fingerprint=fingerprint)
        with self.assertRaises(psycopg.errors.UniqueViolation):
            self.observe(row_fingerprint=fingerprint)
        self.db.rollback()

    def test_22b_the_same_source_row_may_reach_two_projects(self):
        # 1,606 fingerprints in the audited database are exactly this: one sheet imported
        # into two projects. A globally unique index would have made that impossible.
        fingerprint = uuid4().hex
        self.observe(row_fingerprint=fingerprint)
        other_project = self.project + "-b"
        other_provider = uuid4()
        self.db.execute(
            "insert into price_providers (id, organization_id, project_id, name, domain,"
            " provider_type, crawl_method, active, default_interval_minutes)"
            " values (%s,%s,%s,'AhanOnline','e.test','spreadsheet','google_sheet',true,1440)",
            (other_provider, ORG, other_project))
        other_item = uuid4()
        other_run = uuid4()
        self.db.execute(
            "insert into provider_items (id, organization_id, project_id, provider_id,"
            " external_id, external_name, category, url, metadata, active)"
            " values (%s,%s,%s,%s,%s,'a product','angle','https://e.test/p','{}',true)",
            (other_item, ORG, other_project, other_provider, uuid4().hex[:10]))
        self.db.execute(
            "insert into price_collection_runs (id, organization_id, project_id,"
            " provider_id, status, started_at) values (%s,%s,%s,%s,'succeeded',now())",
            (other_run, ORG, other_project, other_provider))
        row = self.observe(project_id=other_project, provider_id=other_provider,
                           collection_run_id=other_run,
                           provider_item_id=other_item, row_fingerprint=fingerprint)
        self.assertIsNotNone(row["id"])

    def test_24_an_observation_cannot_be_changed_or_deleted(self):
        row = self.observe()
        self.db.commit()
        with self.assertRaises(psycopg.errors.RaiseException):
            self.db.execute("update price_observations set normalized_price_irr=1 where id=%s",
                            (row["id"],))
        self.db.rollback()
        with self.assertRaises(psycopg.errors.RaiseException):
            self.db.execute("delete from price_observations where id=%s", (row["id"],))
        self.db.rollback()

    def test_25_a_later_rename_does_not_reach_the_snapshot(self):
        row = self.observe(product_name_snapshot="میلگرد آجدار ۱۰",
                           provider_name_snapshot="AhanOnline")
        self.db.commit()
        self.db.execute("update provider_items set external_name='a different name'"
                        " where id=%s", (self.item_id,))
        self.db.execute("update price_providers set name='a different supplier'"
                        " where id=%s and project_id=%s", (self.provider, self.project))
        self.db.commit()
        after = self.db.execute("select product_name_snapshot, provider_name_snapshot"
                                " from price_observations where id=%s",
                                (row["id"],)).fetchone()
        self.assertEqual("میلگرد آجدار ۱۰", after["product_name_snapshot"])
        self.assertEqual("AhanOnline", after["provider_name_snapshot"])


if __name__ == "__main__":
    unittest.main()
