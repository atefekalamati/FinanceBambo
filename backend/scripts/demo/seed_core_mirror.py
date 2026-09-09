# -*- coding: utf-8 -*-
"""Fill the local Core mirror with demo rows. LOCAL DEMO DATABASE ONLY.

EVERY ROW HERE IS SYNTHETIC
Nothing in this file was copied from the production Core database. The organization, the
people, the project and the schedule are invented for the demo, and each mirror table
carries a `DEMO_LOCAL_ONLY` comment so that anyone opening it in DBeaver is told so by the
database itself rather than having to take a document's word for it.

Two kinds of value are deliberately absent: nothing here contains a credential, and the
`users` rows carry no email or phone. A demo does not need contactable people, and a table
full of plausible-looking personal data is the kind of thing that gets copied somewhere it
should not be.

ALIGNMENT IS BUILT, NOT MAINTAINED
The organization id, project id, area, actors, snapshot ids, file ids, task names and
progress percentages are all read from `devhost.seed`, which is itself mirrored from the
frontend's mock adapters. So the browser, the API, the Finance tables and the Core mirror
show one project because they are computed from one definition -- not because three files
were edited to agree, which is a thing that stops being true the first time someone forgets.

WHAT THE DEMO IS SET UP TO SHOW
Four situations that are hard to explain in the abstract and obvious once seen:

  * `finance_report.issue` is missing from `permissions`, exactly as it is missing from the
    real Core. Issuing a report is refused, and the refusal is the point.
  * One user holds a role granting `finance.edit` and a personal override denying it. Deny
    wins.
  * A second organization with its own project and its own `org_chief` proves a role in one
    organization grants nothing in another.
  * `msp_snapshots` 9001/9002/9003 carry the ids that `progress_snapshot_refs.host_snapshot_id`
    points at, so the logical Core-to-Finance link can be read off two tables side by side.
"""

import sys
from datetime import date
from pathlib import Path
from uuid import UUID

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from psycopg import sql                                                # noqa: E402

from app.finance.domain.persian_calendar import gregorian_to_persian   # noqa: E402
from devhost import seed                                              # noqa: E402

#: The people. Two already exist in `devhost.seed`; the rest are added here for the
#: situations the demo needs to show.
FINANCE_EXPERT = seed.ACTOR_ID                                    # holds org_chief
SITE_SUPERVISOR = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2")    # authored the override
PLANNER = seed.IMPORTER_ID                                        # uploaded the schedules
DENIED_EDITOR = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa4")      # role grants, override denies
OUTSIDER = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa9")           # org_chief somewhere else

#: A second tenant, so cross-organization isolation is demonstrable rather than asserted.
OTHER_ORGANIZATION = UUID("22222222-2222-4222-8222-222222222222")
OTHER_PROJECT = "other_site_99"

#: A second project inside the *same* organization that nobody in the fixture belongs to.
#: Without it, "cross-project denial" can only be tested across organizations -- and the
#: organization gate would refuse first, so the project gate would never be the thing doing
#: the refusing and a fault in it would pass unnoticed.
SIBLING_PROJECT = "annex_site_02"

#: Core permits exactly these three. All of them appear so the progress adapter's exclusion
#: of TARGET is exercised rather than assumed: a baseline states the plan, not what
#: happened, and reading one as progress would report planned work as done.
SNAPSHOT_TYPES = ("TARGET", "ACTUAL", "RESCHEDULED")

#: Finance's whole permission vocabulary. Two of these the host has NOT registered --
#: `finance.manage_invoice` and `finance_report.issue` -- and they appear here anyway,
#: because a local mirror that quietly omitted them would make the routes needing them look
#: broken instead of look blocked. Which is exactly the distinction the demo has to show.
PERMISSIONS = (
    ("finance", "view", "finance.view", "مشاهده مالی", "مالی"),
    ("finance", "edit", "finance.edit", "ویرایش مالی", "مالی"),
    ("finance", "manage_invoice", "finance.manage_invoice", "مدیریت فاکتورها", "مالی"),
    ("finance_report", "view", "finance_report.view", "مشاهده گزارش مالی", "مالی"),
    ("finance_report", "export", "finance_report.export", "خروجی گزارش مالی", "مالی"),
    ("finance_report", "issue", "finance_report.issue", "صدور گزارش مالی", "مالی"),
)

