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

#: The permission catalogue as the real Core has it today. `finance_report.issue` is absent
#: from both, and that is the whole point of mirroring it faithfully.
PERMISSIONS = (
    ("finance", "view", "finance.view", "مشاهده مالی", "مالی"),
    ("finance", "edit", "finance.edit", "ویرایش مالی", "مالی"),
    ("finance_report", "view", "finance_report.view", "مشاهده گزارش مالی", "مالی"),
    ("finance_report", "export", "finance_report.export", "خروجی گزارش مالی", "مالی"),
)

ROLES = (
    ("org_chief", "رئیس سازمان", "customer"),
    ("finance_manager", "مدیر مالی", "customer"),
    ("finance_expert", "کارشناس مالی", "customer"),
    ("viewer", "بیننده", "customer"),
    ("bambo_admin", "مدیر بامبو", "internal"),
)

ROLE_PERMISSIONS = {
    "org_chief": ("finance.view", "finance.edit", "finance_report.view", "finance_report.export"),
    # The role the override-denial demo needs: it grants finance.edit and is *not*
    # org_chief. See USER_ROLES for why that distinction decides what the demo proves.
    "finance_manager": ("finance.view", "finance.edit", "finance_report.view"),
    "finance_expert": ("finance.view", "finance_report.view"),
    "viewer": ("finance.view",),
    "bambo_admin": ("finance.view", "finance_report.view"),
}

USERS = (
    (FINANCE_EXPERT, "کارشناس مالی نمونه"),
    (SITE_SUPERVISOR, "سرپرست کارگاه نمونه"),
    (PLANNER, "برنامه‌ریز نمونه"),
    (DENIED_EDITOR, "کاربر با محدودیت نمونه"),
    (OUTSIDER, "کاربر سازمان دیگر نمونه"),
)

#: `user_roles` rows: (user, role code, organization, project). A NULL project means the
#: role applies across the organization.
#: `DENIED_EDITOR` holds `finance_manager`, deliberately not `org_chief`.
#:
#: The first attempt gave them `org_chief` and the demo failed to prove anything: editing
#: settings still worked, because `settings_edit_permission` asks an org chief for
#: `finance.view` rather than `finance.edit`, and only `finance.edit` had been denied.
#:
#: That is worth knowing on its own -- **denying `finance.edit` does not stop an org chief
#: from editing project settings** -- and it is recorded as a risk in the demo documents
#: rather than being hidden by picking a role that makes the demo look tidy.
USER_ROLES = (
    (FINANCE_EXPERT, "org_chief", None),
    (SITE_SUPERVISOR, "finance_expert", None),
    (PLANNER, "viewer", None),
    (DENIED_EDITOR, "finance_manager", None),
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

    previous = None
    for snapshot in seed.PROGRESS_SNAPSHOTS:
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
            VALUES (%s, %s, %s, 'ACTUAL', %s, %s, %s, %s, %s, 'demo-fixture', %s, %s, %s, %s)
        """, (snapshot["host_snapshot_id"], seed.PROJECT_ID, snapshot["host_file_version_id"],
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
