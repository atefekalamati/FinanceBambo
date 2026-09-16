"""a schedule version that is no longer the one anybody reads says so

Revision ID: 0028
Revises: 0027

THE GAP THIS CLOSES

`finance_mpp_source_versions` had one status -- 'ready' -- and wore it for ever. A project
that has imported the same schedule three times had three 'ready' versions and nothing on
the row said which one anybody may read. "Which version is live" was answerable only by
joining to `progress_snapshot_refs` and to `estimate_line_source_completions`, and a
question that needs two joins to answer is one that gets answered wrongly.

That is not a cosmetic gap. One of the invariants this system is meant to hold is that a
superseded version does not remain effective, and until now the schema could not express
the antecedent.

WHAT IT MAKES SAYABLE, AND WHY THE ROW-COUNT CHECK NEEDED IT

`verify_finance_invariants` asks whether each version holds the number of rows it declares.
On the audited database one version answers 788 against a declared 789 -- and that version
is superseded, referenced by no snapshot and no completion, with bytes that are no longer
on disk.

    The gap is REAL and the row is genuinely missing. Nothing here repairs it, because
    nothing here can: the file those bytes came from is gone, and inventing the row from a
    sibling version would be asserting that two files agree in a place nobody checked.

    Lowering `row_count` to 788 would be worse. It would record that the version is
    complete at 788, which is false -- the count is the one piece of evidence that says a
    row is missing at all.

So the version is marked superseded, which it is, and the invariant is scoped to versions
anybody may still read. The gap stays visible -- the check reports superseded gaps on their
own line rather than dropping them -- and stops being reported as a live defect, which it
is not.

WHAT THIS MIGRATION DOES NOT DECIDE

It adds the column and backfills nothing. Which versions are superseded is a statement
about a project's history, and it is made by `scripts/ops/mark_superseded_source_versions.py`
against evidence -- a newer version of the same file name exists, and this one is named by
no live snapshot reference.
"""

from alembic import op
from sqlalchemy import DDL


revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


UPGRADE_SQL = r"""
ALTER TABLE finance_mpp_source_versions
    ADD COLUMN IF NOT EXISTS superseded_at timestamptz,
    ADD COLUMN IF NOT EXISTS superseded_by uuid
        REFERENCES finance_mpp_source_versions (id),
    ADD COLUMN IF NOT EXISTS superseded_reason text;

COMMENT ON COLUMN finance_mpp_source_versions.superseded_at IS
    'When this version stopped being one anybody may read. NULL means live. The rows and '
    'the hash are untouched: a superseded version is still the evidence of what was '
    'imported that day, and a report issued against it must stay explainable.';

COMMENT ON COLUMN finance_mpp_source_versions.superseded_reason IS
    'Why, in a sentence. A version marked superseded with no reason is a state somebody '
    'set rather than a decision somebody made.';

-- A version cannot supersede itself, and a superseded one states when.
ALTER TABLE finance_mpp_source_versions
    ADD CONSTRAINT finance_mpp_source_version_supersede_shape CHECK (
        (superseded_by IS NULL OR superseded_by <> id)
        AND (superseded_by IS NULL OR superseded_at IS NOT NULL)
        AND (superseded_reason IS NULL OR superseded_at IS NOT NULL));

-- "Which version is live for this project" -- the question that used to need two joins.
CREATE INDEX IF NOT EXISTS ix_finance_mpp_source_version_live
    ON finance_mpp_source_versions (organization_id, project_id, imported_at DESC)
 WHERE superseded_at IS NULL;
"""


DOWNGRADE_SQL = r"""
DROP INDEX IF EXISTS ix_finance_mpp_source_version_live;
ALTER TABLE finance_mpp_source_versions
    DROP CONSTRAINT IF EXISTS finance_mpp_source_version_supersede_shape;
ALTER TABLE finance_mpp_source_versions
    DROP COLUMN IF EXISTS superseded_reason,
    DROP COLUMN IF EXISTS superseded_by,
    DROP COLUMN IF EXISTS superseded_at;
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
