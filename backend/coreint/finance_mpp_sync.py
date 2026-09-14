# -*- coding: utf-8 -*-
"""Reading a schedule file into Finance's OWN tables. No MSP table is touched or needed.

This is the Finance half of the shared reader's output. The MSP importer writes `msp_*`
from the same parse; this writes `finance_mpp_source_versions` and `finance_mpp_rows`, and
neither knows about the other. A deployment running Finance alone has this and nothing
else, and every number a Finance report needs from the schedule is recoverable from these
two tables months later.

IDEMPOTENCE IS THE FILE'S HASH
A version is one row per distinct file CONTENT. Re-reading unchanged bytes finds the
existing version and writes nothing; changed bytes make a new version and leave the old one
intact, so a report issued against the old content stays reproducible.

QUANTITY
`quantity` is written only when the schedule states an APPROVED quantity column -- an alias
the planners agreed means exactly that. Nothing else becomes a quantity: not work, not a
duration, not a cost, not a percentage, and not a custom column that merely holds a number.
The file in front of us states no such column, so every row's quantity is NULL and the
report says so instead of inventing one.
"""

import logging
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4

from psycopg.rows import dict_row

from .finance_quantity import _decimal, approved_quantity
from .mpp_units import normalize_unit
from .mpp_files import MppFileError, resolve_import_file

LOG = logging.getLogger("coreint.finance_mpp_sync")


