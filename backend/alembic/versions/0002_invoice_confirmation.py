"""invoice confirmation idempotency

A confirmation idempotency key on invoices, with a partial unique index so repeating
a confirmation request cannot produce a second confirmation.

Converted from migrations/0002_invoice_confirmation.up.sql and .down.sql, which Git history keeps.
The SQL is embedded unchanged apart from the outer BEGIN/COMMIT: Alembic owns the
transaction boundary, and opening a second one inside it is an error.

The SQL travels as a `DDL` construct rather than a plain string. `op.execute` on a string
parses it for `:name` bind parameters, which would misread PostgreSQL cast syntax and
dollar-quoted function bodies; `DDL` skips that parsing and passes the whole batch through
as it stood in the file. It also works in offline mode (`alembic upgrade head --sql`), where
the mock connection has no `exec_driver_sql` to call.

Revision ID: 0002
Revises: 0001
"""

from alembic import op
from sqlalchemy import DDL

revision = "0002"
down_revision = '0001'
branch_labels = None
depends_on = None


UPGRADE_SQL = """\
ALTER TABLE invoices
    ADD COLUMN IF NOT EXISTS confirmation_idempotency_key text;

CREATE UNIQUE INDEX IF NOT EXISTS ux_invoices_confirmation_idempotency_scope
    ON invoices (organization_id, project_id, confirmation_idempotency_key)
    WHERE confirmation_idempotency_key IS NOT NULL;
"""


DOWNGRADE_SQL = """\
DROP INDEX IF EXISTS ux_invoices_confirmation_idempotency_scope;
ALTER TABLE invoices DROP COLUMN IF EXISTS confirmation_idempotency_key;
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
