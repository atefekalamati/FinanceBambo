# -*- coding: utf-8 -*-
"""Whether a market price belongs to one project or to the whole company.

A daily sheet price is a fact about the market: the price of rebar on a Tuesday does not
change because a different project is asking. It was nonetheless stored per project,
because every table on that path is keyed `(organization_id, project_id, ...)` with
`project_id` NOT NULL inside seven composite foreign keys -- so one Google Sheet became six
imports across six projects and 14,258 duplicate rows.

`scope_level` names the distinction that was previously only implied:

    project        this price was collected for one project and is visible to it alone
    organization   this price is the company's and every project of that company may use it

WHY NOT A NULL PROJECT

Because it would switch the foreign keys off. Under MATCH SIMPLE -- Postgres's default --
a composite foreign key with ANY null column is not enforced at all. A null `project_id`
would leave exactly the rows this feature introduces as the only ones nothing checks.

So an organization-scoped row carries a real `project_id` that no project has. It needs no
row in any table: nothing in Finance references `projects` (zero foreign keys, verified),
and `project_id` is free-form text. It is an identity inside the finance tables and nowhere
else.

`sample_site_01` was deliberately not reused for this. It is seed data, not a formally
defined organization scope, and borrowing it would make demo rows indistinguishable from
the company's real prices.
"""

#: The `project_id` an organization-scoped row carries. Deliberately not a name a project
#: could plausibly have: no real project id begins and ends with a double underscore. Also
#: readable rather than a uuid, so that if `scope_level` is ever dropped these rows can
#: still be told apart by eye.
ORGANIZATION_SENTINEL_PROJECT = "__org_price_scope__"

SCOPE_PROJECT = "project"
SCOPE_ORGANIZATION = "organization"
SCOPE_LEVELS = (SCOPE_PROJECT, SCOPE_ORGANIZATION)


def storage_project_id(scope_level, project_id):
    """Which `project_id` a row of this scope is stored under.

    One place decides it, so an importer and a reader cannot disagree about where an
    organization row lives -- a disagreement that would not fail, it would just quietly
    write rows nobody reads.
    """
    if scope_level == SCOPE_ORGANIZATION:
        return ORGANIZATION_SENTINEL_PROJECT
    return project_id


def is_organization_scope(project_id):
    """Whether a stored `project_id` is the sentinel rather than a real project."""
    return project_id == ORGANIZATION_SENTINEL_PROJECT


#: SQL that matches rows this project may READ: its own, plus the company's.
#:
#: Ordered by the caller, not here -- `scope_level='project'` first, so a price collected
#: for this project beats the company's general one. That ordering is the whole precedence
#: rule and it belongs beside the other rungs in `price_resolution.py`, not buried here.
def readable_scope_clause(alias, project="%s"):
    """`(alias.project_id = <project> OR alias.scope_level = 'organization')`.

    The organization half needs no organization check of its own: every query using this
    is already filtered by `organization_id`, and adding a second one here would read as
    though it were load-bearing when the real guarantee is upstream.
    """
    return ("({a}.project_id = {project} OR {a}.scope_level = '{organization}')"
            .format(a=alias, project=project, organization=SCOPE_ORGANIZATION))


#: How a row's scope becomes the `priceSource` a reader sees. The coarse source stays
#: `sheet`, because a page showing a market price does not become a different page when
#: the price was collected for the company rather than for the project -- the distinction
#: goes in `priceScope` beside it, which is additive and breaks no existing consumer.
def price_scope_of(project_id):
    return SCOPE_ORGANIZATION if is_organization_scope(project_id) else SCOPE_PROJECT