class FinanceMppSyncRefused(RuntimeError):
    """A sync that must not proceed. ``code`` is the stable API contract."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def finance_rows(parsed, *, source_sha256=None, recorded_decision=None):
    """Finance-relevant rows from a parsed file, keyed by the file's own identifiers.

    One row per assignment, plus one row per task that has no assignment at all. The
    second kind is what names a WBS stage: summary tasks carry no resources, so without
    them the report knows a stage exists but not what it is called. They hold no
    assignment and no resource, and the feed is built only from rows that name an
    assignment, so they label the tree without entering any sum.

    The MSP identifiers travel as data; no database identity from any module appears.

    `recorded_decision` is what a person decided about THIS file's amounts, read from
    `finance_mpp_currency_decisions` and handed in: 'toman', 'rial', 'unknown', or None
    when nobody has decided. It arrives as a parameter rather than being looked up, so
    this function stays pure and a test can state every case without a database.
    """
    tasks = {task["uid"]: task for task in parsed.tasks if task["uid"] is not None}
    resources = {r["uid"]: r for r in parsed.resources if r["uid"] is not None}
    currency_scale = _currency_scale(parsed, source_sha256, recorded_decision)

    def base(task):
        metrics = task.get("metrics") or {}
        quantity, unit = approved_quantity(task)
        return {
            "source_task_uid": task["uid"],
            "task_name": task["name"],
            "task_wbs": task["wbs"],
            # As the file states them. No timezone is invented for a wall-clock date.
            "task_start": task.get("start"),
            "task_finish": task.get("finish"),
            "quantity": quantity,
            "quantity_unit": unit,
            "progress_variance": _decimal(metrics.get("progress_variance")),
            "weight_rial": _decimal(metrics.get("weight_rial")),
            "weight_time": _decimal(metrics.get("weight_time")),
            "weight_base": _decimal(metrics.get("weight_base")),
            "actual_progress": _decimal(metrics.get("actual_progress")),
            "actual_progress_percent": _decimal(metrics.get("actual_progress_percent")),
            "physical_progress": _decimal(metrics.get("physical_progress")),
            "planned_progress": _decimal(metrics.get("planned_progress")),
            # The SCHEDULE's own cost. Finance actual cost comes from confirmed
            # invoices; the prefix is what keeps the two from being read as one.
            "source_cost": _decimal(metrics.get("task_cost")),
            "source_actual_cost": _decimal(metrics.get("task_actual_cost")),
            "source_fixed_cost": _decimal(metrics.get("task_fixed_cost")),
            # The same figure in the unit Finance counts in. The raw column above is the
            # file's own number and stays that way; this one has been through the same
            # currency decision the assignment cost passes through, so the two amounts on
            # one row can finally be added together. Read by the mapper, never summed
            # across rows without de-duplicating by task: like `source_cost`, a task's
            # fixed cost is repeated on every row the task has.
            "source_fixed_cost_irr": _file_fixed_cost_rials(
                metrics.get("task_fixed_cost"), currency_scale),
            # Absent here on purpose. These belong to an assignment, and a task that has
            # none -- a stage heading -- has none of them either. The loop below fills them
            # for the rows that do.
            "source_assignment_units": None,
            "source_assignment_cost_irr": None,
            "normalized_unit": None,
            "unit_source": None,
            "unit_confidence": None,
            "source_material_quantity": None,
            "source_resource_rate_irr": None,
            "source_rate_basis": None,
        }

    rows = []
    assigned = set()
    if parsed.assignments:
        for assignment in parsed.assignments:
            task = tasks.get(assignment["task_uid"])
            if task is None:
                continue
            resource = resources.get(assignment["resource_uid"]) or {}
            row = base(task)
            unit_code, unit_source, unit_confidence = normalize_unit(
                resource.get("quantity_unit"))
            row.update({
                "source_assignment_uid": assignment["assignment_uid"],
                "source_resource_uid": assignment["resource_uid"],
                # THIS assignment's figures. The task's stay in `source_cost`, where they
                # are the task's: a reader wanting what one item costs had nowhere to look,
                # and summing the task's figure across its items counted it once per item.
                "source_assignment_units": _file_units(assignment.get("units")),
                "source_assignment_cost_irr": _file_rials(assignment.get("cost"), currency_scale),
                # The PHYSICAL quantity, from the file's own Material field -- not derived
                # from units, work, duration or cost, none of which state a quantity.
                "source_material_quantity": _file_quantity(assignment.get("planned_quantity")),
                # What one of those units costs, per the resource's standard rate.
                "source_resource_rate_irr": _file_rate_rials(resource.get("standard_rate"),
                                                             currency_scale),
                # ...and whether the file's own arithmetic proves the rate is per unit.
                "source_rate_basis": _rate_basis(resource, assignment),
                # What the file's own unit text was recognised as, and how sure that is.
                "normalized_unit": unit_code,
                "unit_source": unit_source,
                "unit_confidence": unit_confidence,
                "resource_name": resource.get("name"),
                "resource_type": resource.get("native_type"),
                # The resource's own unit -- never the approved quantity's, which is
                # `quantity_unit` and belongs to a different number.
                "resource_unit": (resource.get("quantity_unit")
                                  or resource.get("material_label")
                                  or resource.get("initials")),
            })
            rows.append(row)
            assigned.add(task["uid"])

    # A row for every task that produced none above. A summary task carries no resource
    # assignment -- MS Project rolls its children up instead -- so it was absent from
    # Finance entirely, and the WBS report had no name for the stage it heads: the page
    # showed the bare code "1.5" where "اجرای عملیات سیویل" belongs. These rows exist to
    # carry that name.
    #
    # They state NO assignment and NO resource, which is what they are, and that is also
    # what keeps them out of the calculation: `FinanceRowsProgressProvider` builds feed
    # rows only from rows that name an assignment, so a stage heading can never pair with
    # an estimate line or contribute an executed quantity. It is a label, and it is stored
    # as one.
    for task in parsed.tasks:
        if task["uid"] is None or task["uid"] in assigned:
            continue
        row = base(task)
        row.update({"source_assignment_uid": None, "source_resource_uid": None,
                    "resource_name": None, "resource_type": None,
                    "resource_unit": None, "source_material_quantity": None,
                    "source_resource_rate_irr": None, "source_rate_basis": None})
        rows.append(row)
    return rows


#: MPXJ returns assignment units scaled by a hundred: 56000.0 where the file shows 560,
#: 751640.0 where it shows 7516.4. Verified against the project's own MS Project dialog on
#: five of five rows. The stored number is the one the file shows.
_UNITS_SCALE = Decimal(100)

#: The file states `currencySymbol = تومان` and `currencyCode = IRR`, which disagree; its
#: amounts match the toman figures the dialog shows. Finance stores rials, so the amount is
#: multiplied by ten here and the column may honestly be called `_irr`. Dividing by ten
#: recovers the file's own number.
_TOMAN_TO_RIAL = Decimal(10)

#: The toman decision belongs to exact bytes, never to "any file that says تومان".
#:
#: Two entries, because the same schedule reached this project as two files: MS Project
#: rewrote the container (1,638,400 bytes and 1,518,592 bytes) without changing a figure.
#: Compared assignment by assignment, the pair agree on all 727 costs, all 727 material
#: quantities, all 727 actual quantities and all 81 standard rates, and state the same
#: Status Date -- so one decision covers both, and it is recorded rather than guessed.
#:
#: A THIRD file does not inherit this. Adding a sha here is a statement that somebody read
#: that file's amounts and found them to be toman.
_APPROVED_TOMAN_SHA256 = frozenset({
    "b86b63738f592bfd90286ab08daedcea4374d815c02a7503adc18182cec6e908",
    "9792d658aed54efa0f397cccf73b9e1f55623f73fa0e0062643f62d8132520f3",
})


def _currency_scale(parsed, source_sha256, recorded_decision=None):
    """What to multiply the file's amounts by to get rials, or None to leave costs null.

    Three sources, in this order, and the order is the point:

      1. A decision a person recorded for exactly these bytes, in
         `finance_mpp_currency_decisions`. First because it is the most specific thing
         anybody knows about this file, and because it carries evidence, an author and a
         date -- none of which a constant in this file can.
      2. The two shas approved in code. Kept, and still authoritative for those two files:
         moving them would mean an existing, reviewed decision stopped applying the moment
         a table was empty.
      3. A file that states rials plainly, with nothing to disagree about.

    Anything else returns None, and None means the costs stay null. A file saying تومان
    with code IRR and no recorded decision is the case this whole function exists for:
    believing the symbol stores toman as rial and every cost is a tenth of the truth;
    believing the code does the opposite.
    """
    symbol = str(getattr(parsed, "currency_symbol", None) or "").strip()
    code = str(getattr(parsed, "currency_code", None) or "").strip().upper()

    if recorded_decision == "toman":
        return _TOMAN_TO_RIAL
    if recorded_decision == "rial":
        return Decimal(1)
    if recorded_decision == "unknown":
        # Somebody looked and could not tell. That is a finding, and it outranks the
        # guess the plain-rial branch below would otherwise make.
        return None

    if (source_sha256 in _APPROVED_TOMAN_SHA256
            and symbol == "تومان" and code == "IRR"):
        return _TOMAN_TO_RIAL
    if code == "IRR" and symbol in ("", "IRR", "ریال", "﷼"):
        return Decimal(1)
    # Unknown/conflicting currency is not an IRR amount. Null costs may still pass.
    return None


#: How far the file's own multiplication may drift before it stops being a proof. MPXJ
#: hands back doubles, so 3538.11 x 800000 arrives as 2830488000.0000005; a millionth is
#: far wider than that and far narrower than any real disagreement.
_RATE_TOLERANCE = Decimal("0.000001")

#: The one rate meaning this reader can prove. Named rather than boolean because a second
#: basis (a per-hour rate, a per-use charge) would be a different value here, not a flag.
MATERIAL_UNIT_RATE = "material_unit"


def _rate_basis(resource, assignment):
    """Whether the resource's rate may be read as the price of one material unit.

    The file never says so; it says a quantity, a rate and a cost, and when those three
    multiply out the rate is per unit and nothing else fits. A WORK resource is refused
    before the arithmetic: MS Project's rate for one is per hour, and this project's are
    all zero anyway. Anything unproven returns None, and None means "not an estimate
    basis" everywhere downstream -- never "zero" and never "assume it".
    """
    if (resource.get("native_type") or "").upper() != "MATERIAL":
        return None
    quantity = _decimal(assignment.get("planned_quantity"))
    rate = _decimal(resource.get("standard_rate"))
    cost = _decimal(assignment.get("cost"))
    if quantity is None or rate is None or cost is None or rate == 0:
        return None
    product = quantity * rate
    if cost == 0:
        # A free line is provable too, but only if the numbers agree that it is free.
        return MATERIAL_UNIT_RATE if product == 0 else None
    if abs(product - cost) / abs(cost) <= _RATE_TOLERANCE:
        return MATERIAL_UNIT_RATE
    return None


#: How many decimals of a physical quantity are the file's own. MPXJ hands back doubles, so
#: the quantity a planner typed as 3538.11 arrives as 3538.1100000000006 and 2299 arrives as
#: 2298.999999999999. Six places keep every digit anyone types into MS Project and drop the
#: tail the double added; the number stored is then the number the file shows.
_QUANTITY_PLACES = Decimal("0.000001")


def _file_quantity(value):
    """The physical quantity the file states, without the double's rounding tail."""
    number = _decimal(value)
    if number is None:
        return None
    quantized = number.quantize(_QUANTITY_PLACES, rounding=ROUND_HALF_UP)
    # `normalize` drops trailing zeros; the `+ 0` keeps 1E+3 from being how 1000 is spelt.
    return quantized.normalize() + Decimal(0)


