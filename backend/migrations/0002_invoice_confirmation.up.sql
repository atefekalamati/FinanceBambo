BEGIN;

ALTER TABLE invoices
    ADD COLUMN IF NOT EXISTS confirmation_idempotency_key text;

CREATE UNIQUE INDEX IF NOT EXISTS ux_invoices_confirmation_idempotency_scope
    ON invoices (organization_id, project_id, confirmation_idempotency_key)
    WHERE confirmation_idempotency_key IS NOT NULL;

COMMIT;
