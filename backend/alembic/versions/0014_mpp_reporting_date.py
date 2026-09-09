"""Persist the reporting date stated by a Finance-owned MPP source.

Revision ID: 0014
Revises: 0013

The import timestamp answers when bytes reached BAMBO. It does not answer which reporting
period those bytes describe. Existing rows stay nullable and keep their historical
import-date fallback; newly parsed files preserve MS Project's Status Date here.
"""

from alembic import op
from sqlalchemy import DDL


revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

UPGRADE_SQL = """
ALTER TABLE finance_mpp_source_versions
    ADD COLUMN reporting_date date;
COMMENT ON COLUMN finance_mpp_source_versions.reporting_date IS
    'Status Date stated by the source schedule; NULL when the file states none.';
"""

DOWNGRADE_SQL = """
ALTER TABLE finance_mpp_source_versions DROP COLUMN reporting_date;
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
