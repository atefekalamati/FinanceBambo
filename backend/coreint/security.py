"""Membership, effective permissions and roles, read from Core's own tables.

THE THREE QUESTIONS, AND WHY THEY HAVE DIFFERENT ANSWERS
Core answers three separate questions with three separate models, and conflating them is
the mistake this module exists to avoid:

  * *Is this person in this organization or project?* -- `organization_memberships` and
    `project_memberships`. Both require a real `user_id` and are unique per user per scope.
  * *What may they do?* -- `user_roles` -> `role_permissions` -> `permissions`, corrected by
    `user_permission_overrides`.
  * *What are they called here?* -- the role code behind their scoped `user_roles` row.

There is a second, older pair -- `organization_members` and `project_members` -- that looks
like the first but is not: its `user_id` is nullable, so it can describe a person who has no
account at all. That makes it a contact directory, not an authorization source, and nothing
here reads it.

FAIL CLOSED, EVERYWHERE
Every path in this module denies when it cannot prove otherwise. An absent row, an inactive
role, a permission code Core has never heard of, a malformed code -- all of them end as a
refusal rather than an error or a default. The one case worth naming: `finance_report.issue`
is absent from Core's catalogue today, so no role can grant it and issuing a report is
denied. That is correct and deliberate. It must not be mapped onto `finance_report.export`
or `finance.edit`, which are different, weaker claims.
"""

import re
from uuid import UUID

from fastapi import HTTPException
from psycopg.rows import dict_row

from app.finance.security.context import AuthContext

#: The shape `AuthContext` accepts. A Core row that does not match it is dropped rather than
#: allowed to fail the whole context: one malformed catalogue entry would otherwise turn
#: every request into a 500, and dropping a permission can only ever deny.
PERMISSION_CODE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")

#: Used when Core knows the person is a member but no role names them. `AuthContext`
#: requires a non-empty string for both, and an empty one would be a lie either way; this at
#: least says only what membership already established.
UNNAMED_ROLE = "member"

#: The organization role Finance's settings policy tests for. Verified to exist in Core's
#: `roles` table, so it is passed through unchanged -- no translation layer, because a
#: translation would be a second place for the two vocabularies to drift apart.
ORG_CHIEF = "org_chief"


class CoreMembershipDenied(HTTPException):
    def __init__(self, detail: str):
        super().__init__(403, detail)


async def _rows(connection, sql, params):
    async with connection.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(sql, params)
        return await cursor.fetchall()


class CoreScopeAuthorizer:
    """Membership gates backed by `organization_memberships` and `project_memberships`.

    The project query joins `projects` even though it already has the project id. Without
    that join a membership in project P would satisfy a request naming organization B, since
    `project_memberships` records no organization of its own -- a cross-organization leak
    through an otherwise valid row.
    """

    ORGANIZATION = """
        SELECT 1 FROM organization_memberships
        WHERE organization_id = %(organization_id)s AND user_id = %(user_id)s
    """

    PROJECT = """
        SELECT 1
        FROM project_memberships AS membership
        JOIN projects AS project ON project.id = membership.project_id
        WHERE membership.project_id = %(project_id)s
          AND membership.user_id    = %(user_id)s
          AND project.organization_id = %(organization_id)s
    """

    def __init__(self, connection):
        self._connection = connection

    async def require_organization(self, context: AuthContext, organization_id) -> None:
        if str(context.organization_id) != str(organization_id):
            # The context was issued for a different organization. Nothing about the
            # database can make that request legitimate.
            raise CoreMembershipDenied("organization membership is required")
        rows = await _rows(self._connection, self.ORGANIZATION,
                           {"organization_id": str(organization_id),
                            "user_id": str(context.user_id)})
        if not rows:
            raise CoreMembershipDenied("organization membership is required")

    async def require_project(self, context: AuthContext, organization_id, project_id) -> None:
        if str(context.organization_id) != str(organization_id):
            raise CoreMembershipDenied("project membership is required")
        rows = await _rows(self._connection, self.PROJECT,
                           {"organization_id": str(organization_id),
                            "project_id": project_id,
                            "user_id": str(context.user_id)})
        if not rows:
            raise CoreMembershipDenied("project membership is required")


class CoreRbacPermissionAuthorizer:
    """The permission gate, resolved from Core on every request.

    It re-reads Core rather than trusting `context.permission_codes`, because the two ports
    are meant to be independent gates. A context is assembled once at the start of a request
    and could be assembled by anything; this asks the database directly, so a permission
    revoked in Core stops working without waiting for a session to expire.
    """

    def __init__(self, connection):
        self._connection = connection

    async def require(self, context: AuthContext, permission_code: str) -> None:
        granted = await effective_permission_codes(
            self._connection, context.user_id, context.organization_id, context.project_id)
        if permission_code not in granted:
            raise HTTPException(403, f"permission {permission_code} is required")


