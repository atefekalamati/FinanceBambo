"""a price somebody typed is not a price the sheet published, and says so

Revision ID: 0032
Revises: 0031

WHAT WAS IMPOSSIBLE

Every row in `price_observations` was an imported one by construction:
`collection_run_id` and `source_url` are NOT NULL, and both are facts about an import. A
person who telephoned a supplier for a quote had nowhere to put it -- so a project whose
sheet covers a fraction of what it buys had no daily price for the rest, and no way to
record one.

WHAT THIS ADDS, AND THE SHAPE OF THE RULE

`origin` on both tables, a provider vocabulary with room for a supplier nobody crawls,
and a manual row keeps the import columns EMPTY rather than
filling them with something plausible. Two CHECKs, not one, because they are two rules
and a reader should be able to fail one without reading the other:

    a manual row      states who entered it and why, and names no run and no url
    a sheet row       names its run and its url

Every existing row is `sheet`, which is true of all 8,696 of them: nothing else could
have been written.

WHY A CATEGORY TABLE WHEN CATEGORIES ALREADY WORK

They already work and this does not replace them. The chips on the prices page are
counted from `provider_items.category` and still are; a manual listing is born with a
category in that same column, so its chip appears by the same mechanism as every other.

The table holds the two things a column cannot:

  * A LEVEL. "Scaffolding" may be this project's word, this organization's, or BAMBO's,
    and a text column on a listing has nowhere to say which.
  * A CATEGORY WITH NOTHING IN IT YET. Somebody declares the category, then records the
    first price against it. Between those two acts the category exists and `GROUP BY
    category` cannot see it, because there is nothing to group.

WHAT IT IS NOT

It is not a foreign key. `provider_items.category` is not constrained to this table and
must not be: the sheet arrives with whatever categories it arrives with, and an import
that failed because a category had not been declared first would make the declaration a
prerequisite for reading a spreadsheet nobody here controls.
"""

from alembic import op
from sqlalchemy import DDL


revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