#: PROVENANCE: this list of role codes was SUPPLIED to us as the host's roles. It was not
#: read from a live Core database by anything in this repository, and nothing here should be
#: read as confirming it. The Persian labels and the category column are local placeholders
#: chosen so the mirror's tables are populated; they are not host evidence either.
HOST_ROLES = (
    ("org_chief", "رئیس سازمان", "customer"),
    ("project_manager", "مدیر پروژه", "customer"),
    ("site_supervisor", "سرپرست کارگاه", "customer"),
    ("technical_expert", "کارشناس فنی", "customer"),
    ("guest", "مهمان", "customer"),
    ("bambo_admin", "مدیر بامبو", "internal"),
    ("project_definition_expert", "کارشناس تعریف پروژه", "customer"),
    ("project_control_expert", "کارشناس کنترل پروژه", "customer"),
    ("capture_expert", "کارشناس برداشت", "customer"),
    ("quantity_survey_expert", "کارشناس متره", "customer"),
    ("finance_expert", "کارشناس مالی", "customer"),
    ("support", "پشتیبانی", "internal"),
)

#: The ONLY host role whose finance permissions were supplied to us. Every other host role
#: above is deliberately absent from this mapping rather than guessed at: an unmapped role
#: grants nothing here, which is also what it does in Finance until Core says otherwise.
#:
#: `finance.manage_invoice` is NOT here, and adding the code to the vocabulary above did not
#: put it here. An administrator-sounding name is not evidence of a grant, and inventing one
#: would make the local demo disagree with the deployment it is supposed to describe.
HOST_ROLE_PERMISSIONS = {
    "bambo_admin": ("finance.view", "finance.edit",
                    "finance_report.view", "finance_report.export"),
}

#: Host roles we hold no finance permission evidence for. Named rather than left implicit,
#: so "we were not told" cannot be mistaken for "they have none".
UNMAPPED_HOST_ROLES = tuple(code for code, _label, _category in HOST_ROLES
                            if code not in HOST_ROLE_PERMISSIONS)

#: Synthetic roles this demo needs and the host does not have. The `demo_` prefix is the
#: point: a reader looking at the mirror's tables can tell at a glance which rows describe
#: the host and which exist to make a local scenario runnable.
DEMO_ROLES = (
    ("demo_finance_editor", "ویرایشگر مالی (فقط دمو)", "customer"),
    ("demo_finance_viewer", "بیننده مالی (فقط دمو)", "customer"),
)

DEMO_ROLE_PERMISSIONS = {
    "demo_finance_editor": ("finance.view", "finance.edit",
                            "finance_report.view", "finance_report.export"),
    "demo_finance_viewer": ("finance.view",),
}

ROLES = HOST_ROLES + DEMO_ROLES
ROLE_PERMISSIONS = {**HOST_ROLE_PERMISSIONS, **DEMO_ROLE_PERMISSIONS}

USERS = (
    (FINANCE_EXPERT, "کارشناس مالی نمونه"),
    (SITE_SUPERVISOR, "سرپرست کارگاه نمونه"),
    (PLANNER, "برنامه‌ریز نمونه"),
    (DENIED_EDITOR, "کاربر با محدودیت نمونه"),
    (OUTSIDER, "کاربر سازمان دیگر نمونه"),
)

