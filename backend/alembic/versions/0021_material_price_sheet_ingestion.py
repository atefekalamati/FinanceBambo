"""make the existing price-intelligence tables able to hold a spreadsheet source

Revision ID: 0021
Revises: 0020

WHAT ALREADY EXISTED, AND IS REUSED UNCHANGED

Revision 0008 laid down the whole provider-neutral price shape -- `price_providers`,
`provider_items`, `price_collection_runs`, `price_observations`,
`provider_resource_mappings`, `price_resolution_policies` -- and nothing has ever written
to it. This revision does not rebuild any of that. `price_observations` already keeps the
raw price as text, a nullable normalised IRR amount, a TOMAN source currency, a raw_data
document, a validation status with a `needs_review` value, and nullable mapping/resource
columns so an unmapped row is storable. All of that is what a sheet row needs.

WHAT WAS MISSING, AND WHY EACH COLUMN IS HERE

Every item below comes from reading the actual sheet (see
`docs/MATERIAL_PRICE_SHEET_CONTRACT_FA.md`), not from imagining one.

  * `provider_type` permitted only 'website' and `crawl_method` only json/html/browser/
    disabled. A Google Sheet is neither crawled nor a website, and calling it one would
    make every later reader guess. Both vocabularies gain one value.

  * The sheet's date column has EIGHT spellings across four real days -- Persian and ASCII
    digits, slash and dash, padded and not, plus 279 cells Google had already turned into a
    Gregorian datetime. So three columns rather than one: the cell exactly as received, the
    Jalali reading when it parses, and the Gregorian date when THAT parses. Any of them may
    be null, and a null means "this could not be read", never "today".

  * `observed_at` is NOT NULL and always was, but the sheet states no provider observation
    time. Rather than let that column silently mean four different things,
    `observed_at_source` says which one it holds. A reader who needs a real provider
    timestamp can now tell that it does not have one.

  * Brick carries a second price -- `قیمت در هر مترمربع`, present on 205 of 213 rows. It is
    not the primary price and must never be shown as one, so it gets its own nullable
    column instead of being folded into the main amount.

  * `row_fingerprint` is what makes an import idempotent. The natural identity of a sheet
    observation is (provider item, workflow date, price), because the duplicate productIds
    turned out to be one product on two dates. Re-running the same import must not double
    the rows, and the database is the right place for that to be impossible rather than
    merely unlikely.

  * `provider_items.active` exists for the 80 rows of the 1072 in the pipe sheet that are
    not pipes: fittings, valves, teflon tape. They are imported and kept -- the raw history
    is not edited -- but they are not part of the active pipe list, and `inactive_reason`
    records why in words rather than leaving a bare false.

TWO NEW TABLES, BOTH APPEND-ONLY

  * `material_unit_settings` -- which unit an authorised Finance user has chosen to display
    a category in. Versioned and append-only exactly like `price_versions` and
    `unit_conversions`, because a unit change is a decision and the previous decision stays
    readable. The sheet's own unit never becomes this by itself.

  * `provider_item_unit_factors` -- a product-specific conversion factor, for the crossings
    that no dimension table can answer: piece to kilogram for one brick, branch to kilogram
    for one beam. `unit_conversions` stays the place for dimension-compatible factors and is
    not touched; this is for factors that belong to one listing and nothing else. Append-only
    for the same reason, and it records who supplied the number and where it came from.

WHAT THIS DOES NOT DO

No table is dropped, renamed or rewritten. No trigger is disabled. No row of financial data
is written, backfilled or deleted. `price_versions`, `estimate_lines`, `invoices` and
`report_snapshots` are not touched at all -- an observation is evidence, and turning
evidence into an official price stays a person's decision.
"""

from alembic import op
from sqlalchemy import DDL


revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


