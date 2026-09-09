# -*- coding: utf-8 -*-
r"""TEST_ONLY. Read a Google Sheet of daily material prices and see how far it gets.

    ..\..\..\.venv312\Scripts\python -m scripts.test_only.price_sheet_probe --url "<sheet url>"
    ..\..\..\.venv312\Scripts\python -m scripts.test_only.price_sheet_probe --csv sample.csv \
        --db postgresql://postgres@127.0.0.1:5432/bambo_price_sheet_test --import --runs 2

WHAT THIS IS FOR

Finding out whether a sheet CAN become a price source, without any of it becoming one. It
discovers the sheet's columns rather than assuming them, turns each row into one canonical
record, says why a record is or is not usable, and -- only against a database named on the
command line, never the project's -- proves the row survives a round trip into
`price_observations`.

WHAT IT WILL NOT DO

  * write to `bambo_canonical_test`, or to anything in `FORBIDDEN_DATABASES`. The live
    database is read exactly twice, both times SELECT: the resource catalogue for the
    mapping dry run, and nothing else.
  * map an item to a Finance resource by name. A name is not an identity; the dry run
    reports EXACT only when a unit agrees as well, and everything else is AMBIGUOUS or
    NO_MATCH with the reason attached.
  * invent a column, a unit, a currency or a date. What the sheet does not state is None,
    and a record missing something required is reported INVALID rather than repaired.
  * create a provider, an item or a mapping in the live database, or a `price_versions`
    row anywhere. A price version is a person's decision; this only prepares observations.
"""

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

LIVE_DSN = "postgresql://postgres@127.0.0.1:5432/bambo_canonical_test"

#: Databases this script refuses to write to, whatever the arguments say. The live local
#: database is on the list: a discovery run must not be able to leave a row in it.
FORBIDDEN_DATABASES = frozenset({"bambo", "bambo_canonical_local", "bambo_canonical_test"})

#: The read-only ways a Google Sheet can be fetched, most specific first. All of them are
#: tried, because which one works is itself the answer to "how is this sheet shared?".
EXPORT_FORMS = (
    ("export csv", "https://docs.google.com/spreadsheets/d/{id}/export?format=csv&gid={gid}"),
    ("gviz csv", "https://docs.google.com/spreadsheets/d/{id}/gviz/tq?tqx=out:csv&gid={gid}"),
    ("published csv", "https://docs.google.com/spreadsheets/d/{id}/pub?gid={gid}&single=true&output=csv"),
)

#: Words a header may use for the same thing, lower-cased and stripped. Used ONLY to
#: propose a meaning for a discovered column -- never to require one, and never to rename
#: anything: the sheet's own header text travels into `raw_data` untouched.
HEADER_HINTS = {
    "price": ("قیمت", "price", "نرخ", "مبلغ", "قیمت روز", "بها"),
    "unit": ("واحد", "unit", "واحد فروش"),
    "currency": ("ارز", "currency", "واحد پول"),
    "name": ("عنوان", "نام", "name", "title", "شرح", "کالا", "محصول"),
    # Before `provider`, deliberately: a header like "زمان آپدیت شده توسط سایت" contains
    # the word "سایت" and would otherwise be read as naming the seller.
    "time": ("زمان", "ساعت", "time", "updated"),
    "provider": ("منبع", "provider", "تامین کننده", "تأمین‌کننده", "فروشنده", "سایت", "source"),
    "url": ("url", "لینک", "آدرس", "link"),
    "date": ("تاریخ", "date", "observed_at", "زمان", "تاریخ اعلام"),
    "category": ("گروه", "دسته", "category", "نوع", "کتگوری"),
}

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


# ------------------------------------------------------------------ phase 1: the sheet
def sheet_identity(url):
    """The spreadsheet id and gid a URL names, or (None, None)."""
    found = re.search(r"/spreadsheets/d/([A-Za-z0-9-_]+)", url or "")
    gid = re.search(r"[#&?]gid=(\d+)", url or "")
    return (found.group(1) if found else None), (gid.group(1) if gid else "0")


