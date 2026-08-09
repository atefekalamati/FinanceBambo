BEGIN;

ALTER TABLE report_snapshots
    ADD COLUMN IF NOT EXISTS snapshot_payload jsonb,
    ADD COLUMN IF NOT EXISTS resource_version_ids jsonb;

UPDATE report_snapshots
SET snapshot_payload = jsonb_build_object(
    'reportingDate', reporting_date,
    'calculatedMetrics', calculated_metrics
)
WHERE snapshot_payload IS NULL;

UPDATE report_snapshots
SET resource_version_ids = '[]'::jsonb
WHERE resource_version_ids IS NULL;

ALTER TABLE report_snapshots
    ALTER COLUMN snapshot_payload SET NOT NULL,
    ALTER COLUMN resource_version_ids SET NOT NULL;

COMMIT;
