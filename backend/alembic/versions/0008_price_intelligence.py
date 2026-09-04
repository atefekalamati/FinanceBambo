"""add provider-neutral price intelligence storage

Revision ID: 0008
Revises: 0007

External prices are evidence, not official Finance prices.  This revision keeps raw
observations separate from the existing append-only ``price_versions`` ledger so a
failed mapping, stale source or anomalous value can never silently affect reports.
"""

from alembic import op
from sqlalchemy import DDL


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


UPGRADE_SQL = r"""
CREATE TABLE price_providers (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    project_id text NOT NULL,
    name text NOT NULL CHECK (length(btrim(name)) > 0),
    domain text NOT NULL CHECK (length(btrim(domain)) > 0),
    description text,
    provider_type text NOT NULL CHECK (provider_type IN ('website')),
    crawl_method text NOT NULL CHECK (crawl_method IN ('json', 'html', 'browser', 'disabled')),
    active boolean NOT NULL DEFAULT false,
    default_interval_minutes integer NOT NULL CHECK (default_interval_minutes > 0),
    last_success_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, project_id, id),
    UNIQUE (organization_id, project_id, domain)
);

CREATE TABLE provider_items (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    project_id text NOT NULL,
    provider_id uuid NOT NULL,
    external_id text NOT NULL CHECK (length(btrim(external_id)) > 0),
    external_name text NOT NULL CHECK (length(btrim(external_name)) > 0),
    category text NOT NULL CHECK (length(btrim(category)) > 0),
    url text NOT NULL CHECK (length(btrim(url)) > 0),
    source_unit text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, project_id, id),
    UNIQUE (organization_id, project_id, provider_id, external_id),
    FOREIGN KEY (organization_id, project_id, provider_id)
        REFERENCES price_providers (organization_id, project_id, id) ON DELETE RESTRICT
);

CREATE TABLE provider_resource_mappings (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    project_id text NOT NULL,
    provider_item_id uuid NOT NULL,
    finance_resource_id uuid NOT NULL,
    confidence_score numeric(5,4) NOT NULL CHECK (confidence_score >= 0 AND confidence_score <= 1),
    approved boolean NOT NULL DEFAULT false,
    approved_by uuid,
    approved_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((approved = false AND approved_by IS NULL AND approved_at IS NULL)
        OR (approved = true AND approved_by IS NOT NULL AND approved_at IS NOT NULL)),
    UNIQUE (organization_id, project_id, id),
    UNIQUE (organization_id, project_id, provider_item_id, finance_resource_id),
    FOREIGN KEY (organization_id, project_id, provider_item_id)
        REFERENCES provider_items (organization_id, project_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (organization_id, project_id, finance_resource_id)
        REFERENCES finance_resources (organization_id, project_id, id) ON DELETE RESTRICT
);

CREATE TABLE price_collection_runs (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    project_id text NOT NULL,
    provider_id uuid NOT NULL,
    started_at timestamptz NOT NULL,
    finished_at timestamptz,
    status text NOT NULL CHECK (status IN ('running', 'succeeded', 'partially_succeeded', 'failed')),
    total_items integer NOT NULL DEFAULT 0 CHECK (total_items >= 0),
    successful_items integer NOT NULL DEFAULT 0 CHECK (successful_items >= 0),
    failed_items integer NOT NULL DEFAULT 0 CHECK (failed_items >= 0),
    error_message text,
    CHECK (successful_items + failed_items <= total_items),
    UNIQUE (organization_id, project_id, id),
    FOREIGN KEY (organization_id, project_id, provider_id)
        REFERENCES price_providers (organization_id, project_id, id) ON DELETE RESTRICT
);

CREATE TABLE price_observations (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    project_id text NOT NULL,
    provider_id uuid NOT NULL,
    provider_item_id uuid NOT NULL,
    mapping_id uuid,
    resource_id uuid,
    collection_run_id uuid NOT NULL,
    raw_price text NOT NULL CHECK (length(btrim(raw_price)) > 0),
    normalized_price_irr numeric(18,0),
    source_currency text NOT NULL CHECK (source_currency IN ('IRR', 'TOMAN')),
    source_unit text,
    normalized_unit text,
    source_url text NOT NULL CHECK (length(btrim(source_url)) > 0),
    observed_at timestamptz NOT NULL,
    fetched_at timestamptz NOT NULL,
    availability text NOT NULL CHECK (availability IN ('available', 'unavailable', 'unknown')),
    validation_status text NOT NULL CHECK (validation_status IN ('pending', 'valid', 'needs_review', 'rejected')),
    confidence_score numeric(5,4) CHECK (confidence_score >= 0 AND confidence_score <= 1),
    validation_reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
    raw_data jsonb NOT NULL,
    price_version_id uuid,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((mapping_id IS NULL AND resource_id IS NULL)
        OR (mapping_id IS NOT NULL AND resource_id IS NOT NULL)),
    UNIQUE (organization_id, project_id, id),
    FOREIGN KEY (organization_id, project_id, provider_id)
        REFERENCES price_providers (organization_id, project_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (organization_id, project_id, provider_item_id)
        REFERENCES provider_items (organization_id, project_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (organization_id, project_id, mapping_id)
        REFERENCES provider_resource_mappings (organization_id, project_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (organization_id, project_id, resource_id)
        REFERENCES finance_resources (organization_id, project_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (organization_id, project_id, collection_run_id)
        REFERENCES price_collection_runs (organization_id, project_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (organization_id, project_id, price_version_id)
        REFERENCES price_versions (organization_id, project_id, id) ON DELETE RESTRICT
);

CREATE TABLE price_collection_schedules (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    project_id text NOT NULL,
    provider_id uuid NOT NULL,
    category text NOT NULL CHECK (length(btrim(category)) > 0),
    interval_minutes integer NOT NULL CHECK (interval_minutes > 0),
    enabled boolean NOT NULL DEFAULT false,
    next_run_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, project_id, provider_id, category),
    FOREIGN KEY (organization_id, project_id, provider_id)
        REFERENCES price_providers (organization_id, project_id, id) ON DELETE RESTRICT
);

CREATE TABLE price_resolution_policies (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    project_id text NOT NULL,
    resource_id uuid NOT NULL,
    strategy text NOT NULL CHECK (strategy IN ('median', 'preferred_provider', 'weighted_provider', 'manual_approval')),
    preferred_provider_id uuid,
    provider_weights jsonb NOT NULL DEFAULT '{}'::jsonb,
    anomaly_threshold_percent numeric(9,4) NOT NULL CHECK (anomaly_threshold_percent > 0),
    max_age_minutes integer NOT NULL CHECK (max_age_minutes > 0),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, project_id, resource_id),
    FOREIGN KEY (organization_id, project_id, resource_id)
        REFERENCES finance_resources (organization_id, project_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (organization_id, project_id, preferred_provider_id)
        REFERENCES price_providers (organization_id, project_id, id) ON DELETE RESTRICT
);

CREATE INDEX ix_price_providers_scope_active
    ON price_providers (organization_id, project_id, active);
CREATE INDEX ix_provider_items_scope_provider
    ON provider_items (organization_id, project_id, provider_id, category);
CREATE INDEX ix_provider_mappings_scope_resource
    ON provider_resource_mappings (organization_id, project_id, finance_resource_id, approved);
CREATE INDEX ix_price_collection_runs_scope_provider_started
    ON price_collection_runs (organization_id, project_id, provider_id, started_at DESC);
CREATE INDEX ix_price_observations_scope_resource_observed
    ON price_observations (organization_id, project_id, resource_id, observed_at DESC);
CREATE INDEX ix_price_observations_scope_status
    ON price_observations (organization_id, project_id, validation_status, fetched_at DESC);
CREATE INDEX ix_price_collection_schedules_due
    ON price_collection_schedules (enabled, next_run_at) WHERE enabled = true;

CREATE TRIGGER price_observations_immutable
BEFORE UPDATE OR DELETE ON price_observations
FOR EACH ROW EXECUTE FUNCTION finance_reject_mutation();
"""


DOWNGRADE_SQL = r"""
DROP TABLE IF EXISTS price_resolution_policies;
DROP TABLE IF EXISTS price_collection_schedules;
DROP TABLE IF EXISTS price_observations;
DROP TABLE IF EXISTS price_collection_runs;
DROP TABLE IF EXISTS provider_resource_mappings;
DROP TABLE IF EXISTS provider_items;
DROP TABLE IF EXISTS price_providers;
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
