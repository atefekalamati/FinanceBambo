# -*- coding: utf-8 -*-
"""item rate links

Revision ID: 0039
Revises: 0038

A crew or a machine on an estimate line is priced by the hour, and the hourly rates a
project keeps are `price_versions` rows on `work` resources -- set in settings under
«قیمت‌گذاری نیرو و تجهیزات». Until now the only way to give such a LINE one of those
rates was to type it again on the line's own resource. This table records the other
way: a link from the line to the resource whose rate it uses, so one rate set once in
settings prices every line linked to it, and a revision of that rate reaches them all.

One live link per line; a new link supersedes the old one, appended and never deleted,
because a report issued while the old link was in force was calculated with it. The
resolver reads the link's time (`created_at`) against the time a rate was typed on the
line's own resource, and the newer decision wins -- the rule of 2026-09-27.

No row is written by this revision.
"""
from alembic import op
from sqlalchemy import DDL

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None

UPGRADE_SQL = """
CREATE TABLE IF NOT EXISTS finance_item_rate_links (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    project_id text NOT NULL,
    estimate_line_id uuid NOT NULL,
    -- The resource whose hourly rate prices the line. Not the line's own resource.
    rate_resource_id uuid NOT NULL,
    reason text NOT NULL CHECK (btrim(reason) <> ''),
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    superseded_at timestamptz,
    FOREIGN KEY (organization_id, project_id, estimate_line_id)
        REFERENCES estimate_lines (organization_id, project_id, id) ON DELETE NO ACTION,
    FOREIGN KEY (organization_id, project_id, rate_resource_id)
        REFERENCES finance_resources (organization_id, project_id, id) ON DELETE NO ACTION
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_finance_item_rate_links_live
    ON finance_item_rate_links (organization_id, project_id, estimate_line_id)
    WHERE superseded_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_finance_item_rate_links_resource
    ON finance_item_rate_links (organization_id, project_id, rate_resource_id);
"""

DOWNGRADE_SQL = """
DROP INDEX IF EXISTS ix_finance_item_rate_links_resource;
DROP INDEX IF EXISTS ux_finance_item_rate_links_live;
DROP TABLE IF EXISTS finance_item_rate_links;
"""


def upgrade():
    op.execute(DDL(UPGRADE_SQL))


def downgrade():
    op.execute(DDL(DOWNGRADE_SQL))