def fetch_sheet(url, timeout=45):
    """Every read-only form, reported. Returns (text, which form worked, attempts)."""
    identifier, gid = sheet_identity(url)
    attempts = []
    if identifier is None:
        return None, None, [("url", "not a spreadsheet URL", None)]
    for label, template in EXPORT_FORMS:
        target = template.format(id=identifier, gid=gid)
        try:
            with urllib.request.urlopen(target, timeout=timeout) as answer:
                body = answer.read()
                kind = answer.headers.get("Content-Type", "")
                attempts.append((label, "HTTP %s %s" % (answer.status, kind), len(body)))
                if "text/csv" in kind or "text/plain" in kind:
                    return body.decode("utf-8-sig"), label, attempts
        except urllib.error.HTTPError as error:
            body = error.read()
            hint = ""
            if b"accounts.google.com" in body or b"Sign in" in body:
                hint = " (a Google sign-in page: the sheet is not readable without an account)"
            attempts.append((label, "HTTP %s%s" % (error.code, hint), len(body)))
        except Exception as error:                                # noqa: BLE001
            attempts.append((label, "%s: %s" % (type(error).__name__, error), None))
    return None, None, attempts


# ------------------------------------------------ phases 2-4: columns and the record
def discover_columns(rows, header):
    """What each column looks like, from the sheet's own values. No column is required."""
    described = []
    for index, name in enumerate(header):
        values = [row[index] for row in rows if index < len(row) and (row[index] or "").strip()]
        sample = values[0] if values else None
        described.append({
            "column": name,
            "example": sample,
            "filled": len(values),
            "type": detect_type(values),
            "likely_meaning": propose_meaning(name),
            "presence": ("required" if len(values) == len(rows) and rows
                         else "optional" if values else "unknown"),
        })
    return described


def detect_type(values):
    if not values:
        return "unknown"
    if all(parse_number(value) is not None for value in values):
        return "number"
    if all(parse_date(value) is not None for value in values):
        return "date"
    return "text"


def propose_meaning(name):
    text = (name or "").strip().lower()
    for meaning, words in HEADER_HINTS.items():
        for word in words:
            if word in text:
                return meaning
    return None


def parse_number(value):
    """A number the sheet states, in Persian or Latin digits, or None."""
    if value is None:
        return None
    text = str(value).translate(_DIGITS)
    text = re.sub(r"[,٬\s ]", "", text).replace("٫", ".")
    if not re.fullmatch(r"-?\d+(\.\d+)?", text or ""):
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def parse_clock(value):
    """A time of day the sheet states, in Persian or Latin digits, or None."""
    text = str(value or "").translate(_DIGITS).strip()
    found = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", text)
    if not found:
        return None
    hour, minute, second = int(found.group(1)), int(found.group(2)), int(found.group(3) or 0)
    if hour > 23 or minute > 59 or second > 59:
        return None
    return "%02d:%02d:%02d" % (hour, minute, second)


def parse_date(value):
    """An ISO or Jalali-looking date, as text plus a flag. None when it is neither."""
    if not value:
        return None
    text = str(value).translate(_DIGITS).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}([ T].*)?", text):
        return {"text": text, "calendar": "gregorian"}
    if re.fullmatch(r"1[34]\d{2}[/-]\d{1,2}[/-]\d{1,2}", text):
        return {"text": text, "calendar": "jalali"}
    return None


def canonical_record(row, header, meanings, sheet_url, category_default=None):
    """One sheet row as the canonical test object. Nothing is guessed; raw_data is whole."""
    raw = {header[index]: (row[index] if index < len(row) else None)
           for index in range(len(header))}

    def by_meaning(meaning):
        column = meanings.get(meaning)
        return None if column is None else (raw.get(column) or None)

    price_text = by_meaning("price")
    time_text = by_meaning("time")
    price = parse_number(price_text)
    observed = parse_date(by_meaning("date"))
    if observed is not None and time_text:
        clock = parse_clock(time_text)
        if clock:
            observed = dict(observed, time=clock)
    known = {meanings[key] for key in meanings if meanings[key]}
    metadata = {name: value for name, value in raw.items()
                if name not in known and (value or "").strip()}
    return {
        "category": by_meaning("category") or category_default,
        "provider": by_meaning("provider"),
        "provider_item_name": by_meaning("name"),
        "observed_at": observed,
        "price": None if price is None else str(price),
        "currency": by_meaning("currency"),
        "source_unit": by_meaning("unit"),
        # Left None deliberately: normalising a unit needs the registry's opinion, and the
        # registry is Finance's, not the sheet's. `coreint.mpp_units` does that work when
        # a real integration asks it to.
        "normalized_unit": None,
        "source_url": by_meaning("url") or sheet_url,
        "metadata": metadata,
        "raw_data": raw,
    }


