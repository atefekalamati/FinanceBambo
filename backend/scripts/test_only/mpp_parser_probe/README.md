# MPP parser probe — TEST ONLY, DISPOSABLE

Reads a real `.mpp` with MPXJ and writes a JSON fixture that
`scripts/test_only/seed_msp_resource_assignments.py` accepts.

```
.mpp ──▶ parse_mpp.py ──▶ fixture.json ──▶ check_fixture.py      (offline: will it be accepted?)
        (MPXJ on a JVM)         │
                                └──────▶ load_scratch.py ──▶ bambo_mpp_probe ──▶ validate_scratch.py
                                          creates the DB,       (disposable)      counts, references,
                                          runs alembic,                           resource rollup
                                          loads Core parents + msp_tasks,
                                          then the EXISTING seed script
                                          for resources + assignments
```

**This is not the production MSP parser and must never become one.** The production path is
MPP → Core's MPXJ importer → the `msp_*` tables, and that importer lives outside this
repository. This probe exists to answer one question quickly: *can a real `.mpp` be turned
into rows the Finance side already knows how to consume?*

`parse_mpp.py` and `check_fixture.py` open no database at all — the parser has no `psycopg`
import and no `--dsn` argument, so the only thing it can damage is its own output file. The
three scripts that do connect (`load_scratch.py`, `validate_scratch.py`,
`finance_consume_check.py`) go through `scratch_target.py`, which permits exactly one local
database and refuses every other by name.

**To remove it:** delete this directory. Nothing outside it refers to it, no migration was
added, and no file under `app/` was touched.

---

## Install

Everything lands inside this directory and on `E:`, because `C:` is full.

```bash
cd backend/scripts/test_only/mpp_parser_probe

export TMPDIR=E:/bamboo/FINANCE/.piptmp PIP_CACHE_DIR=E:/bamboo/FINANCE/.pipcache
python -m venv probe-env
./probe-env/Scripts/python -m pip install mpxj jpype1 install-jdk
```

`mpxj` imports `jpype` but does not declare it as a dependency, which is why `jpype1` is
listed explicitly.

Then a JVM. There is none on this machine, so one is fetched:

```bash
./probe-env/Scripts/python -c "import jdk; print(jdk.install('17', jre=True, path='<abs path>/jre'))"
```

**It has to be a full JRE.** A jlink'd minimal runtime — `jdk4py`, the obvious pip-installable
choice — omits the `jdk.charsets` module, and MPXJ's `CharsetHelper` asks for `MacRoman` in a
static initialiser. The failure is `UnsupportedCharsetException: MacRoman` thrown during class
loading, before your file is opened, which reads like a corrupt `.mpp` rather than a missing
module. Java 17 is chosen to match production, whose `parser_engine` reads `mpxj-16.4.1/jvm-17`.

Verified here: `mpxj 16.7.0`, `jpype1 1.7.1`, Temurin `17.0.20.1+1` JRE, CPython 3.12.

---

## Run

```bash
# 1. read the file
./probe-env/Scripts/python parse_mpp.py \
    --input "E:\bamboo\FINANCE\Sources\زمان بندی پل.mpp" \
    --output fixture.json

# 2. will the seed script accept it? (no database needed)
../../../../.venv312/Scripts/python check_fixture.py fixture.json
```

Then load it into a scratch database — see the next section.

`JAVA_HOME` is picked up if set; otherwise the bundled JRE is used. `--strict` makes
`parse_mpp.py` exit non-zero if it warned about anything.

---

## The scratch database

Steps 3 and 4 above have a precondition the probe cannot satisfy on a real database:
`seed_msp_resource_assignments.py` writes **only** `msp_resources` and
`msp_resource_assignments`. It refuses to touch `msp_tasks`, `msp_snapshots` and
`msp_file_versions` — so it cannot create the snapshot its own rows hang from, and its
`check_tasks` refuses the whole run unless every `task_uid` in the fixture already exists in
`msp_tasks` for that snapshot. This fixture names **266 distinct task UIDs**.

`load_scratch.py` solves that by building a disposable database that contains them:

```bash
cd backend

FIXTURE=scripts/test_only/mpp_parser_probe/fixture.json
PY=../.venv312/Scripts/python

# dry run: proves the target and reports what would load, writes nothing
$PY -m scripts.test_only.mpp_parser_probe.load_scratch --fixture $FIXTURE

# build it
$PY -m scripts.test_only.mpp_parser_probe.load_scratch --fixture $FIXTURE --recreate --apply

# validate again later, read-only
$PY -m scripts.test_only.mpp_parser_probe.validate_scratch --snapshot-id 9001 --fixture $FIXTURE
```

It creates `bambo_mpp_probe` on `127.0.0.1:5432`, runs `alembic upgrade head` (which is what
brings `msp_resources` and `msp_resource_assignments` into existence, at revision 0007),
applies `scripts/demo/core_mirror.sql` for the Core-side tables, inserts one organization,
project, file version and snapshot, loads `msp_tasks` from the fixture, and then hands the
resources and assignments to **the existing seed script, unmodified, as a subprocess**.

