"""a person's recorded answer to "what currency are this file's amounts in"

Revision ID: 0023
Revises: 0022

THE PROBLEM THIS SOLVES

`coreint/finance_mpp_sync.py` holds a frozenset of approved SHA256s, and its comment is
exactly right about why: a file that says `currencySymbol = تومان` and `currencyCode = IRR`
is not evidence of anything, because those two disagree. Believing the symbol would store
toman as rial and every cost would be a tenth of the truth; believing the code would do the
opposite. So the decision belongs to exact bytes, and a new file inherits nothing.

What the frozenset cannot do is be added to without a deploy. A schedule re-saved by MS
Project gets a new sha while stating identical figures -- that has now happened three times
to one file -- and each time, costs go null until somebody ships code. Worse, the reason
the decision was made lives in a comment, where it cannot record WHO decided or WHEN.

WHAT THIS ADDS, AND WHAT IT DELIBERATELY DOES NOT

A table of decisions: one row per (scope, sha256), saying what the amounts are in, who
established that, when, and on what evidence. The frozenset stays exactly as it is and is
still consulted first -- this widens the question "is this file approved", it does not
replace the answer already given for the two files in code.

A row here is NOT a way to make a guess official. `evidence` is required and must not be
blank, for the same reason `price_versions.reason` is: a decision nobody explained is one
nobody can review. And a sha with no row and no frozenset entry still resolves to no
currency at all, which is what makes costs null rather than wrong.

Append-only, like every other decision in this schema, and enforced by the same trigger
every historical table carries. A correction is a new VERSION; the previous one is never
touched, because "what did we believe when that report was issued" has to have an answer.
"""

from alembic import op
from sqlalchemy import DDL


revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


UPGRADE_SQL = r"""
CREATE TABLE IF NOT EXISTS finance_mpp_currency_decisions (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    project_id text NOT NULL,

    -- The bytes this decision is about. Not the file NAME: MS Project rewrites the
    -- container and the name stays while the content identity changes, which is precisely
    -- the confusion this table exists to prevent.
    source_sha256 text NOT NULL CHECK (length(source_sha256) = 64),
    version integer NOT NULL CHECK (version > 0),

    -- What the file's own currency fields say, recorded as read rather than as understood.
    -- Stored so a later reader can see the disagreement that made a decision necessary.
    file_currency_symbol text,
    file_currency_code text,

    -- The decision. 'toman' means the amounts are toman and Finance multiplies by ten to
    -- store rials; 'rial' means they are already rials; 'unknown' is an explicit refusal
    -- that keeps costs null, and is worth recording so nobody re-investigates the same
    -- file twice.
    amounts_are text NOT NULL CHECK (amounts_are IN ('toman', 'rial', 'unknown')),

    -- Why this is believed. Required and non-blank: "somebody read the amounts and found
    -- them to be toman" is the whole content of an approval, and without it the row is a
    -- guess wearing a decision's clothes.
    evidence text NOT NULL CHECK (length(btrim(evidence)) > 0),

    -- When the evidence is "it states the same figures as a file already decided", this
    -- names that file. Nullable because reading the amounts directly is also evidence.
    compared_with_sha256 text CHECK (compared_with_sha256 IS NULL
                                     OR length(compared_with_sha256) = 64),

    decided_by uuid NOT NULL,
    decided_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (organization_id, project_id, id),
    UNIQUE (organization_id, project_id, source_sha256, version)
);

-- The current decision for one file is simply its highest version. There is no
-- `superseded_at`, and that is deliberate rather than an omission: the immutability
-- trigger below refuses UPDATE, so a column that has to be written after the fact could
-- never be written. `price_versions` and `unit_conversions` resolve the same way -- a
-- correction is a new version and the previous one stays exactly as it was recorded.
CREATE INDEX IF NOT EXISTS ix_mpp_currency_decisions_current
    ON finance_mpp_currency_decisions (organization_id, project_id, source_sha256,
                                       version DESC);

-- A decision is a record of a judgement. Changing one after the fact would change what a
-- report was issued against, so the same guard every other historical table carries.
CREATE TRIGGER finance_mpp_currency_decisions_immutable
    BEFORE UPDATE OR DELETE ON finance_mpp_currency_decisions
    FOR EACH ROW EXECUTE FUNCTION finance_reject_mutation();
"""


DOWNGRADE_SQL = r"""
DROP TRIGGER IF EXISTS finance_mpp_currency_decisions_immutable
    ON finance_mpp_currency_decisions;
DROP INDEX IF EXISTS ix_mpp_currency_decisions_current;
DROP TABLE IF EXISTS finance_mpp_currency_decisions;
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