# ------------------------------------------------------------------ phase 5: validation
REQUIRED = ("price", "provider_item_name", "source_url")


def validate(record):
    """VALID / AMBIGUOUS / INVALID, with the reasons that decided it."""
    reasons = []
    for field in REQUIRED:
        if not record.get(field):
            reasons.append("%s is missing" % field)
    if reasons:
        return "INVALID", reasons
    # A zero is kept, not corrected and not thrown away: the sheet said zero, and whether
    # that means "free" or "nobody filled this in" is a person's call, not a parser's.
    if Decimal(record["price"]) == 0:
        reasons.append("price is zero; a zero price needs a person to confirm it")
    elif Decimal(record["price"]) < 0:
        return "INVALID", ["price is negative"]
    if not record.get("currency"):
        reasons.append("currency is not stated; IRR vs TOMAN cannot be assumed")
    if not record.get("source_unit"):
        reasons.append("unit is not stated")
    if not record.get("observed_at"):
        reasons.append("observation date is not stated")
    if not record.get("provider"):
        reasons.append("provider is not stated")
    if not record.get("category"):
        reasons.append("category is not stated")
    return ("AMBIGUOUS", reasons) if reasons else ("VALID", [])


#: What the sheet's own currency word means to the column, which only accepts these two.
#: A word not on this list is NOT quietly read as rials -- the record says so instead.
CURRENCY_WORDS = {"irr": "IRR", "ریال": "IRR", "﷼": "IRR",
                  "toman": "TOMAN", "تومان": "TOMAN", "تومن": "TOMAN"}


def currency_of(record, assumed=None):
    """The currency, as the sheet spells it -- or as an operator explicitly supplied it.

    `assumed` is never a default and never inferred from the size of the numbers. It is a
    person on the command line saying "this sheet is in toman", and when it is used the
    observation records that it was: the reason travels with the row, so nobody later reads
    a supplied currency as a stated one.
    """
    text = (record.get("currency") or "").strip().lower()
    return CURRENCY_WORDS.get(text) or assumed


def normalized_irr(record, assumed=None):
    """The price in rials, or None.

    None whenever the stated currency is anything but rials. Toman x10 is a conversion,
    and this mission introduces none: an unconverted number in a column named `_irr` would
    be wrong by a factor of ten and look right.
    """
    if currency_of(record, assumed) != "IRR" or record.get("price") is None:
        return None
    return Decimal(record["price"])


def item_identity(record):
    """What the thing IS, with no price and no date in it.

    A price is something an item HAS on a day, not part of what it is; keying the item on
    the price made the same rebar a new item every time the market moved. The extra
    attributes the sheet carries (a weight, a size, a grade) belong here, because on this
    sheet two rows share a name and are told apart only by one of them.
    """
    parts = [str(record.get("provider") or ""), str(record.get("provider_item_name") or "")]
    for key in sorted((record.get("metadata") or {})):
        parts.append("%s=%s" % (key, record["metadata"][key]))
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def observation_identity(record):
    """WHEN that item was seen at WHAT price -- the observation, not the item."""
    moment = record.get("observed_at") or {}
    parts = [item_identity(record), str(moment.get("text") or ""), str(moment.get("time") or ""),
             str(record.get("price") or ""), str(record.get("source_url") or "")]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