UPGRADE_SQL = r"""
-- ---------------------------------------------------------------- provider vocabulary
ALTER TABLE price_providers
    DROP CONSTRAINT IF EXISTS price_providers_provider_type_check;
ALTER TABLE price_providers
    ADD CONSTRAINT price_providers_provider_type_check
    CHECK (provider_type IN ('website', 'spreadsheet'));

ALTER TABLE price_providers
    DROP CONSTRAINT IF EXISTS price_providers_crawl_method_check;
ALTER TABLE price_providers
    ADD CONSTRAINT price_providers_crawl_method_check
    CHECK (crawl_method IN ('json', 'html', 'browser', 'google_sheet', 'disabled'));

-- ------------------------------------------------------------------- provider items
-- The pipe sheet holds 80 rows that are not pipes. They are imported and kept; they are
-- not active. A reason in words, because `active = false` on its own tells the next
-- reader nothing about whether it was a decision or an accident.
ALTER TABLE provider_items
    ADD COLUMN IF NOT EXISTS active boolean NOT NULL DEFAULT true;
ALTER TABLE provider_items
    ADD COLUMN IF NOT EXISTS inactive_reason text;
ALTER TABLE provider_items
    DROP CONSTRAINT IF EXISTS provider_items_inactive_reason_check;
ALTER TABLE provider_items
    ADD CONSTRAINT provider_items_inactive_reason_check
    CHECK (active = true OR length(btrim(coalesce(inactive_reason, ''))) > 0);

-- Which worksheet a listing came from. Text rather than a foreign key: a worksheet is not
-- an entity this database owns, and the sheet may be renamed without anything here being
-- wrong.
ALTER TABLE provider_items
    ADD COLUMN IF NOT EXISTS source_worksheet text;

-- --------------------------------------------------------------- price observations
ALTER TABLE price_observations
    ADD COLUMN IF NOT EXISTS source_document_id text;
ALTER TABLE price_observations
    ADD COLUMN IF NOT EXISTS source_worksheet text;
ALTER TABLE price_observations
    ADD COLUMN IF NOT EXISTS source_row_number integer
        CHECK (source_row_number IS NULL OR source_row_number > 0);

-- The date column, three ways. All nullable: unreadable is a real answer.
ALTER TABLE price_observations
    ADD COLUMN IF NOT EXISTS workflow_date_raw text;
ALTER TABLE price_observations
    ADD COLUMN IF NOT EXISTS workflow_date_jalali text;
ALTER TABLE price_observations
    ADD COLUMN IF NOT EXISTS workflow_date_gregorian date;

-- What `observed_at` actually holds, so it cannot be mistaken for a provider timestamp
-- the sheet never supplied.
ALTER TABLE price_observations
    ADD COLUMN IF NOT EXISTS observed_at_source text NOT NULL DEFAULT 'unknown';
ALTER TABLE price_observations
    DROP CONSTRAINT IF EXISTS price_observations_observed_at_source_check;
ALTER TABLE price_observations
    ADD CONSTRAINT price_observations_observed_at_source_check
    CHECK (observed_at_source IN ('provider', 'workflow_date', 'fetch_time', 'unknown'));

-- Brick's second price. Never the primary one.
ALTER TABLE price_observations
    ADD COLUMN IF NOT EXISTS secondary_price_irr numeric(18,0)
        CHECK (secondary_price_irr IS NULL OR secondary_price_irr >= 0);
ALTER TABLE price_observations
    ADD COLUMN IF NOT EXISTS secondary_price_basis text;
ALTER TABLE price_observations
    DROP CONSTRAINT IF EXISTS price_observations_secondary_price_pair_check;
ALTER TABLE price_observations
    ADD CONSTRAINT price_observations_secondary_price_pair_check
    CHECK ((secondary_price_irr IS NULL AND secondary_price_basis IS NULL)
        OR (secondary_price_irr IS NOT NULL AND secondary_price_basis IS NOT NULL));

-- Idempotency, enforced rather than hoped for.
ALTER TABLE price_observations
    ADD COLUMN IF NOT EXISTS row_fingerprint text;
CREATE UNIQUE INDEX IF NOT EXISTS ux_price_observations_fingerprint
    ON price_observations (organization_id, project_id, provider_item_id, row_fingerprint)
    WHERE row_fingerprint IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_price_observations_item_workflow_date
    ON price_observations (organization_id, project_id, provider_item_id,
                           workflow_date_gregorian DESC NULLS LAST, fetched_at DESC);

-- ------------------------------------------------------------- collection run detail
-- A run that read five worksheets and failed on one is neither a success nor a failure,
-- and `status` alone cannot say which worksheet. These say it.
ALTER TABLE price_collection_runs
    ADD COLUMN IF NOT EXISTS source_document_id text;
ALTER TABLE price_collection_runs
    ADD COLUMN IF NOT EXISTS worksheet_report jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE price_collection_runs
    ADD COLUMN IF NOT EXISTS rejected_items integer NOT NULL DEFAULT 0
        CHECK (rejected_items >= 0);
ALTER TABLE price_collection_runs
    ADD COLUMN IF NOT EXISTS published_at timestamptz;

-- One run at a time per provider. A partial import racing another partial import is how a
-- price set ends up half from each.
CREATE UNIQUE INDEX IF NOT EXISTS ux_price_collection_runs_one_running
    ON price_collection_runs (organization_id, project_id, provider_id)
    WHERE status = 'running';

-- -------------------------------------------------------------- unit configuration
-- Append-only and versioned, like every other decision in this schema. The unit a category
-- is displayed in is a choice an authorised person made on a date, and the previous choice
-- stays readable afterwards.
CREATE TABLE IF NOT EXISTS material_unit_settings (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    project_id text NOT NULL,
    category text NOT NULL CHECK (length(btrim(category)) > 0),
    resource_id uuid,
    version integer NOT NULL CHECK (version > 0),
    display_unit text NOT NULL CHECK (length(btrim(display_unit)) > 0),
    reason text NOT NULL CHECK (length(btrim(reason)) > 0),
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, project_id, id),
    FOREIGN KEY (organization_id, project_id, resource_id)
        REFERENCES finance_resources (organization_id, project_id, id) ON DELETE RESTRICT
);

-- Two partial uniques rather than one over a nullable column: in SQL two NULLs are not
-- equal, so a plain UNIQUE would let the category-wide setting be inserted twice at the
-- same version and neither row would be wrong by the constraint's reckoning.
CREATE UNIQUE INDEX IF NOT EXISTS ux_material_unit_settings_category_version
    ON material_unit_settings (organization_id, project_id, category, version)
    WHERE resource_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_material_unit_settings_resource_version
    ON material_unit_settings (organization_id, project_id, category, resource_id, version)
    WHERE resource_id IS NOT NULL;

-- ------------------------------------------------------ product-specific conversions
-- `unit_conversions` answers "how many grams in a kilogram" and keeps doing so. This
-- answers "how many kilograms is THIS brick", which is a fact about one listing and cannot
-- live in a dimension table without being wrong for every other listing.
CREATE TABLE IF NOT EXISTS provider_item_unit_factors (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    project_id text NOT NULL,
    provider_item_id uuid NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    from_unit text NOT NULL CHECK (length(btrim(from_unit)) > 0),
    to_unit text NOT NULL CHECK (length(btrim(to_unit)) > 0),
    factor numeric(24,8) NOT NULL CHECK (factor > 0),
    -- Where the number came from. 'sheet_attribute' means it was read off a column the
    -- sheet states; 'manual' means a person supplied it. Nothing else may set one.
    origin text NOT NULL CHECK (origin IN ('sheet_attribute', 'manual')),
    reason text NOT NULL CHECK (length(btrim(reason)) > 0),
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (from_unit <> to_unit),
    UNIQUE (organization_id, project_id, id),
    UNIQUE (organization_id, project_id, provider_item_id, from_unit, to_unit, version),
    FOREIGN KEY (organization_id, project_id, provider_item_id)
        REFERENCES provider_items (organization_id, project_id, id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_provider_item_unit_factors_lookup
    ON provider_item_unit_factors (organization_id, project_id, provider_item_id,
                                   from_unit, to_unit, version DESC);
"""


