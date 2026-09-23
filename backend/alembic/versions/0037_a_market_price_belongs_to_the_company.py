# -*- coding: utf-8 -*-
"""a market price belongs to the company, not to one of its projects

Revision ID: 0037
Revises: 0036

WHAT THIS FIXES

One Google Sheet has been imported six times. The same document, `1RgjXoz-s99l175H`, was
read once per project across two organizations and produced 14,258 observation rows -- six
copies of one market reading, each of which has to be imported again, aged again and
mapped again. The price of rebar on a given day is a fact about the market. It is not a
fact about `terrace`.

It was stored per project because there was nowhere else to put it: every one of these
four tables is keyed `(organization_id, project_id, ...)`, `project_id` is NOT NULL, and it
sits inside seven composite foreign keys. Making it nullable is the obvious move and it is
the wrong one -- under MATCH SIMPLE a foreign key with ANY null column is not checked at
all, so a null `project_id` would silently switch OFF referential integrity on exactly the
rows this change is meant to make safe.

WHAT IT DOES INSTEAD

`scope_level` says out loud what was previously implied. Existing rows are `project` and
keep every guarantee they have; new sheet imports may be `organization`, and those rows
carry a deterministic sentinel `project_id` so the composite keys stay whole and enforced.

  scope_level = 'project'       project_id is a real project. Unchanged.
  scope_level = 'organization'  project_id is `__org_price_scope__`, a name no project has.

The sentinel needs no row anywhere: nothing in Finance has a foreign key to `projects` --
verified, zero constraints -- and `project_id` is free-form text. It is an identity inside
the finance tables and nothing else. `sample_site_01` was NOT reused: it is seed data, not
a formally defined organization scope, and borrowing it would make demo rows
indistinguishable from company prices.

WHY UNIQUENESS NEEDS NO CHANGE

Every unique constraint here already begins `(organization_id, project_id, ...)`, including
`ux_price_observations_fingerprint`. The sentinel is a different `project_id`, so
organization-scoped rows get their own namespace for free: an organization row and a
project row cannot collide, re-importing an organization sheet is still idempotent against
its own fingerprint, and no existing ON CONFLICT clause changes.

WHAT IT DOES NOT DO

It does not move the 14,258 historical rows. They stay project-scoped, readable and
current for the projects that own them. Backfilling them into one organization copy means
choosing which of six imports is the truth and deleting five, and that is a decision about
data, not a schema change.
"""

from alembic import op
from sqlalchemy import DDL

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None

#: The project_id organization-scoped rows carry. Deterministic, and deliberately not a
#: name a project could have: no real project id begins and ends with a double underscore.
#: Repeated in `domain/price_scope.py` for the application; a migration states the value it
#: writes rather than importing one that a later edit could change under it.
ORGANIZATION_SENTINEL_PROJECT = "__org_price_scope__"

#: The four tables a sheet import writes, in dependency order.
_SCOPED_TABLES = ("price_providers", "provider_items", "price_collection_runs",
                  "price_observations")

UPGRADE_SQL = "\n".join(
    """
ALTER TABLE {table}
    ADD COLUMN IF NOT EXISTS scope_level text NOT NULL DEFAULT 'project';

-- Every row that exists was written for one project, and the DEFAULT above has already
-- said so for each of them. Stated again explicitly so the backfill is visible in the
-- migration rather than implied by a column default a later edit might drop.
UPDATE {table} SET scope_level = 'project' WHERE scope_level IS NULL;

ALTER TABLE {table}
    ADD CONSTRAINT {table}_scope_level_check
    CHECK (scope_level IN ('project', 'organization'));

-- The sentinel and the scope have to agree in both directions. Half of this rule caught
-- nothing on its own: an organization row with a real project_id would be invisible to
-- the resolver, and a project row parked on the sentinel would be visible to every
-- project in the company. Both are silent.
ALTER TABLE {table}
    ADD CONSTRAINT {table}_scope_matches_project
    CHECK ((scope_level = 'organization') = (project_id = '{sentinel}'));
""".format(table=table, sentinel=ORGANIZATION_SENTINEL_PROJECT)
    for table in _SCOPED_TABLES)

#: One index per table, on the columns the resolver actually filters by. Not one per
#: column: an index nobody's WHERE clause matches is write cost with no read to pay for it.
UPGRADE_SQL += """
CREATE INDEX IF NOT EXISTS ix_price_observations_scope_lookup
    ON price_observations (organization_id, scope_level, provider_item_id,
                           workflow_date_gregorian DESC);

CREATE INDEX IF NOT EXISTS ix_provider_items_scope_lookup
    ON provider_items (organization_id, scope_level, provider_id, external_id);

CREATE INDEX IF NOT EXISTS ix_price_providers_scope_lookup
    ON price_providers (organization_id, scope_level, domain);
"""

DOWNGRADE_SQL = """
DROP INDEX IF EXISTS ix_price_providers_scope_lookup;
DROP INDEX IF EXISTS ix_provider_items_scope_lookup;
DROP INDEX IF EXISTS ix_price_observations_scope_lookup;
""" + "\n".join(
    """
ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_scope_matches_project;
ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_scope_level_check;
ALTER TABLE {table} DROP COLUMN IF EXISTS scope_level;
""".format(table=table)
    for table in reversed(_SCOPED_TABLES))


def upgrade():
    op.execute(DDL(UPGRADE_SQL))


def downgrade():
    # Dropping `scope_level` loses the distinction, so any organization-scoped rows written
    # while it existed would come back as ordinary rows of a project called
    # `__org_price_scope__`. That is recoverable -- the sentinel still names them -- and it
    # is why the sentinel is a readable string rather than a uuid.
    op.execute(DDL(DOWNGRADE_SQL))
