"""The one status column that was text with nothing to check it

`progress_snapshot_refs.snapshot_status` has been plain `text NOT NULL` since 0001. Every
other status column in the Finance schema carries a CHECK naming its vocabulary --
`finance_mpp_source_versions.status` allows exactly `ready` and `failed`, and the invoice,
attachment, extraction, import and price-run columns each do the same. This one was
missed, which is the difference between a column that cannot hold a typo and a column that
merely has not been given one yet.

The rule it now carries is the source version's own, because a snapshot reference IS a
reference to a source version's feed and the two are read together: `active_source_version`
filters on `status = 'ready'`, and a reference pointing at anything else is a reference the
report cannot use. Every row in every database checked holds `ready`.

Nothing else moves. The column keeps its type, its NOT NULL and its default, and no row is
rewritten -- this only closes the set of values a future write may use.
"""

from alembic import op
from sqlalchemy.schema import DDL

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


UPGRADE_SQL = r"""
ALTER TABLE progress_snapshot_refs
    ADD CONSTRAINT progress_snapshot_refs_status_check
    CHECK (snapshot_status IN ('ready', 'failed'));
"""

DOWNGRADE_SQL = r"""
ALTER TABLE progress_snapshot_refs
    DROP CONSTRAINT IF EXISTS progress_snapshot_refs_status_check;
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
