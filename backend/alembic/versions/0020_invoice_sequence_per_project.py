"""A per-project invoice number that the database allocates

WHAT WAS THERE BEFORE
`invoice_number` was text, supplied by whoever created the invoice, and filled in with
`F-` plus the first block of the row's UUID when they supplied nothing. Two invoices in one
project could carry the same number, an invoice could carry a number nobody could explain,
and a void reused the number of the invoice it reversed -- so "invoice 7" could name two
documents with opposite financial signs. Nothing in the database said otherwise, because
nothing in the database had an opinion about the number at all.

WHAT THIS PUTS IN ITS PLACE
`invoice_seq`, an integer, unique per project and allocated by a counter this revision
creates. It starts at 1 in every project and counts up by one. The zero-padding readers
see -- 001, 042, 999 -- is a presentation decision made at the API boundary, so the number
that reaches four digits simply prints as 2000 and nothing has to be migrated for it.

THE BACKFILL AND THE TRIGGER THAT REFUSES IT
Existing rows are numbered by creation order within their project. That is an UPDATE on
`invoices`, and `confirmed_invoice_immutable` (from 0001) raises on any UPDATE to a row
whose status is confirmed, voided or corrected -- which is nearly every row worth
numbering. The trigger is therefore disabled for the length of this one transaction and
re-enabled in it. Both statements are transactional DDL: if anything here fails, the
rollback restores the trigger with the rest.

Disabling it is the narrow choice, not the broad one. The alternatives were to teach the
guard function to permit a column it should never permit at runtime, or to rewrite the
table -- one weakens the invariant for ever, the other is a far larger operation. This
weakens it for the duration of one migration that holds an ACCESS EXCLUSIVE lock anyway.

WHY A COUNTER TABLE AND NOT max()+1
`max(invoice_seq)+1` read inside a transaction gives two concurrent creators the same
answer; both then insert, and one fails on the unique constraint with an error that
describes nothing the caller did wrong. The counter row is a single point every creator in
a project must pass through: `INSERT ... ON CONFLICT DO UPDATE ... RETURNING` takes a row
lock, so the second creator waits for the first to commit and is handed the next number.

The unique constraint below is the safety net, not the mechanism. If it is ever violated,
something allocated a number without going through the counter, and the right outcome is a
refused write rather than two invoices sharing a number.

WHAT THIS REVISION DELIBERATELY DOES NOT DO
It does not drop `invoice_number`. The column stops being written by this release, and
dropping it belongs to a later revision -- after a release has run without it, and after
anybody still reading it has been given the replacement. A column that is merely unread is
recoverable; a dropped one is not.

REVISION NUMBERING
The specification for this work says "next migration: 0019". 0019 was taken while this was
being specified -- it is `0019_finance_mpp_fixed_cost` -- so this is 0020 and follows it.
The chain stays linear, which `tests/test_migrations.py` requires and explains.
"""

from alembic import op
from sqlalchemy.schema import DDL

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


UPGRADE_SQL = r"""
ALTER TABLE invoices
    ADD COLUMN invoice_seq integer;

COMMENT ON COLUMN invoices.invoice_seq IS
    'The invoice''s number within its project: 1 for the first invoice of a project and '
    'one more for each after it, allocated by finance_invoice_counters. Every invoice has '
    'one, including a reversal -- a void is its own document and carries its own number.';

-- The backfill is an UPDATE, and `confirmed_invoice_immutable` refuses one on any row that
-- is confirmed, voided or corrected. Disabled here and re-enabled below, both inside this
-- revision's transaction: a failure anywhere between them rolls the trigger back too.
ALTER TABLE invoices DISABLE TRIGGER confirmed_invoice_immutable;

-- Creation order within the project, with the id as the tiebreak so that two invoices
-- created in the same instant still get a defined order rather than an arbitrary one.
UPDATE invoices AS target
   SET invoice_seq = numbered.row_number
  FROM (SELECT id,
               ROW_NUMBER() OVER (PARTITION BY organization_id, project_id
                                  ORDER BY created_at, id) AS row_number
          FROM invoices) AS numbered
 WHERE target.id = numbered.id;

ALTER TABLE invoices ENABLE TRIGGER confirmed_invoice_immutable;

ALTER TABLE invoices
    ALTER COLUMN invoice_seq SET NOT NULL;

ALTER TABLE invoices
    ADD CONSTRAINT ux_invoices_project_seq UNIQUE (organization_id, project_id, invoice_seq);

-- One row per project. `next_number` is what the next invoice will be given, so a project
-- that has never had one starts at 1 and a project with 12 invoices resumes at 13.
CREATE TABLE finance_invoice_counters (
    organization_id uuid NOT NULL,
    project_id text NOT NULL,
    next_number integer NOT NULL,
    PRIMARY KEY (organization_id, project_id),
    CONSTRAINT finance_invoice_counters_positive CHECK (next_number >= 1)
);

COMMENT ON TABLE finance_invoice_counters IS
    'One row per project holding the next invoice number to hand out. Allocation is an '
    'INSERT ... ON CONFLICT DO UPDATE ... RETURNING inside the transaction that writes the '
    'invoice, so a rolled back invoice releases its number and leaves no gap.';

INSERT INTO finance_invoice_counters (organization_id, project_id, next_number)
SELECT organization_id, project_id, MAX(invoice_seq) + 1
  FROM invoices
 GROUP BY organization_id, project_id;
"""

DOWNGRADE_SQL = r"""
DROP TABLE IF EXISTS finance_invoice_counters;

ALTER TABLE invoices
    DROP CONSTRAINT IF EXISTS ux_invoices_project_seq;

ALTER TABLE invoices
    DROP COLUMN IF EXISTS invoice_seq;
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
