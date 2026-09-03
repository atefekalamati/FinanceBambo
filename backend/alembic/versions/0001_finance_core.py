"""finance core schema

The 15 finance tables, their composite tenant foreign keys, the CHECK and UNIQUE
constraints, the scope indexes, and the trigger function plus triggers that make the
history tables append-only.

Converted from migrations/0001_finance_core.up.sql and .down.sql, which Git history keeps.
The SQL is embedded unchanged apart from the outer BEGIN/COMMIT: Alembic owns the
transaction boundary, and opening a second one inside it is an error.

The SQL travels as a `DDL` construct rather than a plain string. `op.execute` on a string
parses it for `:name` bind parameters, which would misread PostgreSQL cast syntax and
dollar-quoted function bodies; `DDL` skips that parsing and passes the whole batch through
as it stood in the file. It also works in offline mode (`alembic upgrade head --sql`), where
the mock connection has no `exec_driver_sql` to call.

Revision ID: 0001
Revises: (none, this is the base revision)
"""

from alembic import op
from sqlalchemy import DDL

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


UPGRADE_SQL = """\
CREATE OR REPLACE FUNCTION finance_reject_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'immutable finance history cannot be updated or deleted';
END;
$$;

CREATE TABLE IF NOT EXISTS finance_project_settings (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    project_id text NOT NULL,
    revision integer NOT NULL CHECK (revision > 0),
    gross_built_area numeric(18,4) NOT NULL CHECK (gross_built_area > 0),
    currency text NOT NULL DEFAULT 'IRR' CHECK (currency = 'IRR'),
    effective_from date NOT NULL,
    reason text NOT NULL CHECK (length(btrim(reason)) > 0),
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, project_id, id),
    UNIQUE (organization_id, project_id, revision)
);

CREATE TABLE IF NOT EXISTS finance_resources (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    project_id text NOT NULL,
    resource_type text NOT NULL CHECK (resource_type IN ('material', 'labor', 'equipment', 'general_cost')),
    code text NOT NULL,
    title text NOT NULL,
    base_unit text,
    dimension text,
    external_resource_id text,
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at timestamptz,
    deleted_by uuid,
    UNIQUE (organization_id, project_id, id),
    CHECK (
        (resource_type = 'general_cost')
        OR (base_unit IS NOT NULL AND dimension IS NOT NULL)
    ),
    CHECK ((deleted_at IS NULL) = (deleted_by IS NULL))
);

CREATE TABLE IF NOT EXISTS estimate_lines (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    project_id text NOT NULL,
    resource_id uuid NOT NULL,
    activity_external_id text,
    assignment_external_id text,
    original_quantity numeric(18,4),
    original_unit_price_irr numeric(18,0),
    source text NOT NULL CHECK (source IN ('progress_feed', 'excel_import', 'manual_entry')),
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at timestamptz,
    deleted_by uuid,
    UNIQUE (organization_id, project_id, id),
    FOREIGN KEY (organization_id, project_id, resource_id)
        REFERENCES finance_resources (organization_id, project_id, id)
        ON DELETE NO ACTION,
    CHECK ((deleted_at IS NULL) = (deleted_by IS NULL))
);

CREATE TABLE IF NOT EXISTS estimate_revisions (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    project_id text NOT NULL,
    estimate_line_id uuid NOT NULL,
    revision integer NOT NULL CHECK (revision > 0),
    previous_quantity numeric(18,4),
    new_quantity numeric(18,4),
    reason text NOT NULL CHECK (length(btrim(reason)) > 0),
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, project_id, id),
    UNIQUE (organization_id, project_id, estimate_line_id, revision),
    FOREIGN KEY (organization_id, project_id, estimate_line_id)
        REFERENCES estimate_lines (organization_id, project_id, id)
        ON DELETE NO ACTION
);

CREATE TABLE IF NOT EXISTS price_versions (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    project_id text NOT NULL,
    resource_id uuid NOT NULL,
    scope_kind text NOT NULL CHECK (scope_kind IN ('organization', 'project')),
    version integer NOT NULL CHECK (version > 0),
    unit_price_irr numeric(18,0) NOT NULL CHECK (unit_price_irr >= 0),
    effective_from date NOT NULL,
    reason text NOT NULL CHECK (length(btrim(reason)) > 0),
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, project_id, id),
    UNIQUE (organization_id, project_id, resource_id, scope_kind, version),
    FOREIGN KEY (organization_id, project_id, resource_id)
        REFERENCES finance_resources (organization_id, project_id, id)
        ON DELETE NO ACTION
);

CREATE TABLE IF NOT EXISTS unit_conversions (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    project_id text NOT NULL,
    scope_kind text NOT NULL CHECK (scope_kind IN ('organization', 'project')),
    version integer NOT NULL CHECK (version > 0),
    source_unit text NOT NULL,
    target_unit text NOT NULL,
    dimension text NOT NULL,
    factor numeric(24,8) NOT NULL CHECK (factor > 0),
    effective_from date NOT NULL,
    reason text NOT NULL CHECK (length(btrim(reason)) > 0),
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, project_id, id),
    UNIQUE (organization_id, project_id, scope_kind, source_unit, target_unit, dimension, version),
    CHECK (source_unit <> target_unit)
);

CREATE TABLE IF NOT EXISTS progress_snapshot_refs (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    project_id text NOT NULL,
    progress_snapshot_id uuid NOT NULL,
    source_file_version_id uuid NOT NULL,
    source_file_name_safe text NOT NULL,
    reporting_date date NOT NULL,
    snapshot_status text NOT NULL,
    imported_by uuid NOT NULL,
    imported_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, project_id, id),
    UNIQUE (organization_id, project_id, progress_snapshot_id)
);

CREATE TABLE IF NOT EXISTS progress_overrides (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    project_id text NOT NULL,
    estimate_line_id uuid NOT NULL,
    progress_snapshot_ref_id uuid NOT NULL,
    computed_value numeric(18,4) NOT NULL,
    override_value numeric(18,4) NOT NULL,
    reason text NOT NULL CHECK (length(btrim(reason)) > 0),
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, project_id, id),
    FOREIGN KEY (organization_id, project_id, estimate_line_id)
        REFERENCES estimate_lines (organization_id, project_id, id)
        ON DELETE NO ACTION,
    FOREIGN KEY (organization_id, project_id, progress_snapshot_ref_id)
        REFERENCES progress_snapshot_refs (organization_id, project_id, id)
        ON DELETE NO ACTION
);

CREATE TABLE IF NOT EXISTS invoices (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    project_id text NOT NULL,
    invoice_number text,
    invoice_date date NOT NULL,
    vendor_name text NOT NULL,
    description text,
    source text NOT NULL CHECK (source IN ('manual', 'image', 'voice', 'corrective', 'reversal')),
    status text NOT NULL CHECK (status IN ('draft', 'awaitingConfirmation', 'confirmed', 'voided', 'corrected')),
    discount_irr numeric(18,0) NOT NULL DEFAULT 0 CHECK (discount_irr >= 0),
    tax_irr numeric(18,0) NOT NULL DEFAULT 0 CHECK (tax_irr >= 0),
    shipping_irr numeric(18,0) NOT NULL DEFAULT 0 CHECK (shipping_irr >= 0),
    other_costs_irr numeric(18,0) NOT NULL DEFAULT 0 CHECK (other_costs_irr >= 0),
    final_amount_irr numeric(18,0),
    financial_effect_sign smallint NOT NULL DEFAULT 1 CHECK (financial_effect_sign IN (-1, 1)),
    idempotency_key text,
    source_file_sha256 text,
    original_invoice_id uuid,
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    submitted_by uuid NOT NULL,
    confirmed_by uuid,
    confirmed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, project_id, id),
    UNIQUE (organization_id, project_id, idempotency_key),
    FOREIGN KEY (organization_id, project_id, original_invoice_id)
        REFERENCES invoices (organization_id, project_id, id)
        ON DELETE NO ACTION,
    CHECK (
        (status = 'confirmed' AND confirmed_by IS NOT NULL AND confirmed_at IS NOT NULL)
        OR status <> 'confirmed'
    )
);

CREATE TABLE IF NOT EXISTS invoice_lines (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    project_id text NOT NULL,
    invoice_id uuid NOT NULL,
    estimate_line_id uuid,
    resource_id uuid NOT NULL,
    quantity numeric(18,4),
    unit text,
    unit_price_snapshot_irr numeric(18,0),
    raw_amount_irr numeric(18,0) NOT NULL,
    allocated_discount_irr numeric(18,0) NOT NULL DEFAULT 0,
    allocated_tax_irr numeric(18,0) NOT NULL DEFAULT 0,
    allocated_shipping_irr numeric(18,0) NOT NULL DEFAULT 0,
    allocated_other_costs_irr numeric(18,0) NOT NULL DEFAULT 0,
    final_line_amount_irr numeric(18,0) NOT NULL,
    price_version_id uuid,
    description text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, project_id, id),
    FOREIGN KEY (organization_id, project_id, invoice_id)
        REFERENCES invoices (organization_id, project_id, id)
        ON DELETE NO ACTION,
    FOREIGN KEY (organization_id, project_id, estimate_line_id)
        REFERENCES estimate_lines (organization_id, project_id, id)
        ON DELETE NO ACTION,
    FOREIGN KEY (organization_id, project_id, resource_id)
        REFERENCES finance_resources (organization_id, project_id, id)
        ON DELETE NO ACTION,
    FOREIGN KEY (organization_id, project_id, price_version_id)
        REFERENCES price_versions (organization_id, project_id, id)
        ON DELETE NO ACTION
);

CREATE TABLE IF NOT EXISTS finance_attachments (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    project_id text NOT NULL,
    invoice_id uuid,
    logical_type text NOT NULL CHECK (logical_type IN ('invoice_image', 'invoice_voice')),
    original_name_safe text NOT NULL,
    stored_name text NOT NULL,
    mime_type text NOT NULL,
    size_bytes bigint NOT NULL CHECK (size_bytes > 0),
    sha256 text NOT NULL CHECK (length(sha256) = 64),
    storage_key text NOT NULL,
    processing_status text NOT NULL CHECK (processing_status IN ('uploaded', 'processing', 'ready', 'failed')),
    uploaded_by uuid NOT NULL,
    uploaded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at timestamptz,
    deleted_by uuid,
    UNIQUE (organization_id, project_id, id),
    UNIQUE (organization_id, project_id, sha256),
    FOREIGN KEY (organization_id, project_id, invoice_id)
        REFERENCES invoices (organization_id, project_id, id)
        ON DELETE NO ACTION,
    CHECK ((deleted_at IS NULL) = (deleted_by IS NULL))
);

CREATE TABLE IF NOT EXISTS extraction_drafts (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    project_id text NOT NULL,
    attachment_id uuid NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    review_status text NOT NULL CHECK (review_status IN ('awaitingReview', 'accepted', 'rejected')),
    provider_adapter text NOT NULL,
    extracted_fields jsonb NOT NULL,
    confirmed_fields jsonb,
    financial_effect_irr numeric(18,0) NOT NULL DEFAULT 0,
    submitted_by uuid NOT NULL,
    confirmed_by uuid,
    confirmed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, project_id, id),
    UNIQUE (organization_id, project_id, attachment_id, version),
    FOREIGN KEY (organization_id, project_id, attachment_id)
        REFERENCES finance_attachments (organization_id, project_id, id)
        ON DELETE NO ACTION,
    CHECK (financial_effect_irr = 0)
);

CREATE TABLE IF NOT EXISTS report_snapshots (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    project_id text NOT NULL,
    reporting_date date NOT NULL,
    progress_snapshot_ref_id uuid NOT NULL,
    finance_settings_id uuid NOT NULL,
    estimate_revision_ids jsonb NOT NULL,
    price_version_ids jsonb NOT NULL,
    unit_conversion_ids jsonb NOT NULL,
    invoice_ids jsonb NOT NULL,
    calculated_metrics jsonb NOT NULL,
    issued_by uuid NOT NULL,
    issued_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, project_id, id),
    FOREIGN KEY (organization_id, project_id, progress_snapshot_ref_id)
        REFERENCES progress_snapshot_refs (organization_id, project_id, id)
        ON DELETE NO ACTION,
    FOREIGN KEY (organization_id, project_id, finance_settings_id)
        REFERENCES finance_project_settings (organization_id, project_id, id)
        ON DELETE NO ACTION
);

CREATE TABLE IF NOT EXISTS finance_audit_events (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    project_id text NOT NULL,
    actor_user_id uuid NOT NULL,
    action text NOT NULL,
    entity_type text NOT NULL,
    entity_id uuid NOT NULL,
    reason text,
    before_values jsonb,
    after_values jsonb,
    occurred_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, project_id, id)
);

CREATE TABLE IF NOT EXISTS finance_import_batches (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL,
    project_id text NOT NULL,
    import_kind text NOT NULL CHECK (import_kind IN ('estimate', 'prices')),
    currency_unit text CHECK (currency_unit IN ('IRR', 'TOMAN')),
    file_sha256 text NOT NULL CHECK (length(file_sha256) = 64),
    normalized_rows jsonb NOT NULL,
    validation_errors jsonb NOT NULL,
    status text NOT NULL CHECK (status IN ('previewed', 'committed')),
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    committed_at timestamptz,
    UNIQUE (organization_id, project_id, id),
    CHECK ((status = 'committed') = (committed_at IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS ix_finance_project_settings_scope ON finance_project_settings (organization_id, project_id, effective_from);
CREATE INDEX IF NOT EXISTS ix_finance_resources_scope ON finance_resources (organization_id, project_id, resource_type);
CREATE INDEX IF NOT EXISTS ix_estimate_lines_scope ON estimate_lines (organization_id, project_id, resource_id);
CREATE INDEX IF NOT EXISTS ix_estimate_revisions_scope ON estimate_revisions (organization_id, project_id, estimate_line_id);
CREATE INDEX IF NOT EXISTS ix_price_versions_scope ON price_versions (organization_id, project_id, resource_id, effective_from);
CREATE INDEX IF NOT EXISTS ix_unit_conversions_scope ON unit_conversions (organization_id, project_id, source_unit, target_unit, effective_from);
CREATE INDEX IF NOT EXISTS ix_progress_snapshot_refs_scope ON progress_snapshot_refs (organization_id, project_id, reporting_date);
CREATE INDEX IF NOT EXISTS ix_progress_overrides_scope ON progress_overrides (organization_id, project_id, estimate_line_id);
CREATE INDEX IF NOT EXISTS ix_invoices_scope ON invoices (organization_id, project_id, invoice_date, status);
CREATE INDEX IF NOT EXISTS ix_invoice_lines_scope ON invoice_lines (organization_id, project_id, invoice_id);
CREATE INDEX IF NOT EXISTS ix_finance_attachments_scope ON finance_attachments (organization_id, project_id, invoice_id);
CREATE INDEX IF NOT EXISTS ix_extraction_drafts_scope ON extraction_drafts (organization_id, project_id, attachment_id, version);
CREATE INDEX IF NOT EXISTS ix_report_snapshots_scope ON report_snapshots (organization_id, project_id, reporting_date);
CREATE INDEX IF NOT EXISTS ix_finance_audit_events_scope ON finance_audit_events (organization_id, project_id, occurred_at);
CREATE INDEX IF NOT EXISTS ix_finance_import_batches_scope ON finance_import_batches (organization_id, project_id, status, created_at);

CREATE OR REPLACE FUNCTION finance_guard_estimate_original()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.original_quantity IS DISTINCT FROM OLD.original_quantity
       OR NEW.original_unit_price_irr IS DISTINCT FROM OLD.original_unit_price_irr
       OR NEW.resource_id IS DISTINCT FROM OLD.resource_id
       OR NEW.activity_external_id IS DISTINCT FROM OLD.activity_external_id
       OR NEW.assignment_external_id IS DISTINCT FROM OLD.assignment_external_id THEN
        RAISE EXCEPTION 'original estimate fields are immutable';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION finance_guard_confirmed_invoice()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status IN ('confirmed', 'voided', 'corrected') THEN
        RAISE EXCEPTION 'confirmed finance invoices are immutable';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS finance_project_settings_immutable ON finance_project_settings;
CREATE TRIGGER finance_project_settings_immutable BEFORE UPDATE OR DELETE ON finance_project_settings FOR EACH ROW EXECUTE FUNCTION finance_reject_mutation();
DROP TRIGGER IF EXISTS estimate_revisions_immutable ON estimate_revisions;
CREATE TRIGGER estimate_revisions_immutable BEFORE UPDATE OR DELETE ON estimate_revisions FOR EACH ROW EXECUTE FUNCTION finance_reject_mutation();
DROP TRIGGER IF EXISTS price_versions_immutable ON price_versions;
CREATE TRIGGER price_versions_immutable BEFORE UPDATE OR DELETE ON price_versions FOR EACH ROW EXECUTE FUNCTION finance_reject_mutation();
DROP TRIGGER IF EXISTS unit_conversions_immutable ON unit_conversions;
CREATE TRIGGER unit_conversions_immutable BEFORE UPDATE OR DELETE ON unit_conversions FOR EACH ROW EXECUTE FUNCTION finance_reject_mutation();
DROP TRIGGER IF EXISTS progress_snapshot_refs_immutable ON progress_snapshot_refs;
CREATE TRIGGER progress_snapshot_refs_immutable BEFORE UPDATE OR DELETE ON progress_snapshot_refs FOR EACH ROW EXECUTE FUNCTION finance_reject_mutation();
DROP TRIGGER IF EXISTS progress_overrides_immutable ON progress_overrides;
CREATE TRIGGER progress_overrides_immutable BEFORE UPDATE OR DELETE ON progress_overrides FOR EACH ROW EXECUTE FUNCTION finance_reject_mutation();
DROP TRIGGER IF EXISTS report_snapshots_immutable ON report_snapshots;
CREATE TRIGGER report_snapshots_immutable BEFORE UPDATE OR DELETE ON report_snapshots FOR EACH ROW EXECUTE FUNCTION finance_reject_mutation();
DROP TRIGGER IF EXISTS finance_audit_events_immutable ON finance_audit_events;
CREATE TRIGGER finance_audit_events_immutable BEFORE UPDATE OR DELETE ON finance_audit_events FOR EACH ROW EXECUTE FUNCTION finance_reject_mutation();
DROP TRIGGER IF EXISTS estimate_original_fields_immutable ON estimate_lines;
CREATE TRIGGER estimate_original_fields_immutable BEFORE UPDATE ON estimate_lines FOR EACH ROW EXECUTE FUNCTION finance_guard_estimate_original();
DROP TRIGGER IF EXISTS confirmed_invoice_immutable ON invoices;
CREATE TRIGGER confirmed_invoice_immutable BEFORE UPDATE OR DELETE ON invoices FOR EACH ROW EXECUTE FUNCTION finance_guard_confirmed_invoice();
"""


DOWNGRADE_SQL = """\
DROP TABLE IF EXISTS finance_import_batches;

DROP TABLE IF EXISTS finance_audit_events;
DROP TABLE IF EXISTS report_snapshots;
DROP TABLE IF EXISTS extraction_drafts;
DROP TABLE IF EXISTS finance_attachments;
DROP TABLE IF EXISTS invoice_lines;
DROP TABLE IF EXISTS invoices;
DROP TABLE IF EXISTS progress_overrides;
DROP TABLE IF EXISTS progress_snapshot_refs;
DROP TABLE IF EXISTS unit_conversions;
DROP TABLE IF EXISTS price_versions;
DROP TABLE IF EXISTS estimate_revisions;
DROP TABLE IF EXISTS estimate_lines;
DROP TABLE IF EXISTS finance_resources;
DROP TABLE IF EXISTS finance_project_settings;

DROP FUNCTION IF EXISTS finance_guard_confirmed_invoice();
DROP FUNCTION IF EXISTS finance_guard_estimate_original();
DROP FUNCTION IF EXISTS finance_reject_mutation();
"""


def upgrade() -> None:
    op.execute(DDL(UPGRADE_SQL))


def downgrade() -> None:
    op.execute(DDL(DOWNGRADE_SQL))
