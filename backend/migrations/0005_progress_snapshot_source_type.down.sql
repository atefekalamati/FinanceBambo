BEGIN;

-- Drops only what the up migration added. No stored financial fact is lost: every row's
-- source_type is NULL unless a later import set it, and no calculation reads this column.
ALTER TABLE progress_snapshot_refs DROP CONSTRAINT IF EXISTS progress_snapshot_refs_source_type_check;
ALTER TABLE progress_snapshot_refs DROP COLUMN IF EXISTS source_type;

COMMIT;
