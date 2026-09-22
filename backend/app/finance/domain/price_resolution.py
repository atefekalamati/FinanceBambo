# -*- coding: utf-8 -*-
"""One ladder for "what does this line cost", shared by every reader that needs it.

WHY THIS EXISTS

There were two answers to that question and they disagreed. The live report resolved a
price from `price_versions` and never looked at a sheet; Items and Estimates resolved one
from `price_observations` through the item mapping and never looked at `price_versions`.
Two pages, one project, two different numbers -- and on terrace the disagreement is total:
of 715 eligible estimate lines, the report resolves 0 and the mapping path resolves 2.

The rungs, in order. The first that answers, wins:

    1. price_versions, scope_kind='project'        a price someone set FOR THIS PROJECT
    2. price_versions, scope_kind='organization'   the company's price for that resource
    3. the mapped market listing's newest VALID observation   (the sheet)
    4. nothing

A project price outranks an organization price because it is the more specific statement,
and both outrank the sheet because a person chose them deliberately for this work while
the sheet is a market reading that happens to be attached. `scope_kind` has no 'global'
rung: the CHECK on `price_versions` permits only 'organization' and 'project', so a global
tier is not omitted here, it does not exist yet.

WHAT CALLERS GET BACK

`priceSource` says WHICH rung answered -- `project`, `organization`, `provider_sheet`, or
NULL when none did. A reader who cannot tell a deliberate project price from a market
reading cannot judge the number, and before this every caller was in that position.

WHY SQL AND NOT PYTHON

Because the alternative is one round trip per line, and because the rule was already
written in SQL three times in one query -- once each for the id, the amount, the scope and
the date, the same eight-line ORDER BY copied out four times. A rule stated four times is a
rule that will be changed three times.
"""

#: The tie-break within `price_versions`, from most specific to least. Project before
#: organization, then the newest effective date, then the newest version of that date.
_VERSION_ORDER = """ORDER BY (pv.scope_kind='project') DESC, pv.effective_from DESC,
                            pv.version DESC, pv.created_at DESC, pv.id DESC"""


def resolved_price_joins(alias="l", as_of="%s"):
    """LATERAL joins that resolve one price per row of `alias`.

    Produces two derived tables, `manual_price` and `sheet_price`. They are LEFT joins:
    a line with no price anywhere still comes back, with NULLs, because a line the report
    cannot price is a line the report must still COUNT. Dropping it here would make
    `totalLineCount` a count of priced lines, which is the one thing it must not be.

    `as_of` is the report cutoff, passed twice -- once per join.
    """
    return """
  LEFT JOIN LATERAL (
       SELECT pv.id AS price_version_id, pv.unit_price_irr, pv.scope_kind,
              pv.effective_from
         FROM price_versions pv
        WHERE pv.organization_id={a}.organization_id
          AND pv.project_id={a}.project_id
          AND pv.resource_id={a}.resource_id
          AND pv.effective_from<={as_of}
        {order}
        LIMIT 1) manual_price ON TRUE
  LEFT JOIN LATERAL (
       SELECT o.normalized_price_irr AS unit_price_irr,
              o.workflow_date_gregorian AS effective_from
         FROM finance_item_price_mappings fm
         JOIN price_observations o
           ON o.organization_id=fm.organization_id AND o.project_id=fm.project_id
          AND o.provider_item_id=fm.provider_item_id
          AND o.validation_status='valid'
        WHERE fm.organization_id={a}.organization_id
          AND fm.project_id={a}.project_id
          AND fm.source_assignment_uid={a}.source_assignment_uid
          AND fm.superseded_at IS NULL
          AND (o.workflow_date_gregorian IS NULL OR o.workflow_date_gregorian<={as_of})
        ORDER BY o.workflow_date_gregorian DESC NULLS LAST, o.fetched_at DESC, o.id
        LIMIT 1) sheet_price ON TRUE""".format(a=alias, as_of=as_of, order=_VERSION_ORDER)


#: The four columns a caller selects. `priceSource` is the rung that answered; without it
#: a NULL price and a sheet price are equally anonymous numbers.
RESOLVED_PRICE_COLUMNS = """
       COALESCE(manual_price.unit_price_irr, sheet_price.unit_price_irr)
           AS current_unit_price_irr,
       CASE WHEN manual_price.unit_price_irr IS NOT NULL THEN manual_price.scope_kind
            WHEN sheet_price.unit_price_irr IS NOT NULL THEN 'provider_sheet'
       END AS current_price_scope,
       COALESCE(manual_price.effective_from, sheet_price.effective_from)
           AS current_price_effective_from,
       manual_price.price_version_id AS price_version_id"""

#: What `current_price_scope` can hold, for anyone matching on it.
SCOPE_PROJECT = "project"
SCOPE_ORGANIZATION = "organization"
SCOPE_PROVIDER_SHEET = "provider_sheet"
