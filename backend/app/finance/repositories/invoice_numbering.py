"""Where an invoice's number comes from.

One function, used by both transactions that write an invoice: the ordinary create path in
`repositories/invoices.py` and the extraction confirmation in `repositories/extractions.py`.
Two copies of this statement would be two places for the rule to drift.
"""

#: `INSERT ... ON CONFLICT DO UPDATE ... RETURNING` in one statement, because the point is
#: the row lock it takes. A concurrent creator in the same project blocks here until this
#: transaction commits or rolls back, and is then handed the next number -- no read, no
#: gap, and no two callers holding the same answer.
#:
#: A project that has never had an invoice inserts `next_number = 2` and is handed 1: the
#: row records what the NEXT invoice gets, and `next_number - 1` is what this one gets.
ALLOCATE_SQL = ("INSERT INTO finance_invoice_counters(organization_id,project_id,next_number)"
                " VALUES(%s,%s,2)"
                " ON CONFLICT (organization_id,project_id)"
                " DO UPDATE SET next_number=finance_invoice_counters.next_number+1"
                " RETURNING next_number-1 AS allocated")


class InvoiceNumberConflict(RuntimeError):
    """The unique constraint refused a number the counter handed out.

    This is never a caller's mistake and it is not an idempotency conflict, which is why
    it is its own type: something wrote an invoice_seq without passing through the counter,
    and the honest answer is a failure rather than a 409 that tells the caller to retry
    something that would fail again.
    """


async def allocate_invoice_number(cursor, organization_id, project_id):
    """The next invoice number for this project. Must run inside the writing transaction."""
    await cursor.execute(ALLOCATE_SQL, (organization_id, project_id))
    return (await cursor.fetchone())["allocated"]
