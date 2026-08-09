BEGIN;

ALTER TABLE report_snapshots
    DROP COLUMN IF EXISTS snapshot_payload,
    DROP COLUMN IF EXISTS resource_version_ids;

COMMIT;
