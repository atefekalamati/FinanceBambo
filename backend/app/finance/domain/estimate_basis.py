# -*- coding: utf-8 -*-
"""The original quantity and unit rate a line reports, when the line itself has none.

`estimate_lines.original_quantity` and `original_unit_price_irr` are immutable by trigger,
and rightly: they record what was estimated at the beginning, and an estimate that can be
rewritten records nothing. Lines mapped from a schedule before the mapper read the file's
Material field and standard rate were created with both columns NULL, and those values were
in the file the whole time.

`estimate_line_source_completions` holds them beside the line — one row per line, naming the
source version and its sha256, the assignment, and when the values were written down. This
module is the one place that says how the two are combined:

    the line's own column when it has one, the completion otherwise, and NULL when neither.

WHY IT IS A SUBQUERY AND NOT A JOIN
The two callers — the items listing and the report's `load` — are single large statements
that already join resources, revisions, prices and invoices. A correlated subquery drops
into an expression slot in both without touching their FROM clauses, so neither query can
change shape, lose a row, or start double-counting one because a join fanned out.

WHAT THIS IS NOT
It is not a revision. `estimate_revisions` says the estimate CHANGED and moves the latest
quantity; a completion says the estimate was always this and was written down late, and it
moves only what the original columns would have said. A line that already carries an
original is untouched by all of this: the completion table is only ever written where the
column is NULL, and the COALESCE below prefers the column regardless.

It is not a price of the day either. The rate here is the ESTIMATE's basis, from the
schedule the estimate was mapped from; `price_versions` still answers "what does this cost
today", and a line with no price version still reports no current price.
"""

#: The effective original quantity for an alias of `estimate_lines`.
EFFECTIVE_ORIGINAL_QUANTITY = """COALESCE({l}.original_quantity,
    (SELECT c.quantity FROM estimate_line_source_completions c
      WHERE c.organization_id = {l}.organization_id
        AND c.project_id = {l}.project_id
        AND c.estimate_line_id = {l}.id))"""

#: The effective original unit rate, in rials, for an alias of `estimate_lines`.
EFFECTIVE_ORIGINAL_PRICE = """COALESCE({l}.original_unit_price_irr,
    (SELECT c.unit_price_irr FROM estimate_line_source_completions c
      WHERE c.organization_id = {l}.organization_id
        AND c.project_id = {l}.project_id
        AND c.estimate_line_id = {l}.id))"""

#: Where the effective original came from, so a reader is never left guessing.
#:
#: `recorded` — the line's own columns, written when it was created.
#: `source_completion` — the source version named in the completion row.
#: NULL — nothing states an original, and the line reports itself as unmeasured.
ORIGINAL_VALUE_SOURCE = """CASE
    WHEN {l}.original_quantity IS NOT NULL OR {l}.original_unit_price_irr IS NOT NULL
        THEN 'recorded'
    WHEN EXISTS (SELECT 1 FROM estimate_line_source_completions c
                  WHERE c.organization_id = {l}.organization_id
                    AND c.project_id = {l}.project_id
                    AND c.estimate_line_id = {l}.id)
        THEN 'source_completion'
    ELSE NULL END"""


def effective_original_quantity(alias="l"):
    """The effective original quantity expression for a given table alias."""
    return EFFECTIVE_ORIGINAL_QUANTITY.format(l=alias)


def effective_original_price(alias="l"):
    """The effective original unit rate expression for a given table alias."""
    return EFFECTIVE_ORIGINAL_PRICE.format(l=alias)


def original_value_source(alias="l"):
    """The provenance expression for a given table alias."""
    return ORIGINAL_VALUE_SOURCE.format(l=alias)
