# -*- coding: utf-8 -*-
"""Which financial items belong in the price management view today.

`finance_resources` is a reference entity. Invoices point at it, estimates point at it,
issued reports pin it, and the audit trail names it — so every row in it must stay
resolvable for ever, and nothing here deletes, hides or rewrites one. What this module
decides is narrower and purely operational: of those rows, which ones a person is meant to
be pricing *today*.

The three that qualify:

  * an item read from the schedule the project is running on — it has a
    `source_resource_uid`, and it is the reason the price module exists;
  * an item somebody entered themselves — it is theirs, whatever it looks like;
  * an item a local test seed invented out of a schedule TASK, but which has since been
    used in a real financial operation. Origin does not disqualify a row that the business
    is actually transacting on.

The one that does not:

  * a seed-made row with no operational relationship at all. It is history. It keeps its
    prices, its estimate lines and its identity; it simply is not something to price now.

WHY THE FINGERPRINT NEEDS ALL THREE PARTS
`code LIKE 'MSP-T%'` alone is free text a person can type. `source_resource_uid IS NULL`
alone is true of every hand-made item. `external_resource_id IS NOT NULL` alone is true of
anything ever linked to an external system. Only the coincidence of all three identifies
the seed's own handiwork — it wrote the task's uid into both the code and the external id
of a resource it derived from a task — and the rule is written to fail towards showing.

WHY THIS IS NOT A GLOBAL FILTER
It is applied by the PRICE module's own queries and nowhere else. `GET /resources` still
answers with the whole catalogue, because four other consumers need it: the price history
resolves item titles through it, the invoices page labels its lines from it, the home
page's price widget reads it, and the items page counts what it withheld from it. Filtering
the catalogue would break all four while fixing none of them properly.
"""

#: The operational test, as a SQL predicate over an alias of `finance_resources`.
#:
#: Written once and shared, so the listing, the counting and the export cannot come to
#: different answers about the same row. `{r}` is the table alias to substitute.
ACTIVE_PRICE_RESOURCE = """(
    {r}.source_resource_uid IS NOT NULL
    OR NOT ({r}.source_resource_uid IS NULL
            AND {r}.code LIKE 'MSP-T%%'
            AND {r}.external_resource_id IS NOT NULL)
    OR EXISTS (SELECT 1 FROM invoice_lines il
                WHERE il.organization_id = {r}.organization_id
                  AND il.project_id = {r}.project_id
                  AND il.resource_id = {r}.id)
)"""


def active_price_resource(alias="r"):
    """The predicate for a given table alias.

    A function rather than a constant so a caller cannot silently use it against the wrong
    alias, and so the one place that defines "operational" stays one place.
    """
    return ACTIVE_PRICE_RESOURCE.format(r=alias)
