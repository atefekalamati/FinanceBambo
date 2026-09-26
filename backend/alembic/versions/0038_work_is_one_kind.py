# -*- coding: utf-8 -*-
"""work is one kind

Revision ID: 0038
Revises: 0037

Finance separated the hours a project buys into `labor` and `equipment`. No figure ever
depended on the difference -- both are hours, priced per hour, settled against invoices
the same way -- and MS Project, where every resource comes from, calls both WORK and does
not say which. So each crew and each machine in a schedule waited for a person to decide,
through an endpoint that existed only on the development host; on the product they waited
forever and never reached an estimate line. Decided 2026-09-26: one kind, `work`.

WHAT THIS DOES

Widens the two CHECK constraints to admit `work`. Nothing else. The rows that say `labor`
or `equipment` are left exactly as they are: the application reads both as `work` through
`domain/resource_types.canonical_resource_type`, so no row is rewritten and no history is
lost. `msp_resources` is Finance's own table (0007), not Core's.

DOWNGRADE

Restores the four-value CHECKs. A `work` row written after this revision cannot be
expressed in the old vocabulary without guessing, so the downgrade REFUSES when any exist
rather than call every crew a machine. Delete or reclassify them first.
"""
from alembic import op
from sqlalchemy import DDL

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None

#: (table, column, constraint name) for the two columns that name a resource's kind.
_TYPED = (
    ("finance_resources", "resource_type", "finance_resources_resource_type_check"),
    ("msp_resources", "bambo_resource_type", "msp_resources_bambo_type_check"),
)

_NEW_KINDS = "('material', 'work', 'general_cost', 'labor', 'equipment')"
_OLD_KINDS = "('material', 'labor', 'equipment', 'general_cost')"

UPGRADE_SQL = "\n".join(
    """
ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name};
ALTER TABLE {table}
    ADD CONSTRAINT {name}
    CHECK ({column} IS NULL OR {column} IN {kinds});
""".format(table=table, column=column, name=name, kinds=_NEW_KINDS)
    for table, column, name in _TYPED)

DOWNGRADE_SQL = "\n".join(
    """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM {table} WHERE {column} = 'work') THEN
        RAISE EXCEPTION '{table}.{column} holds ''work'' rows; the old vocabulary cannot name them';
    END IF;
END $$;
ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name};
ALTER TABLE {table}
    ADD CONSTRAINT {name}
    CHECK ({column} IS NULL OR {column} IN {kinds});
""".format(table=table, column=column, name=name, kinds=_OLD_KINDS)
    for table, column, name in reversed(_TYPED))


def upgrade():
    op.execute(DDL(UPGRADE_SQL))


def downgrade():
    op.execute(DDL(DOWNGRADE_SQL))