def _file_rate_rials(value, currency_scale=None):
    """A per-unit rate in whole rials. Money is whole here, and a rate is money."""
    number = _file_rials(value, currency_scale)
    return None if number is None else number.quantize(Decimal(1), rounding=ROUND_HALF_UP)


def _file_units(value):
    """The units the file shows for an assignment, or None when it states none."""
    number = _decimal(value)
    return None if number is None else number / _UNITS_SCALE


def _file_rials(value, currency_scale=None):
    """The assignment's cost in rials. Not a price: a price is per unit and a person enters
    it. Not an actual cost either: that comes from a confirmed invoice."""
    number = _decimal(value)
    if number is None:
        return None
    if currency_scale is None:
        raise FinanceMppSyncRefused(
            "MPP_CURRENCY_UNRESOLVED",
            "assignment currency needs an explicit decision for this source file")
    return number * currency_scale


def _file_fixed_cost_rials(value, currency_scale):
    """The task's own fixed cost in rials, or None when the file states none.

    Zero is exempt from the currency decision, and only zero: nothing is nothing in every
    currency, and MS Project writes 0.0 here for every task nobody entered a fixed cost on
    -- which is almost all of them. Refusing a whole file over those would make an
    undecided currency fatal to schedules that state no task money at all, which is a
    stricter rule than the one the amounts themselves are held to. Any other amount goes
    through exactly the decision the assignment cost goes through, and refuses the same way.
    """
    number = _decimal(value)
    if number is None or number == 0:
        return number
    return _file_rials(number, currency_scale)