# --------------------------------------------------------- phase 7: the mapping dry run
def mapping_dry_run(records, dsn=LIVE_DSN):
    """Candidates only, read-only, and never on the strength of a name alone."""
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(dsn, row_factory=dict_row, connect_timeout=10) as db:
        resources = db.execute(
            "SELECT id, code, title, base_unit, resource_type FROM finance_resources "
            "WHERE deleted_at IS NULL ORDER BY code").fetchall()
    report = []
    for record in records:
        name = (record.get("provider_item_name") or "").strip()
        unit = (record.get("source_unit") or "").strip()
        if not name:
            report.append({"item": None, "verdict": "NO_MATCH",
                           "reason": "the row names no item", "candidates": []})
            continue
        by_name = [r for r in resources if name and name in (r["title"] or "")]
        same_unit = [r for r in by_name if unit and (r["base_unit"] or "") == unit]
        if len(same_unit) == 1:
            verdict, reason = "EXACT", "one resource shares the item's name AND its unit"
        elif by_name:
            verdict = "AMBIGUOUS"
            reason = ("%d resource(s) share the name; a name alone is not an identity"
                      % len(by_name))
        else:
            verdict, reason = "NO_MATCH", "no resource carries this name"
        report.append({
            "item": name, "unit": unit or None, "verdict": verdict, "reason": reason,
            "candidates": [{"code": r["code"], "title": r["title"], "unit": r["base_unit"]}
                           for r in (same_unit or by_name)[:5]],
        })
    return report


# --------------------------------------------- phases 8-9: the temporary database only
PROVIDER_SQL = """
    INSERT INTO price_providers (id, organization_id, project_id, name, domain, description,
                                 provider_type, crawl_method, active, default_interval_minutes)
    VALUES (%(id)s, %(org)s, %(project)s, %(name)s, %(domain)s,
            'TEST ONLY -- google sheet discovery run', 'website', 'json', false, 1440)
    ON CONFLICT (organization_id, project_id, domain) DO NOTHING
"""

ITEM_SQL = """
    INSERT INTO provider_items (id, organization_id, project_id, provider_id, external_id,
                                external_name, category, url, source_unit, metadata)
    VALUES (%(id)s, %(org)s, %(project)s, %(provider_id)s, %(external_id)s, %(name)s,
            %(category)s, %(url)s, %(unit)s, %(metadata)s)
    ON CONFLICT (organization_id, project_id, provider_id, external_id) DO NOTHING
"""

RUN_SQL = """
    INSERT INTO price_collection_runs (id, organization_id, project_id, provider_id,
                                       started_at, finished_at, status, total_items,
                                       successful_items, failed_items)
    VALUES (%(id)s, %(org)s, %(project)s, %(provider_id)s, %(started)s, %(finished)s,
            %(status)s, %(total)s, %(ok)s, %(failed)s)
"""

OBSERVATION_SQL = """
    INSERT INTO price_observations (id, organization_id, project_id, provider_id,
        provider_item_id, collection_run_id, raw_price, normalized_price_irr,
        source_currency, source_unit, normalized_unit, source_url, observed_at, fetched_at,
        availability, validation_status, validation_reasons, raw_data)
    VALUES (%(id)s, %(org)s, %(project)s, %(provider_id)s, %(item_id)s, %(run_id)s,
            %(raw_price)s, %(price_irr)s, %(currency)s, %(unit)s, NULL, %(url)s,
            %(observed_at)s, %(fetched_at)s, 'unknown', %(status)s, %(reasons)s, %(raw)s)
"""


