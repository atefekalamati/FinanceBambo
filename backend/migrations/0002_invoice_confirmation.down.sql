BEGIN;

DROP INDEX IF EXISTS ux_invoices_confirmation_idempotency_scope;
ALTER TABLE invoices DROP COLUMN IF EXISTS confirmation_idempotency_key;

COMMIT;