DOWNGRADE_SQL = r"""
DROP TABLE IF EXISTS provider_item_unit_factors;
DROP TABLE IF EXISTS material_unit_settings;

DROP INDEX IF EXISTS ux_price_collection_runs_one_running;
ALTER TABLE price_collection_runs
    DROP COLUMN IF EXISTS published_at,
    DROP COLUMN IF EXISTS rejected_items,
    DROP COLUMN IF EXISTS worksheet_report,
    DROP COLUMN IF EXISTS source_document_id;

DROP INDEX IF EXISTS ix_price_observations_item_workflow_date;
DROP INDEX IF EXISTS ux_price_observations_fingerprint;
ALTER TABLE price_observations
    DROP CONSTRAINT IF EXISTS price_observations_secondary_price_pair_check;
ALTER TABLE price_observations
    DROP CONSTRAINT IF EXISTS price_observations_observed_at_source_check;
ALTER TABLE price_observations
    DROP COLUMN IF EXISTS row_fingerprint,
    DROP COLUMN IF EXISTS secondary_price_basis,
    DROP COLUMN IF EXISTS secondary_price_irr,
    DROP COLUMN IF EXISTS observed_at_source,
    DROP COLUMN IF EXISTS workflow_date_gregorian,
    DROP COLUMN IF EXISTS workflow_date_jalali,
    DROP COLUMN IF EXISTS workflow_date_raw,
    DROP COLUMN IF EXISTS source_row_number,
    DROP COLUMN IF EXISTS source_worksheet,
    DROP COLUMN IF EXISTS source_document_id;

ALTER TABLE provider_items
    DROP CONSTRAINT IF EXISTS provider_items_inactive_reason_check;
ALTER TABLE provider_items
    DROP COLUMN IF EXISTS source_worksheet,
    DROP COLUMN IF EXISTS inactive_reason,
    DROP COLUMN IF EXISTS active;

-- The vocabularies go back to what 0008 declared. This is the one part of the downgrade
-- that can REFUSE: a row whose provider_type is 'spreadsheet' fails the restored check,
-- and it should -- silently deleting a provider to make a downgrade succeed would be
-- destroying the thing the downgrade is supposed to be protecting.
ALTER TABLE price_providers
    DROP CONSTRAINT IF EXISTS price_providers_crawl_method_check;
ALTER TABLE price_providers
    ADD CONSTRAINT price_providers_crawl_method_check
    CHECK (crawl_method IN ('json', 'html', 'browser', 'disabled'));

ALTER TABLE price_providers
    DROP CONSTRAINT IF EXISTS price_providers_provider_type_check;
ALTER TABLE price_providers
    ADD CONSTRAINT price_providers_provider_type_check
    CHECK (provider_type IN ('website'));
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