#: `user_roles` rows: (user, role code, organization, project). A NULL project means the
#: role applies across the organization.
#:
#: `FINANCE_EXPERT` holds TWO roles on purpose: `org_chief`, a host role this mirror grants
#: no finance permission to, and `demo_finance_editor`, which carries the permissions. What
#: they can do therefore comes entirely from the assignment and not at all from the title --
#: which is now true in the application as well. It was not: `settings_edit_permission` used
#: to ask an `org_chief` for `finance.view` instead of `finance.edit`, so a chief edited the
#: gross built area holding read-only permission and denying them `finance.edit` changed
#: nothing. That rule is gone; this pairing is what would catch it coming back.
#:
#: `SITE_SUPERVISOR` holds only an unmapped host role, so they can read nothing. That is the
#: state every host role except `bambo_admin` is in until Core tells us otherwise, and the
#: demo shows it rather than papering over it with a guess.
#:
#: `DENIED_EDITOR` holds `demo_finance_editor` plus a personal denial of `finance.edit`:
#: the deny has to beat the grant.
USER_ROLES = (
    (FINANCE_EXPERT, "org_chief", None),
    (FINANCE_EXPERT, "demo_finance_editor", None),
    (SITE_SUPERVISOR, "site_supervisor", None),
    (PLANNER, "demo_finance_viewer", None),
    (DENIED_EDITOR, "demo_finance_editor", None),
)

MIRROR_TABLES = (
    "msp_tasks", "msp_snapshots", "msp_file_versions", "media_files",
    "user_permission_overrides", "user_roles", "role_permissions",
    "project_memberships", "organization_memberships",
    "permissions", "roles", "projects", "users", "organizations",
)

TABLE_NOTE = (
    "DEMO_LOCAL_ONLY - local mirror of the BAMBO Core table of the same name. "
    "Schema copied from the real Core schema; every row is synthetic demo data and none "
    "of it came from production."
)


def jalali(value: date) -> str:
    year, month, day = gregorian_to_persian(value)
    return f"{year:04d}-{month:02d}-{day:02d}"


def _tasks_for(snapshot) -> list[dict]:
    """The distinct tasks referenced by a snapshot's assignment rows, in a stable order.

    Derived from the assignments rather than listed separately, so a snapshot's task set and
    its progress feed cannot describe different schedules.
    """
    seen, tasks = set(), []
    for assignment in snapshot["assignments"]:
        task = assignment["task"]
        if task["taskExternalId"] in seen:
            continue
        seen.add(task["taskExternalId"])
        tasks.append(task)
    return tasks


