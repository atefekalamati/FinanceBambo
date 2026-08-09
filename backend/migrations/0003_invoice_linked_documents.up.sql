BEGIN;

CREATE UNIQUE INDEX IF NOT EXISTS ux_invoices_one_reversal_per_original
    ON invoices (organization_id, project_id, original_invoice_id)
    WHERE source = 'reversal';

COMMIT;
