"""the snapshot status check names the vocabulary this column actually holds

0017 closed `progress_snapshot_refs.snapshot_status`, which needed closing. It took the rule
from `finance_mpp_source_versions.status` -- `ready` and `failed` -- on the reasoning that a
snapshot reference IS a reference to a source version's feed. That reasoning is right about
the relationship and wrong about the vocabulary: the two columns are read by different code
and answer different questions, and this one's words are `ready` and `superseded`.

WHY THAT IS NOT A MATTER OF OPINION
Four independent places already say so, and none of them says `failed`:

  * `app/finance/schemas/progress.py` -- `status: Literal["ready", "superseded"]`
  * `contracts/openapi.json` -- the published enum
  * the Integration Kit's `schemas/progress-snapshot.schema.json` -- `enum: [ready, superseded]`
  * `tests/test_core_integration.py` -- asserts a snapshot's status becomes `"superseded"`

WHY IT WOULD HAVE BROKEN SOMETHING REAL
`superseded` is not hypothetical and not rare. `coreint/progress.py` computes it as "a later
snapshot points at this one" and emits it in the feed header; `services/progress.py` hands
that header to `domain/progress.py:reference_from_header`, which writes the value straight
into this column. So every report pinned at a PAST reporting date resolves a snapshot that
later ones supersede, and storing its reference would have violated the constraint -- a 500
on the historical reports, produced by the module's own correct behaviour. Meanwhile `failed`,
which 0017 permitted, is written to this column by nothing at all.

WHY A NEW REVISION INSTEAD OF AN EDIT
0017 is published and has been applied -- its own commit records the schema fingerprints from
a PG16 and a PG18 run. A migration that has run somewhere is history; correcting it in place
would leave those databases holding a constraint no revision describes. So this replaces it
forward, which is also what an operator's `alembic upgrade head` already knows how to do.

Both directions refuse over data they would reject rather than failing halfway on a constraint
violation. The downgrade deliberately reinstates 0017's narrower rule -- a downgrade restores
the previous state, it does not improve on it -- and refuses when live rows already hold
`superseded`, because that is the moment the old rule stopped being applicable.

Revision ID: 0018
Revises: 0017
"""

from alembic import op
from sqlalchemy.schema import DDL

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


UPGRADE_SQL = r"""
DO $guard$
DECLARE
    bad integer;
BEGIN
    SELECT COUNT(*) INTO bad
      FROM progress_snapshot_refs
     WHERE snapshot_status NOT IN ('ready', 'superseded');
    IF bad > 0 THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'progress_snapshot_refs holds ' || bad || ' row(s) whose '
                      'snapshot_status is neither ready nor superseded; resolve them '
                      'before applying 0018 -- this migration never rewrites a row';
    END IF;
END
$guard$;

ALTER TABLE progress_snapshot_refs
    DROP CONSTRAINT IF EXISTS progress_snapshot_refs_status_check;

ALTER TABLE progress_snapshot_refs
    ADD CONSTRAINT progress_snapshot_refs_status_check
    CHECK (snapshot_status IN ('ready', 'superseded'));
"""

DOWNGRADE_SQL = r"""
DO $guard$
DECLARE
    bad integer;
BEGIN
    SELECT COUNT(*) INTO bad
      FROM progress_snapshot_refs
     WHERE snapshot_status NOT IN ('ready', 'failed');
    IF bad > 0 THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'downgrading to 0017 would reinstate a CHECK that rejects ' || bad ||
                      ' row(s) this database already holds -- almost certainly '
                      'snapshot_status = superseded, which is a value the module writes. '
                      'Stay on 0018, or decide what those rows should say first';
    END IF;
END
$guard$;

ALTER TABLE progress_snapshot_refs
    DROP CONSTRAINT IF EXISTS progress_snapshot_refs_status_check;

ALTER TABLE progress_snapshot_refs
    ADD CONSTRAINT progress_snapshot_refs_status_check
    CHECK (snapshot_status IN ('ready', 'failed'));
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