#: Effective permissions for one user in one scope.
#:
#: A `user_roles` row applies when its scope contains the request's: an exact organization
#: match, or NULL meaning unscoped. The same for the project. Anything else is a role in some
#: other organization or project and must contribute nothing -- that is the cross-scope leak
#: this WHERE clause exists to prevent.
#:
#: `user_permission_overrides` has no scope of its own, so it applies to the user everywhere.
#: A denial there wins over every role grant. That order is deliberate: an override is a
#: decision someone made about this specific person, and a role is a decision about a
#: category of people, so the specific one is the later word.
EFFECTIVE_PERMISSIONS = """
    WITH granted AS (
        SELECT permission.code
        FROM user_roles AS assignment
        JOIN roles AS role
             ON role.id = assignment.role_id AND role.is_active
        JOIN role_permissions AS grant_row
             ON grant_row.role_id = assignment.role_id
        JOIN permissions AS permission
             ON permission.id = grant_row.permission_id
        WHERE assignment.user_id = %(user_id)s
          AND (assignment.organization_id IS NULL
               OR assignment.organization_id = %(organization_id)s)
          AND (assignment.project_id IS NULL
               OR assignment.project_id = %(project_id)s)
    ),
    override AS (
        SELECT permission.code, correction.allowed
        FROM user_permission_overrides AS correction
        JOIN permissions AS permission ON permission.id = correction.permission_id
        WHERE correction.user_id = %(user_id)s
    )
    SELECT code FROM (
        SELECT code FROM granted
        UNION
        SELECT code FROM override WHERE allowed
    ) AS effective
    WHERE code NOT IN (SELECT code FROM override WHERE NOT allowed)
    ORDER BY code
"""


async def effective_permission_codes(connection, user_id, organization_id, project_id):
    """Permission codes this user holds in this scope, as a frozenset.

    Codes that do not match `PERMISSION_CODE` are dropped. See the constant for why that is
    safe: the only effect of dropping one is to deny something.
    """
    rows = await _rows(connection, EFFECTIVE_PERMISSIONS,
                       {"user_id": str(user_id),
                        "organization_id": str(organization_id),
                        "project_id": project_id})
    return frozenset(row["code"] for row in rows
                     if PERMISSION_CODE.fullmatch(row["code"] or ""))


#: Role codes that apply to this user at organization level -- the scoped `user_roles` rows
#: whose project is unset. `org_chief` is sorted first so a user who holds it is named by it
#: regardless of what else they hold; the rest are alphabetical purely so the answer is
#: stable when someone holds several.
ORGANIZATION_ROLES = """
    SELECT role.code
    FROM user_roles AS assignment
    JOIN roles AS role ON role.id = assignment.role_id AND role.is_active
    WHERE assignment.user_id = %(user_id)s
      AND assignment.project_id IS NULL
      AND (assignment.organization_id IS NULL
           OR assignment.organization_id = %(organization_id)s)
    ORDER BY (role.code = 'org_chief') DESC, role.code
"""

PROJECT_ROLES = """
    SELECT role.code
    FROM user_roles AS assignment
    JOIN roles AS role ON role.id = assignment.role_id AND role.is_active
    WHERE assignment.user_id = %(user_id)s
      AND assignment.project_id = %(project_id)s
    ORDER BY role.code
"""

MEMBERSHIP_ROLES = """
    SELECT
        (SELECT role FROM organization_memberships
          WHERE organization_id = %(organization_id)s
            AND user_id = %(user_id)s) AS organization_role,
        (SELECT role FROM project_memberships
          WHERE project_id = %(project_id)s
            AND user_id = %(user_id)s) AS project_role
"""


async def scoped_roles(connection, user_id, organization_id, project_id):
    """`(organization_role, project_role)` for this user here.

    Precedence, and the reason for it:

      1. A scoped `user_roles` code. This is the RBAC role -- the same vocabulary
         `role_permissions` is written against, and the one holding `org_chief`.
      2. Failing that, the membership table's own `role` column. It is a coarser, separate
         vocabulary (`org_admin`, `editor`, `viewer`, ...), but it is a real statement about
         this person and better than inventing one.
      3. Failing that, `member`. Membership was already proven by the scope gate, so this
         says nothing that is not already true.

    Nothing here grants anything. These names are descriptive; every permission decision
    goes through `effective_permission_codes`.
    """
    parameters = {"user_id": str(user_id), "organization_id": str(organization_id),
                  "project_id": project_id}
    organization = await _rows(connection, ORGANIZATION_ROLES, parameters)
    project = await _rows(connection, PROJECT_ROLES, parameters)
    fallback = (await _rows(connection, MEMBERSHIP_ROLES, parameters))[0]
    return (
        organization[0]["code"] if organization
        else (fallback["organization_role"] or UNNAMED_ROLE),
        project[0]["code"] if project
        else (fallback["project_role"] or UNNAMED_ROLE),
    )


class CoreAuthContextAssembler:
    """Builds an `AuthContext` for an identity the host has already authenticated.

    WHERE THE BOUNDARY IS
    This is not an authentication mechanism and must not become one. Who the caller is comes
    from the BAMBO host's session; `identity(request)` is the seam where that arrives, and it
    is left abstract on purpose because Finance has no session contract with the host and
    inventing one would be guessing at somebody else's design.

    Everything downstream of identity -- membership, roles, permissions -- is read from Core
    here. So the split is: the host says *who*, Core says *what they may do*, and neither
    answer is taken from the other.
    """

    def __init__(self, connection, identity, *, locale="fa", timezone="Asia/Tehran"):
        self._connection = connection
        self._identity = identity
        self._locale, self._timezone = locale, timezone

    async def current(self, request) -> AuthContext:
        user_id, organization_id, project_id = await self._identity(request)
        return await self.assemble(user_id, organization_id, project_id)

    async def assemble(self, user_id: UUID, organization_id: UUID,
                       project_id: str) -> AuthContext:
        organization_role, project_role = await scoped_roles(
            self._connection, user_id, organization_id, project_id)
        codes = await effective_permission_codes(
            self._connection, user_id, organization_id, project_id)
        return AuthContext(
            userId=user_id,
            organizationId=organization_id,
            projectId=project_id,
            organizationRole=organization_role,
            projectRole=project_role,
            permissionCodes=sorted(codes),
            locale=self._locale,
            timezone=self._timezone,
        )
