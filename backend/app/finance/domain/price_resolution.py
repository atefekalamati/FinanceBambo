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
    3. the linked listing's newest VALID observation, PROJECT-scoped
    4. the same, ORGANIZATION-scoped                the company's daily market reading
    5. nothing

THE LATEST DECISION WINS -- decided 2026-09-27

Rungs 1-2 and rungs 3-4 are two DECISIONS a person can make about the same item: type a
rate, or link the item to a market listing. They used to be ranked -- a typed rate beat a
link, always -- and since price versions are append-only, an item once typed could never
be handed back to the sheet. The project owner ruled otherwise: «همیشه آخرین قیمتی که
برای یک محصول ست می‌شود باید ارجحیت داشته باشد». So the two decisions are compared by
WHEN they were made: the newer one prices the item, and typing a rate after a link, or
linking after a rate, flips it again. The tie-break, when the newer decision cannot
answer -- a link whose listing has no valid price yet -- is the other one, not nothing:
a person who linked an unpriced listing did not mean to unprice the item.

Within each decision the old ranking stands: project before organization, newest date
first.

WHERE A LINK IS RECORDED

In two tables, and the resolver reads both. `finance_item_price_mappings` is keyed by the
schedule assignment; `finance_item_price_mapping_components` is keyed by the estimate
line and is what «اتصال به قیمت روز» on the items page writes. The report resolved only
the first, so a link made on the items page never reached the report (measured 2026-09-27:
line «بتن ۴۰۰» on 1.8.1.7.3, linked, component recorded, report unaware). The newest
live link of either kind is the link.

Rungs 2 and 4 are the company's, and both were unreachable until 0037. An organization
price_version carried a project_id and the join demanded it match, so «organization» only
changed precedence WITHIN the project it happened to be stored against; and a sheet
observation had nowhere to live except a project, which is why one Google Sheet was
imported six times and produced 14,258 duplicate rows. The scope now says which it is, and
a price collected for this project still beats the company's general one -- specificity
wins, the same reason project beats organization above.

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


def manual_price_join(*, organization, project, resource, as_of="%s",
                      name="manual_price"):
    """Rungs 1 and 2 on their own: the newest applicable `price_versions` row.

    Split out of `resolved_price_joins` rather than written twice. The daily-prices page
    needs exactly this rung for equipment -- equipment has no worksheet, so rungs 3 and 4
    cannot answer for it -- and a second copy of the WHERE and the ORDER BY is how the two
    readers of `price_versions` would start disagreeing about which price wins. There is
    one statement of the precedence and both callers get it.

    `created_by` and `created_at` are selected because the daily-prices row publishes who
    set the rate and when it was recorded -- which is a different fact from the date it
    takes effect. The other callers ignore both; a derived table with a column nobody reads
    costs nothing.
    """
    return """
  LEFT JOIN LATERAL (
       SELECT pv.id AS price_version_id, pv.unit_price_irr, pv.scope_kind,
              pv.effective_from, pv.created_by, pv.created_at AS price_recorded_at
         FROM price_versions pv
        WHERE pv.organization_id={org}
          AND (pv.scope_kind='organization' OR pv.project_id={proj})
          AND pv.resource_id={res}
          AND pv.effective_from<={as_of}
        {order}
        LIMIT 1) {name} ON TRUE""".format(org=organization, proj=project, res=resource,
                                          as_of=as_of, order=_VERSION_ORDER, name=name)


def resolved_price_joins(alias="l", as_of="%s", *, organization=None, project=None,
                         resource=None, assignment=None, line=None):
    """LATERAL joins that resolve one price per row of `alias`.

    Produces two derived tables, `manual_price` and `sheet_price`. They are LEFT joins:
    a line with no price anywhere still comes back, with NULLs, because a line the report
    cannot price is a line the report must still COUNT. Dropping it here would make
    `totalLineCount` a count of priced lines, which is the one thing it must not be.

    `as_of` is the report cutoff, passed twice -- once per join.

    The keyword arguments override where each key is read from. A caller whose keys sit
    on ONE table leaves them out; Items and Estimates cannot, because its rows come from
    `finance_mpp_rows` while the resource is on a LEFT-joined `finance_resources` that may
    be absent. Reading `resource_id` off a row that might be NULL is how an unclassified
    assignment would silently take some other line's price. `line` is the estimate line's
    id, which the component link is keyed by.

    `sheet_price.linked_at` is WHEN the link was made, and `manual_price.price_recorded_at`
    when the rate was typed; the columns compare the two. See the module docstring.
    """
    organization = organization or "%s.organization_id" % alias
    project = project or "%s.project_id" % alias
    resource = resource or "%s.resource_id" % alias
    assignment = assignment or "%s.source_assignment_uid" % alias
    line = line or "%s.id" % alias
    return manual_price_join(organization=organization, project=project,
                             resource=resource, as_of=as_of) + """
  LEFT JOIN LATERAL (
       SELECT o.normalized_price_irr AS unit_price_irr, o.source_unit, o.scope_level,
              o.workflow_date_gregorian AS effective_from, fm.linked_at
         FROM (
              -- The newest live link, from either table that records one.
              SELECT fm.organization_id, fm.project_id, fm.provider_item_id,
                     fm.created_at AS linked_at
                FROM finance_item_price_mappings fm
               WHERE fm.organization_id={org}
                 AND fm.project_id={proj}
                 AND fm.source_assignment_uid={asg}
                 AND fm.superseded_at IS NULL
              UNION ALL
              SELECT fc.organization_id, fc.project_id, fc.provider_item_id,
                     fc.created_at
                FROM finance_item_price_mapping_components fc
               WHERE fc.organization_id={org}
                 AND fc.project_id={proj}
                 AND fc.estimate_line_id={line}
                 AND fc.superseded_at IS NULL
                 AND fc.active
               ORDER BY linked_at DESC
               LIMIT 1) fm
         JOIN price_observations o
           ON o.organization_id=fm.organization_id
          AND (o.project_id=fm.project_id OR o.scope_level='organization')
          AND o.provider_item_id=fm.provider_item_id
          AND o.validation_status='valid'
        WHERE (o.workflow_date_gregorian IS NULL OR o.workflow_date_gregorian<={as_of})
        ORDER BY (o.scope_level='project') DESC,
                 o.workflow_date_gregorian DESC NULLS LAST, o.fetched_at DESC, o.id
        LIMIT 1) sheet_price ON TRUE""".format(org=organization, proj=project, res=resource, asg=assignment,
                 line=line, as_of=as_of, order=_VERSION_ORDER)