That last point is deliberate. The seed script is the thing being tested; reimplementing its
inserts would produce a second importer that agrees with itself and proves nothing, and the
first time the two drifted the copy would be the one that looked right.

**The load is idempotent.** Re-running without `--recreate` clears this snapshot's tasks and
passes `--replace-test-data` to the seed script, so a repeat run replaces rather than doubles.
That is not cosmetic: `msp_tasks` has no unique key on `(snapshot_id, uid)` — Core's schema
declares none — so an early version of this script appended a second full set of tasks while
the seed script refused its own re-run, leaving 656 task rows for 328 UIDs and the two halves
of one snapshot describing different loads.

### Why this script may write `msp_tasks` when the seed script may not

The seed script refuses Core-owned tables because it is aimed at real databases, where Core
owns that data. `load_scratch.py` only ever addresses a scratch database it created itself,
on loopback, behind `scratch_target.py`. Different target, different rule — neither script's
rule is relaxed.

### The guard

`scratch_target.py` is a new gate rather than a widened copy of `scripts/demo/target.py`:
teaching the demo gate a second database name would loosen a check that protects unrelated
work in order to serve a throwaway probe. It pins host and port, permits only
`bambo_mpp_probe` (plus `postgres`, and only for CREATE/DROP), and refuses by name — with
the reason — `bambo`, `bambo_finance_dev`, `bambo_canonical_local` and
`bambo_finance_integration_demo`, along with the host `192.168.100.200`. Both gates run: once
on the DSN before a socket opens, and once by asking the server that actually answered.

**`bambo_canonical_local` is never touched.** Not read, not written, not connected to.

### To remove the database

```sql
DROP DATABASE bambo_mpp_probe;
```

---

## What the probe read from `زمان بندی پل.mpp`

| | |
|---|---|
| Written by | Microsoft.Project 16.0 |
| Tasks | 328 |
| Resources | 81 — 62 `MATERIAL`, 19 `WORK` |
| Assignments | 727 — 289 carry a quantity, 12 name no resource |
| Distinct `task_uid` referenced | 266 |

All 62 `MATERIAL` resources carry both a quantity and a unit, so the
`msp_resource_assignments` CHECK that forbids a quantity without a unit is satisfied, and the
seed script's post-apply rollup check (each resource's sheet total against the sum of its
assignments) matches on all 62 with zero mismatches. That was computed from the fixture in
advance rather than discovered after writing.

**The unit comes from the Initials column** — this file's author wrote `کیلوگرم`, `مترمکعب`,
`مترطول`, `عدد`, `اصل` there. `MaterialLabel` is empty on every row. That is a convention this
author chose, not something MS Project enforces, which is why `quantity_unit_source` records
where each string was read from: a later file using `MaterialLabel` stays distinguishable.

**No progress is recorded anywhere in this file.** `percent_complete` is 0 on all 328 tasks,
`actual_work` is 0 on all 727 assignments, and `actual_quantity` is 0 — not null — on all 289
assignments that carry a quantity. So this file can prove the planned side of the pipeline and
cannot exercise the actual/progress side at all.

Three resource columns come out null on every row and would be inserted null:
`bambo_resource_type` (never set — MS Project has no labour/equipment distinction to read),
`material_label`, and `code`.

**On the decimals.** Values arrive from MPXJ as Java doubles, so the fixture contains strings
like `"879.3500000000001"` and `"2830488000.0000005"`. Those are faithful — the shortest string
that round-trips the double MPXJ actually computed — and they are *not* rounded here, because
choosing a rounding would be inventing precision the file does not state. The `numeric(18,6)`
and `numeric(18,4)` column scales absorb the noise on insert. Nothing passes through a Python
float at any point: every number is carried as a string and read back with `Decimal`.

---

## Can Finance consume it?

`finance_consume_check.py` drives the real integration against the scratch database. It
duplicates no import logic and relaxes no validation -- every step calls the module Finance
itself calls:

```
msp_snapshots + msp_tasks + msp_resources + msp_resource_assignments
  -> coreint.progress.CoreProgressSnapshotProvider     the real adapter
  -> domain.progress.snapshot_metadata                 the real header check
  -> domain.progress.reference_from_header             the real ProgressReference
  -> repositories.progress.ensure_progress_reference   the real Finance ref row
  -> domain.progress.resolve_progress_quantity         the real calculation
  -> domain.progress.ProgressPairing                   the real matching rule
```

```bash
cd backend
../.venv312/Scripts/python -m scripts.test_only.mpp_parser_probe.finance_consume_check
```

**It works.** The provider returns a feed, `snapshot_metadata` accepts the header, a
`progress_snapshot_refs` row is created and re-pinning the same Core snapshot reuses it, all
727 assignments resolve through `resolve_progress_quantity`, and `ProgressPairing` matches a
real key. No adapter is missing.

### What it found

