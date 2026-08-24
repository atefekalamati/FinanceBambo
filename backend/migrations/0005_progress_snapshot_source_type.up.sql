BEGIN;

-- Where a progress snapshot came from, so nothing has to infer it from a filename.
-- Deliberately nullable with no backfill: the rows already in this table were imported
-- before the column existed and their real source is not recorded anywhere. NULL says
-- "not recorded", which is true; 'other' would say "recorded as something outside the
-- known list", which is a claim nobody can support. A blank source in the UI is better
-- than a confident wrong one -- inferring "Microsoft Project" from a .mpp filename is the
-- guess this column exists to remove.
--
-- ADD COLUMN with no DEFAULT is a catalog-only change in PostgreSQL 11+: no row is
-- rewritten, so the progress_snapshot_refs_immutable trigger (BEFORE UPDATE OR DELETE,
-- FOR EACH ROW) never fires. A backfilling UPDATE would have been rejected by it.
ALTER TABLE progress_snapshot_refs
    ADD COLUMN IF NOT EXISTS source_type text;

-- ADD CONSTRAINT has no IF NOT EXISTS, so the guard is explicit to keep the migration
-- re-runnable like the others in this directory.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'progress_snapshot_refs_source_type_check'
    ) THEN
        ALTER TABLE progress_snapshot_refs
            ADD CONSTRAINT progress_snapshot_refs_source_type_check
            CHECK (source_type IS NULL
                   OR source_type IN ('microsoft_project', 'primavera', 'manual', 'other'));
    END IF;
END $$;

COMMIT;