def statements():
    """Every INSERT the mirror needs, as `(sql, parameters)` pairs, in dependency order."""
    plan: list[tuple[str, dict | tuple]] = []

    plan.append(("""
        INSERT INTO organizations (id, name, code, org_type, status, country)
        VALUES (%s, %s, %s, %s, 'active', 'ایران'), (%s, %s, %s, %s, 'active', 'ایران')
    """, (str(seed.ORGANIZATION_ID), "گروه ساختمانی بامبو", "BAMBO-DEMO", "contractor",
          str(OTHER_ORGANIZATION), "سازمان دیگر نمونه", "OTHER-DEMO", "contractor")))

    for user_id, display_name in USERS:
        # email and phone are left NULL on purpose -- see the module docstring.
        plan.append(("INSERT INTO users (id, display_name, is_active) VALUES (%s, %s, true)",
                     (str(user_id), display_name)))

    plan.append(("""
        INSERT INTO projects (id, organization_id, name, code, status, built_area_sqm,
                              start_date, created_by)
        VALUES (%s, %s, %s, %s, 'active', %s, %s, %s)
    """, (seed.PROJECT_ID, str(seed.ORGANIZATION_ID), "پروژه مسکونی نمونه", "BMB-1405-01",
          seed.GROSS_BUILT_AREA, date(2026, 6, 1), str(FINANCE_EXPERT))))
    plan.append(("""
        INSERT INTO projects (id, organization_id, name, code, status, created_by)
        VALUES (%s, %s, %s, %s, 'active', %s)
    """, (OTHER_PROJECT, str(OTHER_ORGANIZATION), "پروژه سازمان دیگر نمونه", "OTH-1405-99",
          str(OUTSIDER))))
    plan.append(("""
        INSERT INTO projects (id, organization_id, name, code, status, created_by)
        VALUES (%s, %s, %s, %s, 'active', %s)
    """, (SIBLING_PROJECT, str(seed.ORGANIZATION_ID), "پروژه الحاقی نمونه",
          "BMB-1405-02", str(FINANCE_EXPERT))))

    for code, name, category in ROLES:
        plan.append(("""
            INSERT INTO roles (name, code, category, is_system, is_active)
            VALUES (%s, %s, %s, true, true)
        """, (name, code, category)))

    for module_key, action_key, code, label, group_name in PERMISSIONS:
        plan.append(("""
            INSERT INTO permissions (module_key, action_key, code, label, group_name)
            VALUES (%s, %s, %s, %s, %s)
        """, (module_key, action_key, code, label, group_name)))

    for role_code, permission_codes in ROLE_PERMISSIONS.items():
        plan.append(("""
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT role.id, permission.id
            FROM roles AS role, permissions AS permission
            WHERE role.code = %s AND permission.code = ANY(%s)
        """, (role_code, list(permission_codes))))

    for user_id, role_code, project_id in USER_ROLES:
        plan.append(("""
            INSERT INTO user_roles (user_id, role_id, organization_id, project_id)
            SELECT %s, role.id, %s, %s FROM roles AS role WHERE role.code = %s
        """, (str(user_id), str(seed.ORGANIZATION_ID), project_id, role_code)))
    plan.append(("""
        INSERT INTO user_roles (user_id, role_id, organization_id, project_id)
        SELECT %s, role.id, %s, NULL FROM roles AS role WHERE role.code = 'org_chief'
    """, (str(OUTSIDER), str(OTHER_ORGANIZATION))))

    # The deny that beats a role grant.
    plan.append(("""
        INSERT INTO user_permission_overrides (user_id, permission_id, allowed)
        SELECT %s, permission.id, false FROM permissions AS permission
        WHERE permission.code = 'finance.edit'
    """, (str(DENIED_EDITOR),)))

    for user_id, organization_role in ((FINANCE_EXPERT, "org_admin"),
                                       (SITE_SUPERVISOR, "editor"),
                                       (PLANNER, "editor"),
                                       (DENIED_EDITOR, "editor")):
        plan.append(("""
            INSERT INTO organization_memberships (organization_id, user_id, role)
            VALUES (%s, %s, %s)
        """, (str(seed.ORGANIZATION_ID), str(user_id), organization_role)))
    plan.append(("""
        INSERT INTO organization_memberships (organization_id, user_id, role)
        VALUES (%s, %s, 'org_admin')
    """, (str(OTHER_ORGANIZATION), str(OUTSIDER))))

    for user_id, project_role in ((FINANCE_EXPERT, "project_admin"),
                                  (SITE_SUPERVISOR, "editor"),
                                  (PLANNER, "editor"),
                                  (DENIED_EDITOR, "editor")):
        plan.append(("""
            INSERT INTO project_memberships (project_id, user_id, role)
            VALUES (%s, %s, %s)
        """, (seed.PROJECT_ID, str(user_id), project_role)))
    plan.append(("""
        INSERT INTO project_memberships (project_id, user_id, role)
        VALUES (%s, %s, 'project_admin')
    """, (OTHER_PROJECT, str(OUTSIDER))))

    # One type per snapshot, positionally. Said out loud so that adding a fourth snapshot to
    # the fixture fails here with a reason rather than an IndexError three frames down.
    if len(seed.PROGRESS_SNAPSHOTS) != len(SNAPSHOT_TYPES):
        raise ValueError(f"the fixture has {len(seed.PROGRESS_SNAPSHOTS)} progress snapshots "
                         f"but SNAPSHOT_TYPES names {len(SNAPSHOT_TYPES)}; decide which type "
                         "the new snapshot carries before mirroring it")
    previous = None
    for index, snapshot in enumerate(seed.PROGRESS_SNAPSHOTS):
        tasks = _tasks_for(snapshot)
        plan.append(("""
            INSERT INTO msp_file_versions (id, project_id, version_number, original_filename,
                                           stored_rel_path, file_type, detected_role,
                                           upload_role, size_bytes, sha256,
                                           uploaded_by, uploaded_at)
            VALUES (%s, %s, %s, %s, %s, 'MPP', 'ACTUAL', 'ACTUAL', %s, %s, %s, %s)
        """, (snapshot["host_file_version_id"], seed.PROJECT_ID,
              snapshot["host_file_version_id"] - 1000, snapshot["source_file_name_safe"],
              f'demo/{seed.PROJECT_ID}/{snapshot["source_file_name_safe"]}',
              # size_bytes has a > 0 CHECK, so the demo cannot claim an empty file. There
              # is no file at all; this is a placeholder that satisfies the constraint
              # without pretending to a plausible size.
              1,
              # A placeholder digest of the right shape -- the column has a 64-hex-digit
              # CHECK. There is nothing to hash, and a realistic-looking digest would
              # suggest there is.
              f'{"0" * 56}{snapshot["host_file_version_id"]:08d}',
              str(PLANNER), snapshot["imported_at"])))
        plan.append(("""
            INSERT INTO msp_snapshots (id, project_id, file_version_id, snapshot_type,
                                       previous_snapshot_id, source_filename,
                                       source_version_number, display_label, task_count,
                                       parser_engine, status_date_jalali, created_by,
                                       created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'demo-fixture', %s, %s, %s, %s)
        """, (snapshot["host_snapshot_id"], seed.PROJECT_ID, snapshot["host_file_version_id"],
              SNAPSHOT_TYPES[index],
              previous, snapshot["source_file_name_safe"],
              snapshot["host_file_version_id"] - 1000,
              f'وضعیت {jalali(snapshot["reporting_date"])}', len(tasks),
              jalali(snapshot["reporting_date"]),
              str(PLANNER), snapshot["imported_at"], snapshot["imported_at"])))
        previous = snapshot["host_snapshot_id"]

        for index, task in enumerate(tasks, start=1):
            plan.append(("""
                INSERT INTO msp_tasks (snapshot_id, uid, guid, task_id, name, wbs,
                                       outline_number, outline_level, start, finish,
                                       percent_complete, text1)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (snapshot["host_snapshot_id"], index, task["taskExternalId"], index,
                  task["taskName"], task["wbsCode"], task["wbsCode"],
                  (task["wbsCode"] or "").count(".") + 1,
                  task["taskStart"], task["taskFinish"],
                  task["taskProgressPercent"], task["activityCode"])))
    return plan


async def apply(connection) -> dict:
    """Clear the mirror and rewrite it. The caller must already have proved the target.

    Only the mirror tables are touched. Finance tables are never named here, and could not
    be emptied this way in any case -- their immutability triggers refuse DELETE.
    """
    async with connection.cursor() as cursor:
        await cursor.execute("TRUNCATE %s RESTART IDENTITY CASCADE"
                             % ", ".join(MIRROR_TABLES))
        for table in MIRROR_TABLES:
            # COMMENT takes no parameters, so the text is composed as a literal rather than
            # bound. `sql.Literal` does the quoting; formatting it into the string by hand
            # is how a comment ends up ending a statement early.
            await cursor.execute(sql.SQL("COMMENT ON TABLE {} IS {}").format(
                sql.Identifier(table), sql.Literal(TABLE_NOTE)))
        for statement, parameters in statements():
            await cursor.execute(statement, parameters)

        counts = {}
        for table in MIRROR_TABLES:
            # Named, because the caller's connection may use dict_row and a positional
            # index would then be a key that does not exist.
            await cursor.execute(
                sql.SQL("SELECT count(*) AS rows FROM {}").format(sql.Identifier(table)))
            row = await cursor.fetchone()
            counts[table] = row["rows"] if isinstance(row, dict) else row[0]
    return counts