_COLUMNS = ("source_task_uid", "source_assignment_uid", "source_resource_uid",
            "task_name", "task_wbs", "task_start", "task_finish",
            "resource_name", "resource_type", "resource_unit",
            "quantity", "quantity_unit",
            "weight_rial", "weight_time", "weight_base", "actual_progress",
            "actual_progress_percent", "physical_progress", "planned_progress",
            "progress_variance",
            "source_cost", "source_actual_cost", "source_fixed_cost",
            "source_fixed_cost_irr",
            "source_assignment_units", "source_assignment_cost_irr",
            "normalized_unit", "unit_source", "unit_confidence",
            "source_material_quantity", "source_resource_rate_irr", "source_rate_basis")

_INSERT_ROW = (
    "INSERT INTO finance_mpp_rows (id, organization_id, project_id, source_version_id, "
    + ", ".join(_COLUMNS) + ") VALUES ("
    + ", ".join(["%s"] * (4 + len(_COLUMNS))) + ")")


class FinanceMppSyncService:
    """Reads the project's schedule file into Finance's own tables, atomically."""

    async def periodic_tick(self):
        """Sync every Finance project whose file is staged. Never raises.

        A project "has MPP active" when ``<project_id>.mpp`` sits under the configured root,
        exactly as the MSP importer decides it -- but the project list is FINANCE'S: the
        (organization, project) pairs in ``finance_project_settings``, not the host's
        ``projects`` table, so a Finance-only deployment ticks without any MSP schema.
        An unchanged file costs one hash and writes nothing; one project's failure never
        stops the next.
        """
        from pathlib import Path
        root = Path(self._import_root) if self._import_root else None
        if root is None or not root.is_dir():
            return []
        outcomes = []
        for candidate in sorted(root.glob("*.mpp")):
            project_id = candidate.stem
            try:
                async with await self._connect() as connection:
                    async with connection.cursor(row_factory=dict_row) as cursor:
                        await cursor.execute(
                            "SELECT DISTINCT organization_id FROM finance_project_settings "
                            "WHERE project_id = %s", (project_id,))
                        scopes = await cursor.fetchall()
                if not scopes:
                    continue                    # a stray file is not a Finance project
                for scope in scopes:
                    outcome = await self.sync(str(scope["organization_id"]), project_id)
                    outcomes.append({"projectId": project_id,
                                     "organizationId": str(scope["organization_id"]),
                                     "status": outcome["status"],
                                     "rowCount": outcome["rowCount"]})
            except FinanceMppSyncRefused as refused:
                outcomes.append({"projectId": project_id, "status": "refused",
                                 "code": refused.code})
            except Exception as error:                                 # noqa: BLE001
                LOG.exception("finance mpp periodic sync failed project=%s", project_id)
                outcomes.append({"projectId": project_id, "status": "failed",
                                 "code": "FINANCE_MPP_SYNC_CRASHED"})
        return outcomes

    def __init__(self, connection_factory, reader, *, import_root, max_size_mb=100,
                 id_factory=uuid4):
        self._connect = connection_factory
        self._reader = reader
        self._import_root = import_root
        self._max_size_mb = max_size_mb
        self._ids = id_factory

    def _parse_a_private_copy(self, resolved):
        """Copy, verify the copy is the same bytes, parse the copy, remove it.

        Returns the parsed project and the digest those exact bytes hashed to -- the same
        value `resolved.sha256` carries when nothing moved, and a refusal when it did.

        Runs on a worker thread as one unit: the copy, the check and the parse belong
        together, and splitting them would put the gap back.
        """
        import hashlib
        import shutil
        import tempfile

        workspace = tempfile.mkdtemp(prefix="finance-mpp-")
        try:
            private = Path(workspace) / resolved.path.name
            shutil.copyfile(resolved.path, private)

            digest = hashlib.sha256()
            with private.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            copied_sha = digest.hexdigest()
            if copied_sha != resolved.sha256:
                # The staged file changed between being hashed and being copied. Nothing is
                # stored, and the previous source version keeps being the active one.
                raise FinanceMppSyncRefused(
                    "MPP_FILE_NOT_STABLE",
                    "the file changed between being hashed and being copied, so nothing "
                    "was stored: %s" % resolved.relative_name)

            return self._reader.read(private), copied_sha
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

    def _file_name(self, project_id, file_name=None):
        """Which file to read: the caller's choice, else the project's own name.

        A name is only ever a name here -- `resolve_import_file` decides whether it is
        reachable, and it answers that question against the configured root alone. The
        default keeps every existing caller and the periodic tick working unchanged.
        """
        return file_name or ("%s.mpp" % project_id)

    async def _recorded_currency_decision(self, organization_id, project_id, source_sha256):
        """What a person decided this file's amounts are in, or None if nobody has.

        The highest version wins. There is no `superseded_at` to consult because the table
        is immutable by trigger -- a correction is a new version, and the previous one stays
        exactly as it was recorded so a report issued last month still has an answer to
        "what did we believe then".

        A missing table is treated as "nobody has decided", not as an error: a deployment
        that has not run 0023 yet must keep importing exactly as it did before, with the
        two code-approved shas still working and everything else leaving costs null.
        """
        from psycopg import errors

        try:
            async with await self._connect() as connection:
                async with connection.cursor(row_factory=dict_row) as cursor:
                    await cursor.execute(
                        """SELECT amounts_are FROM finance_mpp_currency_decisions
                            WHERE organization_id=%s AND project_id=%s AND source_sha256=%s
                            ORDER BY version DESC LIMIT 1""",
                        (organization_id, project_id, source_sha256))
                    row = await cursor.fetchone()
            return row["amounts_are"] if row else None
        except errors.UndefinedTable:
            return None

    async def sync(self, organization_id, project_id, actor_user_id=None, refresh=False,
                   file_name=None):
        """One sync. Returns what happened; raises `FinanceMppSyncRefused` on refusal.

        The whole write is one transaction: a parse that fails or a row that will not
        insert leaves NO version behind, so a partial read can never be mistaken for a
        complete one.

        `refresh` re-reads an UNCHANGED file and replaces the rows of its existing version.
        The ordinary answer for unchanged bytes is to write nothing, and that is right when
        only the file can change -- but the row shape can change too, and after a migration
        adds a column the stored rows are missing something the file has always stated.
        The version row itself is untouched, so every `progress_snapshot_refs` row and
        every report that pinned this version still resolves. Issued reports are unaffected
        by construction: `report_snapshots.snapshot_payload` freezes the whole feed at
        issue time and is never re-read from these tables.
        """
        import asyncio

        try:
            resolved = resolve_import_file(self._import_root,
                                           self._file_name(project_id, file_name),
                                           self._max_size_mb)
        except MppFileError as error:
            raise FinanceMppSyncRefused(error.code, str(error)) from error

        # THE PARSE READS A PRIVATE COPY, NOT THE STAGED FILE.
        #
        # `resolve_import_file` hashes the staged file and hands back a path; opening that
        # path again is a second read of a file the host may have moved on from. Comparing
        # digests before and after the parse gets close, and measurably not all the way: a
        # file changed DURING the parse and changed back before it returned satisfies both
        # digests while the parser saw different bytes. Measured on an isolated database --
        # the version was stored, and its sha described bytes nobody parsed.
        #
        # Copying first replaces that timing argument with a structural one. The copy lives
        # under a directory only this call knows, so nothing can write it, and its digest is
        # checked against the staged file's before the parser is allowed near it. After
        # that, "the sha describes the bytes parsed" is true because there was only ever one
        # set of bytes.
        #
        # This is not a new storage architecture: no watcher, no queue, no callback, and the
        # copy is gone before the function returns. The size ceiling already bounds it.
        parsed, verified_sha = await asyncio.to_thread(
            self._parse_a_private_copy, resolved)

        # What, if anything, a person has decided about this file's currency. Read before
        # the rows are built because it changes what the amounts mean -- and read on its
        # own short connection so a slow decision lookup is not inside the transaction that
        # holds the import's advisory lock.
        recorded_decision = await self._recorded_currency_decision(
            organization_id, project_id, verified_sha)

        rows = finance_rows(parsed, source_sha256=verified_sha,
                            recorded_decision=recorded_decision)
        if not rows:
            raise FinanceMppSyncRefused(
                "MPP_NO_FINANCE_ROWS",
                "the schedule states no task Finance could record")

        async with await self._connect() as connection:
            async with connection.transaction():
                async with connection.cursor(row_factory=dict_row) as cursor:
                    # SERIALISE ON THE FILE'S IDENTITY BEFORE LOOKING FOR IT.
                    #
                    # The look-up below and the insert further down are two statements, and
                    # two callers reaching them at once both saw nothing and both inserted.
                    # The unique index on (organization, project, sha256) then did its job
                    # -- one version, ready, with its rows, which is the right DATA -- but
                    # the loser got a raw UniqueViolation, which is a 500 on a request whose
                    # honest answer is "somebody else just imported these exact bytes".
                    # Measured: two concurrent first-time syncs, one imported, one crashed.
                    #
                    # The lock is the one `PsycopgFinanceImportRepository.commit` already
                    # takes for the same shape of race, keyed the same way: whoever arrives
                    # second waits, then finds the first one's row and answers `unchanged`.
                    # It is transaction-scoped, so it is released by the commit or the
                    # rollback and never needs unlocking by hand.
                    await cursor.execute(
                        "SELECT pg_advisory_xact_lock(hashtext(%s)::bigint)",
                        ("finance_mpp_sync:%s:%s:%s"
                         % (organization_id, project_id, resolved.sha256),))
                    await cursor.execute("""
                        SELECT v.id, v.row_count, v.source_file_name_safe,
                               v.reporting_date,
                               (SELECT count(*) FROM finance_mpp_rows r
                                 WHERE r.source_version_id=v.id
                                   AND r.organization_id=v.organization_id
                                   AND r.project_id=v.project_id) AS actual_row_count,
                               (SELECT count(*) FROM finance_mpp_rows r
                                 WHERE r.source_version_id=v.id
                                   AND r.organization_id=v.organization_id
                                   AND r.project_id=v.project_id
                                   AND r.quantity IS NOT NULL) AS quantity_row_count
                          FROM finance_mpp_source_versions v
                         WHERE v.organization_id=%s AND v.project_id=%s AND v.source_sha256=%s
                    """, (organization_id, project_id, resolved.sha256))
                    existing = await cursor.fetchone()
                    if existing is not None and not refresh:
                        if existing["row_count"] != existing["actual_row_count"]:
                            # Repair metadata only; unchanged source/financial rows retain
                            # their IDs and history. Older refreshes left this count stale.
                            await cursor.execute(
                                "UPDATE finance_mpp_source_versions SET row_count=%s WHERE id=%s",
                                (existing["actual_row_count"], existing["id"]))
                        # Same bytes, so the same version -- but possibly a different file.
                        # An operator restages a schedule under the name it arrived with,
                        # and the version would go on naming the file it was first read
                        # from, which is no longer a file anyone has. The CONTENT identity
                        # (the hash) and the history (imported_at, the rows) are untouched;
                        # only the provenance label catches up with where the bytes live
                        # now. Issued reports are unaffected either way: each froze its own
                        # copy of the feed at issue time.
                        if existing["source_file_name_safe"] != resolved.relative_name:
                            await cursor.execute("""
                                UPDATE finance_mpp_source_versions
                                   SET source_file_name_safe = %s WHERE id = %s
                            """, (resolved.relative_name, existing["id"]))
                        if (existing.get("reporting_date") is None
                                and getattr(parsed, "status_date", None) is not None):
                            await cursor.execute("""
                                UPDATE finance_mpp_source_versions
                                   SET reporting_date = %s WHERE id = %s
                            """, (parsed.status_date, existing["id"]))
                        return {"status": "unchanged",
                                "sourceVersionId": str(existing["id"]),
                                "fileSha256": resolved.sha256,
                                "rowCount": existing["actual_row_count"],
                                "quantityRowCount": existing["quantity_row_count"],
                                "fileName": resolved.relative_name}
                    if existing is not None:
                        version_id = str(existing["id"])
                        await cursor.execute("""
                            UPDATE finance_mpp_source_versions
                               SET reporting_date = %s WHERE id = %s
                        """, (getattr(parsed, "status_date", None), version_id))
                        await cursor.execute(
                            "DELETE FROM finance_mpp_rows WHERE source_version_id = %s",
                            (version_id,))
                        for row in rows:
                            await cursor.execute(
                                _INSERT_ROW,
                                [str(self._ids()), organization_id, project_id, version_id]
                                + [row.get(column) for column in _COLUMNS])
                        stated = sum(1 for row in rows if row["quantity"] is not None)
                        await cursor.execute(
                            "UPDATE finance_mpp_source_versions SET row_count=%s WHERE id=%s",
                            (len(rows), existing["id"]))
                        return {"status": "refreshed", "sourceVersionId": version_id,
                                "fileSha256": resolved.sha256, "rowCount": len(rows),
                                "quantityRowCount": stated,
                                "fileName": resolved.relative_name}

                    version_id = str(self._ids())
                    await cursor.execute("""
                        INSERT INTO finance_mpp_source_versions
                            (id, organization_id, project_id, source_file_name_safe,
                             source_sha256, source_size_bytes, reader_engine, status,
                             row_count, imported_by, reporting_date)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,'ready',%s,%s,%s)
                    """, (version_id, organization_id, project_id,
                          resolved.relative_name, resolved.sha256, resolved.size_bytes,
                          getattr(parsed, "parser_engine", None), len(rows),
                          actor_user_id, getattr(parsed, "status_date", None)))
                    for row in rows:
                        await cursor.execute(
                            _INSERT_ROW,
                            [str(self._ids()), organization_id, project_id, version_id]
                            + [row.get(column) for column in _COLUMNS])
        stated = sum(1 for row in rows if row["quantity"] is not None)
        LOG.info("finance mpp sync project=%s rows=%d quantities=%d",
                 project_id, len(rows), stated)
        return {"status": "imported", "sourceVersionId": version_id,
                "fileSha256": resolved.sha256, "rowCount": len(rows),
                "quantityRowCount": stated, "fileName": resolved.relative_name}
