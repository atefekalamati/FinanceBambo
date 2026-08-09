BEGIN;

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

COMMIT;