**1. Text1 holds a date — FIXED in host wiring.** `coreint.ACTIVITY_CODE_FIELDS` defaults to
`("text1", "outline_number", "wbs")` and every one of this file's 328 tasks fills Text1 with a
Jalali date. The default order therefore resolved each activity code to a date:

| field order | distinct codes | largest fan-out | sample |
|---|---|---|---|
| `text1, outline_number, wbs` (library default) | 128 | 27 | `1404/5/18` |
| `outline_number, wbs` (what devhost now wires) | 266 | 7 | `1.1` |

The docstring on `ACTIVITY_CODE_FIELDS` anticipates a wrong guess showing up "as unmapped
lines, which is visible, rather than as wrong pairings, which would not be". That holds only
when the field is empty. Here it is full, so the guess did not fail visibly — it succeeded
into the wrong value, and an estimate line would have paired by date.

`devhost/app.py` now passes `activity_code_fields=("outline_number", "wbs")` to **both**
`CoreProgressSnapshotProvider` and `CoreProjectActivityProvider`, from one module constant.
The library default is deliberately unchanged: which field a planner uses is a deployment
fact, not a library one, and a host whose planners really do write codes in Text1 still needs
it. Guarded by `tests/test_activity_code_is_not_a_date.py`.

Note the shape of the improvement: the number of codes shared by more than one assignment
went *up* (106 → 215) while the worst case went *down* (27 → 7). That is the expected
direction — 266 real codes spread across 727 assignments share more often but far more
thinly than 128 dates did.

Whether other BAMBO schedules use Text1 the same way is still unverified; this is one file.

**2. `get_snapshot` applies no snapshot_type filter.** `current_snapshot` correctly refuses
this snapshot: it is a `TARGET` baseline, and `PROGRESS_SNAPSHOT_TYPES` is
`("ACTUAL", "RESCHEDULED")`. But `get_snapshot` has no equivalent clause, so the same
baseline is fetchable by id and is then consumed as executed progress. The two entry points
disagree about what a progress snapshot is.

**3. `importedBy` is null where Finance requires one.** `msp_snapshots.created_by` is
nullable and is null here, while `progress_snapshot_refs.imported_by` is `NOT NULL`.
`reference_from_header` falls back to the request actor and returns None when there is none
-- correct, and never invents a user -- but it means a caller outside the router path can
pin nothing.

**4. Every executed quantity is zero.** All 727 assignments resolve: 289 through
`assignment_actual` as `measured_quantity` (quality 1.0), 438 through the work-effort path
as `work_effort` (quality 0.5, each carrying `PROGRESS_WORK_NOT_QUANTITY`). Total executed
quantity is exactly `0`. The calculation path is exercised; no non-zero result is proven by
this file.

**5. 106 activity codes are shared by more than one assignment**, even on the structural
codes. That is the known override fan-out: a correction keyed on the activity alone reaches
every assignment sharing it.

---

## What it refuses to do

* invent a value — a field MS Project does not carry is `null`, never `0`, and never derived
  from another field;
* derive a quantity from work, duration or a percentage. `work` is hours; `quantity` is
  kilograms and cubic metres. They are read from different MPXJ fields and never substituted
  for one another — confusing them turns 48 crane-hours into 48 kilograms of rebar;
* classify a resource as labour or equipment;
* write to any database.

## Files

| | |
|---|---|
| `parse_mpp.py` | reads the `.mpp`, writes the fixture, prints the counts |
| `check_fixture.py` | runs the seed script's own checks against the fixture, offline |
| `scratch_target.py` | the gate: which database may be written to, and which are refused by name |
| `load_scratch.py` | builds the scratch database and loads the fixture end to end |
| `validate_scratch.py` | counts, references and the resource rollup — read-only, re-runnable |
| `finance_consume_check.py` | drives the real Finance integration over the loaded snapshot |
| `output_example.json` | the shape, with invented values — the real fixture is gitignored |
| `.gitignore` | keeps `probe-env/`, `jre/` and generated fixtures out of the repository |

## Verified end to end

On `زمان بندی پل.mpp`, into `bambo_mpp_probe`, `2026-09-02`:

```
task count                                 fixture=328    database=328    OK
resource count                             fixture=81     database=81     OK
assignment count                           fixture=727    database=727    OK
snapshot.task_count vs msp_tasks           fixture=328    database=328    OK
assignments pointing at a missing task     0 OK
assignments pointing at a missing resource 0 OK
quantity with no unit                      0 OK
MATERIAL resources rolled up               62
rollup matching                            62
rollup mismatched                          0 OK
planned_quantity null/zero/positive        438 / 0 / 289
actual_quantity  null/zero/positive        438 / 289 / 0
VALIDATION PASSED
```

The last line of that reading is the one worth keeping in view: **`actual_quantity` is zero
on every assignment that has one, and positive on none.** This file records no progress at
all, so it exercises the planned side of the pipeline completely and the actual side not at
all. Proving the progress path needs a different file.
