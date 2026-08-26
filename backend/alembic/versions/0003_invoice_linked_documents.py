"""one reversal per invoice

A partial unique index allowing at most one reversal per original invoice, scoped to
the organisation and project like every other constraint here.

Converted from migrations/0003_invoice_linked_documents.up.sql and .down.sql, which Git history keeps.
The SQL is embedded unchanged apart from the outer BEGIN/COMMIT: Alembic owns the
transaction boundary, and opening a second one inside it is an error.

The SQL travels as a `DDL` construct rather than a plain string. `op.execute` on a string
parses it for `:name` bind parameters, which would misread PostgreSQL cast syntax and
dollar-quoted function bodies; `DDL` skips that parsing and passes the whole batch through
as it stood in the file. It also works in offline mode (`alembic upgrade head --sql`), where
the mock connection has no `exec_driver_sql` to call.

Revision ID: 0003
Revises: 0002
"""

from alembic import op
from sqlalchemy import DDL

revision = "0003"
down_revision = '0002'
branch_labels = None
depends_on = None


UPGRADE_SQL = """\
CREATE UNIQUE INDEX IF NOT EXISTS ux_invoices_one_reversal_per_original
    ON invoices (organization_id, project_id, original_invoice_id)
    WHERE source = 'reversal';
"""


DOWNGRADE_SQL = """\
DROP INDEX IF EXISTS ux_invoices_one_reversal_per_original;
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