UPGRADE_SQL = r"""
-- ------------------------------------------------------------------ where a row came from
ALTER TABLE provider_items
    ADD COLUMN IF NOT EXISTS origin text NOT NULL DEFAULT 'sheet';

ALTER TABLE provider_items
    ADD CONSTRAINT provider_items_origin_vocabulary
        CHECK (origin IN ('sheet', 'manual'));

-- A listing nobody fetched has no address, and `url` was NOT NULL because until now
-- every listing was fetched. The same move as `price_observations.source_url` below: the
-- requirement leaves the column and becomes a rule about the row, so it can describe both
-- kinds instead of forcing a manual entry to invent an address it does not have.
ALTER TABLE provider_items ALTER COLUMN url DROP NOT NULL;

ALTER TABLE provider_items
    ADD CONSTRAINT provider_items_sheet_has_its_url
        CHECK (origin = 'manual' OR url IS NOT NULL);

COMMENT ON COLUMN provider_items.origin IS
    'sheet: the importer created this listing from the configured workbook. manual: a '
    'person entered it. The importer never writes a manual row -- its upsert is scoped '
    'to origin = ''sheet'' -- so a re-import cannot overwrite or deactivate a price '
    'somebody recorded by hand.';

-- ------------------------------------------------------ a supplier nobody crawls
-- Every provider so far was a website or a spreadsheet, and every one of them was reached
-- by fetching something. A person telephoning a supplier is neither, and the honest way to
-- record that is to widen the vocabulary rather than to file the entry under 'spreadsheet'
-- -- which would be false, and false in exactly the direction this whole revision exists to
-- prevent: a price that did not come from the sheet claiming that it did.
ALTER TABLE price_providers DROP CONSTRAINT IF EXISTS price_providers_provider_type_check;
ALTER TABLE price_providers
    ADD CONSTRAINT price_providers_provider_type_check
        CHECK (provider_type IN ('website', 'spreadsheet', 'manual'));

ALTER TABLE price_providers DROP CONSTRAINT IF EXISTS price_providers_crawl_method_check;
ALTER TABLE price_providers
    ADD CONSTRAINT price_providers_crawl_method_check
        CHECK (crawl_method IN ('json', 'html', 'browser', 'google_sheet', 'disabled',
                                'manual_entry'));

-- ------------------------------------------------- an observation that is not an import
-- The two import columns stop being mandatory. They do NOT become optional: the CHECKs
-- below require them on exactly the rows that are imports, so the rule moves from the
-- column to the row and gains the ability to describe both kinds.
ALTER TABLE price_observations ALTER COLUMN source_url DROP NOT NULL;
ALTER TABLE price_observations ALTER COLUMN collection_run_id DROP NOT NULL;

ALTER TABLE price_observations
    ADD COLUMN IF NOT EXISTS origin text NOT NULL DEFAULT 'sheet',
    ADD COLUMN IF NOT EXISTS entered_by uuid,
    ADD COLUMN IF NOT EXISTS reason text;

ALTER TABLE price_observations
    ADD CONSTRAINT price_observations_origin_vocabulary
        CHECK (origin IN ('sheet', 'manual'));

-- A hand-entered price states who entered it and why. A price with no author is one
-- nobody can question later, and the reason is the only thing that distinguishes a quote
-- from a guess.
ALTER TABLE price_observations
    ADD CONSTRAINT price_observations_manual_is_attributed CHECK (
        origin = 'sheet'
        OR (entered_by IS NOT NULL AND reason IS NOT NULL
            AND collection_run_id IS NULL AND source_url IS NULL));

-- And an imported price still names the run that read it and the address it came from.
-- Dropping the NOT NULL above would otherwise have quietly permitted an import with
-- neither.
ALTER TABLE price_observations
    ADD CONSTRAINT price_observations_sheet_has_its_run CHECK (
        origin = 'manual' OR (collection_run_id IS NOT NULL AND source_url IS NOT NULL));

-- "Which prices did a person enter" -- asked by the prices page on every load.
CREATE INDEX IF NOT EXISTS ix_price_observations_manual
    ON price_observations (organization_id, project_id, provider_item_id)
 WHERE origin = 'manual';

-- --------------------------------------------------------------- declared categories
CREATE TABLE IF NOT EXISTS finance_price_categories (
    id               uuid PRIMARY KEY,
    organization_id  uuid NOT NULL,
    -- NULL at organization and global level. The scope CHECK below keeps the column and
    -- the level from disagreeing.
    project_id       text,
    scope_level      text NOT NULL
        CHECK (scope_level IN ('project', 'organization', 'global')),
    category         text NOT NULL CHECK (btrim(category) <> ''),
    label            text,
    created_by       uuid NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT finance_price_category_scope_columns CHECK (
        (scope_level = 'project' AND project_id IS NOT NULL)
        OR (scope_level <> 'project' AND project_id IS NULL)),
    UNIQUE (organization_id, project_id, category)
);

COMMENT ON TABLE finance_price_categories IS
    'Categories a person declared, with the level they belong to. It does NOT replace '
    'provider_items.category -- the chips are still counted from that column and a '
    'manual listing is born with its category there. This table holds the two things '
    'that column cannot: which level a category belongs to, and a category that exists '
    'before any product has been recorded in it.';

CREATE INDEX IF NOT EXISTS ix_finance_price_categories_scope
    ON finance_price_categories (organization_id, scope_level, project_id);
"""


DOWNGRADE_SQL = r"""
-- The widened provider vocabulary STAYS, deliberately, and this is the same decision the
-- nullable columns below record. Narrowing it again would fail on any manual provider row,
-- and the only way to make it succeed would be to delete that row -- which is evidence
-- somebody recorded a price. A downgrade that destroys data to make a constraint fit is
-- not a downgrade, so this one leaves two unused words in a CHECK and says why.

DROP INDEX IF EXISTS ix_finance_price_categories_scope;
DROP TABLE IF EXISTS finance_price_categories;

DROP INDEX IF EXISTS ix_price_observations_manual;
ALTER TABLE price_observations
    DROP CONSTRAINT IF EXISTS price_observations_sheet_has_its_run;
ALTER TABLE price_observations
    DROP CONSTRAINT IF EXISTS price_observations_manual_is_attributed;
ALTER TABLE price_observations
    DROP CONSTRAINT IF EXISTS price_observations_origin_vocabulary;
ALTER TABLE price_observations
    DROP COLUMN IF EXISTS reason,
    DROP COLUMN IF EXISTS entered_by,
    DROP COLUMN IF EXISTS origin;

-- Restoring the NOT NULLs -- on `price_observations.collection_run_id` and `source_url`
-- above, and on `provider_items.url` here -- would fail on any manual row, and those rows
-- are evidence a person recorded a price. The downgrade therefore leaves the columns
-- nullable and says so rather than destroying the rows to make a schema fit.
ALTER TABLE provider_items
    DROP CONSTRAINT IF EXISTS provider_items_sheet_has_its_url;
ALTER TABLE provider_items
    DROP CONSTRAINT IF EXISTS provider_items_origin_vocabulary;
ALTER TABLE provider_items
    DROP COLUMN IF EXISTS origin;
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