def import_into(dsn, records, organization, project, now, assumed_currency=None):
    """Insert one collection run's worth of observations into a NAMED test database."""
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
    with psycopg.connect(dsn, row_factory=dict_row, connect_timeout=10) as db:
        name = db.execute("SELECT current_database() AS d").fetchone()["d"]
        if name in FORBIDDEN_DATABASES:
            raise SystemExit("STOP: %r is not a database this script may write to." % name)
        counters = {"providers": 0, "items": 0, "observations": 0,
                    "skipped_duplicate": 0, "skipped_no_currency": 0,
                    "same_moment_conflict": 0}
        runs = {}
        with db.transaction():
            for record in records:
                provider_name = (record.get("provider") or "google-sheet").strip()
                domain = "sheet:" + hashlib.sha1(provider_name.encode()).hexdigest()[:12]
                db.execute(PROVIDER_SQL, {"id": str(uuid4()), "org": organization,
                                          "project": project, "name": provider_name,
                                          "domain": domain})
                provider = db.execute(
                    "SELECT id FROM price_providers WHERE organization_id=%s AND project_id=%s "
                    "AND domain=%s", (organization, project, domain)).fetchone()
                counters["providers"] += 1
                external_id = item_identity(record)[:32]
                db.execute(ITEM_SQL, {
                    "id": str(uuid4()), "org": organization, "project": project,
                    "provider_id": provider["id"], "external_id": external_id,
                    "name": record.get("provider_item_name") or "(unnamed)",
                    "category": record.get("category") or "unknown",
                    "url": record.get("source_url") or "sheet://unknown",
                    "unit": record.get("source_unit"),
                    "metadata": Jsonb(record.get("metadata") or {})})
                item = db.execute(
                    "SELECT id FROM provider_items WHERE organization_id=%s AND project_id=%s "
                    "AND provider_id=%s AND external_id=%s",
                    (organization, project, provider["id"], external_id)).fetchone()
                counters["items"] += 1
                # ONE run per provider per pass. A run is "this collection, this time";
                # one per row would make the run table a copy of the observation table.
                run_id = runs.get(provider["id"])
                if run_id is None:
                    run_id = runs[provider["id"]] = str(uuid4())
                    db.execute(RUN_SQL, {"id": run_id, "org": organization,
                                         "project": project, "provider_id": provider["id"],
                                         "started": now, "finished": now,
                                         "status": "succeeded", "total": 0, "ok": 0,
                                         "failed": 0})
                # The identity under test: the same row, seen again, is not a new fact.
                already = db.execute("""
                    SELECT 1 FROM price_observations
                     WHERE organization_id=%s AND project_id=%s AND provider_item_id=%s
                       AND raw_price=%s AND source_url=%s AND observed_at=%s
                """, (organization, project, item["id"], str(record.get("price")),
                      record.get("source_url") or "sheet://unknown",
                      record["_observed_at"])).fetchone()
                if already:
                    counters["skipped_duplicate"] += 1
                    continue
                # The same item, the same moment, a different price. Both are kept -- the
                # sheet really says both -- and the disagreement is counted, not resolved.
                conflict = db.execute("""
                    SELECT 1 FROM price_observations
                     WHERE organization_id=%s AND project_id=%s AND provider_item_id=%s
                       AND observed_at=%s AND raw_price <> %s
                """, (organization, project, item["id"], record["_observed_at"],
                      str(record.get("price")))).fetchone()
                if conflict:
                    counters["same_moment_conflict"] += 1
                status, reasons = validate(record)
                if not record.get("currency") and assumed_currency:
                    reasons = reasons + ["currency was not stated in the sheet; %s was "
                                         "supplied on the command line" % assumed_currency]
                currency = currency_of(record, assumed_currency)
                if currency is None:
                    # The column accepts IRR or TOMAN and nothing else. A row stating
                    # neither cannot be stored honestly, so it is counted, not guessed.
                    counters["skipped_no_currency"] += 1
                    continue
                db.execute(OBSERVATION_SQL, {
                    "id": str(uuid4()), "org": organization, "project": project,
                    "provider_id": provider["id"], "item_id": item["id"], "run_id": run_id,
                    "raw_price": str(record.get("price")),
                    "price_irr": normalized_irr(record, assumed_currency),
                    "currency": currency,
                    "unit": record.get("source_unit"),
                    "url": record.get("source_url") or "sheet://unknown",
                    "observed_at": record["_observed_at"], "fetched_at": now,
                    "status": {"VALID": "valid", "AMBIGUOUS": "needs_review",
                               "INVALID": "rejected"}[status],
                    "reasons": Jsonb(reasons), "raw": Jsonb(record.get("raw_data") or {})})
                counters["observations"] += 1
                db.execute("UPDATE price_collection_runs SET total_items = total_items + 1, "
                           "successful_items = successful_items + 1 WHERE id = %s", (run_id,))
    return counters


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", help="the Google Sheet URL to probe")
    parser.add_argument("--csv", help="read this local CSV instead (offline mechanics test)")
    parser.add_argument("--db", help="a TEST database DSN; without it nothing is written")
    parser.add_argument("--import", dest="do_import", action="store_true")
    parser.add_argument("--runs", type=int, default=1, help="import this many times")
    parser.add_argument("--assume-currency", choices=("IRR", "TOMAN"),
                        help="the currency for rows that state none. Not a guess and not a "
                             "default: whoever passes it is asserting it, and every row "
                             "stored under it says so in its validation reasons.")
    parser.add_argument("--organization", default="c4ee6a23-b2a8-4afe-94c8-63baba552ca4")
    parser.add_argument("--project", default="terrace")
    parser.add_argument("--category", default=None, help="category when the sheet states none")
    parser.add_argument("--live-dsn", default=LIVE_DSN)
    arguments = parser.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    text, form, attempts = (None, None, [])
    if arguments.csv:
        text, form = io.open(arguments.csv, encoding="utf-8-sig").read(), "local csv"
    elif arguments.url:
        print("\n  PHASE 1 -- ACCESS")
        text, form, attempts = fetch_sheet(arguments.url)
        for label, outcome, size in attempts:
            print("    %-16s %s%s" % (label, outcome, "" if size is None else "  (%d bytes)" % size))
    else:
        parser.error("give --url or --csv")
    if text is None:
        print("\n  NOT READABLE. Nothing further can be discovered, and nothing is assumed.")
        return 2
    print("    read via: %s" % form)

    rows = [row for row in csv.reader(io.StringIO(text))]
    rows = [row for row in rows if any((cell or "").strip() for cell in row)]
    if not rows:
        print("  the sheet is empty")
        return 2
    header, body = rows[0], rows[1:]
    print("\n  PHASE 2 -- COLUMNS (%d data rows)" % len(body))
    described = discover_columns(body, header)
    meanings = {}
    for column in described:
        if column["likely_meaning"] and column["likely_meaning"] not in meanings:
            meanings[column["likely_meaning"]] = column["column"]
        print("    %-22s example=%-18s type=%-8s meaning=%-9s %s"
              % (column["column"][:22], str(column["example"])[:18], column["type"],
                 column["likely_meaning"] or "-", column["presence"]))

    records = [canonical_record(row, header, meanings, arguments.url or arguments.csv,
                                arguments.category) for row in body]
    print("\n  PHASE 4 -- CANONICAL RECORDS (first three)")
    for record in records[:3]:
        print("    " + json.dumps(record, ensure_ascii=False)[:400])

    print("\n  PHASE 5 -- VALIDATION")
    tally = {"VALID": 0, "AMBIGUOUS": 0, "INVALID": 0}
    for record in records:
        status, reasons = validate(record)
        tally[status] += 1
        record["_status"], record["_reasons"] = status, reasons
        observed = record.get("observed_at")
        record["_observed_at"] = None
        if observed and observed["calendar"] == "gregorian":
            stamp = observed["text"].split(" ")[0]
            if observed.get("time"):
                stamp = stamp + "T" + observed["time"]
            record["_observed_at"] = datetime.fromisoformat(
                stamp.replace(" ", "T")).replace(tzinfo=timezone.utc)
    print("    VALID=%(VALID)d  AMBIGUOUS=%(AMBIGUOUS)d  INVALID=%(INVALID)d" % tally)
    for record in records[:5]:
        if record["_reasons"]:
            print("      %-28s %s: %s" % (str(record.get("provider_item_name"))[:28],
                                          record["_status"], "; ".join(record["_reasons"])))

    print("\n  PHASE 7 -- MAPPING DRY RUN (read-only against the live catalogue)")
    try:
        for line in mapping_dry_run(records, arguments.live_dsn)[:8]:
            print("    %-28s %-10s %s" % (str(line["item"])[:28], line["verdict"], line["reason"]))
    except Exception as error:                                    # noqa: BLE001
        print("    could not read the catalogue: %s" % error)

    if arguments.do_import:
        if not arguments.db:
            parser.error("--import needs --db pointing at a test database")
        print("\n  PHASES 8-9 -- IMPORT INTO THE TEST DATABASE, %d time(s)" % arguments.runs)
        usable = [r for r in records if r["_status"] != "INVALID"]
        for attempt in range(1, arguments.runs + 1):
            counters = import_into(arguments.db, usable, arguments.organization,
                                   arguments.project, datetime.now(timezone.utc),
                                   arguments.assume_currency)
            print("    pass %d: observations=%d  duplicates skipped=%d  "
                  "unstated currency skipped=%d  same-moment price conflicts=%d"
                  % (attempt, counters["observations"], counters["skipped_duplicate"],
                     counters["skipped_no_currency"], counters["same_moment_conflict"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