#: What `priceSource` can hold. Three values, and the third is not an absence of a value:
#: `none` is the resolver saying it looked and found nothing, which is a different claim
#: from a field that was never populated.
SOURCE_MANUAL_RESOURCE = "manual_resource"
SOURCE_SHEET = "sheet"
SOURCE_NONE = "none"

#: Which `price_versions.scope_kind` values count as a manual resource price. Both do --
#: the ladder has already chosen between them by the time this runs, and a reader asking
#: "who set this price" is asking about a person either way, not about the scope.
MANUAL_SCOPES = ("project", "organization")

#: The columns a caller selects. Two different questions get two different answers:
#:
#:   `current_price_scope`  -- WHICH rung: project, organization, provider_sheet, or NULL.
#:                             The precise answer, for anyone auditing the precedence.
#:   `current_price_source` -- manual_resource / sheet / none. The answer a page shows,
#:                             where the distinction between a project price and an
#:                             organization price is noise: both were typed by a person.
#:
#: Both are published because collapsing them lost information that the settings screen
#: needs, and keeping only the precise one made every consumer re-derive the coarse one.
#: When the typed rate prices the item: it exists, and either the link cannot answer or
#: the rate was typed AFTER the link was made. Stated once and spliced into every CASE
#: below, so the five columns cannot disagree about which decision won.
MANUAL_WINS = """(manual_price.unit_price_irr IS NOT NULL
                  AND (sheet_price.unit_price_irr IS NULL
                       OR manual_price.price_recorded_at >= sheet_price.linked_at))"""

RESOLVED_PRICE_COLUMNS = """
       CASE WHEN {wins} THEN manual_price.unit_price_irr
            ELSE sheet_price.unit_price_irr
       END AS current_unit_price_irr,
       CASE WHEN {wins} THEN manual_price.scope_kind
            WHEN sheet_price.unit_price_irr IS NOT NULL THEN 'provider_sheet'
       END AS current_price_scope,
       CASE WHEN {wins} THEN 'manual_resource'
            WHEN sheet_price.unit_price_irr IS NOT NULL THEN 'sheet'
            ELSE 'none'
       END AS current_price_source,
       CASE WHEN {wins} THEN manual_price.effective_from
            ELSE sheet_price.effective_from
       END AS current_price_effective_from,
       CASE WHEN {wins}
                 THEN CASE WHEN manual_price.scope_kind='organization'
                           THEN 'organization' ELSE 'project' END
            WHEN sheet_price.unit_price_irr IS NOT NULL THEN sheet_price.scope_level
       END AS current_price_scope_level,
       CASE WHEN {wins} THEN manual_price.price_version_id END AS price_version_id""".format(wins=MANUAL_WINS)

#: What `current_price_scope` can hold, for anyone matching on it.
SCOPE_PROJECT = "project"
SCOPE_ORGANIZATION = "organization"
SCOPE_PROVIDER_SHEET = "provider_sheet"


def price_source_of(scope_kind):
    """The coarse source for a scope, for callers resolving a price in Python.

    Kept beside the SQL that produces the same mapping so the two cannot drift: a service
    that classified `organization` as a sheet price would disagree with the report about
    what the user is looking at, and nothing would fail.
    """
    if scope_kind in MANUAL_SCOPES:
        return SOURCE_MANUAL_RESOURCE
    if scope_kind == SCOPE_PROVIDER_SHEET:
        return SOURCE_SHEET
    return SOURCE_NONE


def resolved_price_columns(base_unit=None):
    """`RESOLVED_PRICE_COLUMNS`, plus the unit the price is quoted per.

    The two rungs are quoted per DIFFERENT units and only the caller knows one of them. A
    manual price is per `finance_resources.base_unit` -- the unit a person chose when they
    priced the thing. A sheet price is per whatever the worksheet column said, which is
    what `price_observations.source_unit` records. Publishing the amount without the unit
    invites the reader to assume they match; on this data they frequently do not, which is
    the whole reason the conversion rules exist.

    `base_unit` is a SQL expression for the resource's base unit, e.g. `"r.base_unit"`.
    Omitted, the caller gets the columns unchanged.
    """
    if base_unit is None:
        return RESOLVED_PRICE_COLUMNS
    return RESOLVED_PRICE_COLUMNS + """,
       CASE WHEN %s THEN %s
            WHEN sheet_price.unit_price_irr IS NOT NULL THEN sheet_price.source_unit
       END AS current_price_unit""" % (MANUAL_WINS, base_unit)
