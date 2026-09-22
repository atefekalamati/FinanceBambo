"""A price revision need not be explained in words.

Revision ID: 0036
Revises: 0035

`price_versions.reason` was NOT NULL with CHECK (length(btrim(reason)) > 0), so every
rate revision had to carry a sentence. The row already records WHO and WHEN -- `created_by`
and `created_at` are NOT NULL and neither can be omitted -- and for an ordinary equipment
rate revision that is the whole of the evidence a reader needs.

What the requirement actually bought was the opposite of evidence. A client that must send
something sends something: the finance UI was filling the field with a generated sentence
purely to pass validation, so the history accumulated text that reads like a recorded
reason and records nothing. A blank the reader can see is more honest than a placeholder
they cannot tell from a real one.

The column becomes nullable and the check is rewritten to keep its original guarantee for
any value that IS present: a reason may be absent, but it may not be an empty string
pretending to be one.

Existing rows are untouched -- every one of them has a reason today, and nothing here
rewrites, clears or reinterprets them.

The downgrade is deliberately NOT destructive. Restoring NOT NULL would require inventing
text for any row written without a reason while this revision was live, and a migration
that fabricates financial history is worse than one that declines to. It restores the
CHECK only, and says so.
"""

from alembic import op
from sqlalchemy import DDL


revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


UPGRADE_SQL = r"""
ALTER TABLE price_versions ALTER COLUMN reason DROP NOT NULL;

ALTER TABLE price_versions DROP CONSTRAINT price_versions_reason_check;
ALTER TABLE price_versions
    ADD CONSTRAINT price_versions_reason_check CHECK (
        reason IS NULL OR length(btrim(reason)) > 0);

COMMENT ON COLUMN price_versions.reason IS
    'Why this rate was set, when somebody chose to say. Optional: created_by and '
    'created_at are recorded on every version and are the evidence that a revision '
    'happened. An empty string is still refused -- absent and blank are different '
    'statements and only one of them is honest.';
"""


DOWNGRADE_SQL = r"""
ALTER TABLE price_versions DROP CONSTRAINT price_versions_reason_check;
ALTER TABLE price_versions
    ADD CONSTRAINT price_versions_reason_check CHECK (
        reason IS NULL OR length(btrim(reason)) > 0);

COMMENT ON COLUMN price_versions.reason IS
    'Why this rate was set. NOT NULL was NOT restored by this downgrade: any row '
    'written without a reason while 0036 was live would need text invented for it, '
    'and a migration that fabricates financial history is worse than one that '
    'declines to. Restore it by hand once those rows are resolved.';
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
