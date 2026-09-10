# -*- coding: utf-8 -*-
"""Which schedule a project is running on, decided in one place.

Four services needed the answer and each carried its own copy of it: the items repository
(four times inside one statement), the activity catalogue, the mapping service and the
rows-backed progress provider. The copies agreed, which is the dangerous kind of
duplication -- they would go on agreeing until one of them was edited, and then a page
would price an estimate from one file while the chart beside it read progress from
another, with nothing in either answer saying so.

THE RULE

The project's own ready source version, most recently imported. Scope is part of the rule
and not an afterthought: a version belonging to another project or another organisation is
never the answer, whatever its date, and a project with nothing imported has no active
version rather than somebody else's.

`status = 'ready'` is what keeps a half-finished import out. A version is written before
its rows are, so a reader that took the newest row regardless of status would show a
schedule that is still being read.

WHAT THIS IS NOT

It is not a way to ASK for a particular version. A caller that has an explicit version --
a report pinned to one, a baseline comparison, a snapshot being replayed -- names it, and
naming it must still be scoped to the project. `finance_progress._BY_ID` is that path, and
it deliberately carries no ordering: an explicit choice is not a competition between dates.
"""

#: The table the answer lives in. Named once so a rename is one edit.
SOURCE_VERSION_TABLE = "finance_mpp_source_versions"


def active_source_version(columns="id",
                          organization="%(organization_id)s",
                          project="%(project_id)s"):
    """The statement that resolves a project's active source version.

    `columns` is what the caller needs back -- an id for a scoping subquery, the whole row
    for a provider building a feed header. `organization` and `project` are how the caller
    supplies the scope: a placeholder in its own paramstyle, or a column reference when
    this is a correlated subquery inside a larger statement.
    """
    return ("SELECT %s FROM %s"
            " WHERE organization_id = %s AND project_id = %s AND status = 'ready'"
            " ORDER BY imported_at DESC, id DESC LIMIT 1"
            % (columns, SOURCE_VERSION_TABLE, organization, project))


def active_source_version_for(alias):
    """The id of the active version, as a correlated subquery beside `alias`.

    For a statement that already joins the tenant's own rows: the scope comes from the
    columns it is standing next to, so the subquery cannot be scoped to a different
    project than the row it qualifies.
    """
    return "(%s)" % active_source_version(organization="%s.organization_id" % alias,
                                          project="%s.project_id" % alias)
