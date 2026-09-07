# -*- coding: utf-8 -*-
"""Parsed file records reshaped into the rows the feed builders already understand.

`task_row` and `assignment_row` in `progress.py` define what a feed row means. They were
written against rows a SELECT returns; this module hands them the same keys built from a
parsed file instead. Nothing here decides feed semantics -- it only puts file data into
the shape those two functions read, so a file-backed feed and a database-backed feed
cannot drift into two different meanings of the same field.

Types are normalised here too: the reader states numbers as decimal STRINGS (deliberately,
so no float ever touches them) while psycopg hands the Core adapter `Decimal`. The shared
builders must see one type from both, so the strings become `Decimal` on the way through.

The database identities those row dicts carry (`id`, `snapshot_id`) do not exist for a
file, so they are None. Nothing downstream may use them: `task_external_id` prefers the
stable MSP `uid`, which the file does state.
"""

from decimal import Decimal, InvalidOperation

from .finance_quantity import approved_quantity


def _num(value):
    """The reader's decimal STRING as a Decimal, matching what psycopg hands the Core
    adapter for the same column. Without this the two sources feed the shared builders
    different types and the first `format(value, "f")` fails on the file path."""
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _resource_index(parsed):
    return {r["uid"]: r for r in parsed.resources if r["uid"] is not None}


def _bambo_type(native_type):
    """Core's classification, only where the file gives a basis for one.

    MATERIAL is unambiguous. WORK is not -- MS Project does not say whether a work
    resource is labour or equipment -- so it stays None rather than being guessed, exactly
    as the Core adapter leaves it null for the same reason.
    """
    return "material" if (native_type or "").upper() == "MATERIAL" else None


def _task_fields(task):
    """The task half of a feed row, including the custom columns read by alias."""
    metrics = task.get("metrics") or {}
    fields = {
        # No database identity exists for a file-parsed task.
        "id": None,
        "uid": task["uid"],
        "guid": task["guid"],
        "task_id": task["task_id"],
        "name": task["name"],
        "wbs": task["wbs"],
        "outline_number": task["outline_number"],
        "outline_level": task["outline_level"],
        "start": task["start"],
        "finish": task["finish"],
        "percent_complete": _num(task["percent_complete"]),
        "percent_work_complete": _num(task["percent_work_complete"]),
        "physical_percent_complete": _num(task["physical_percent_complete"]),
        "text1": task["text1"],
    }
    # The planners' own columns, under the same names the Core feed query selects, so the
    # shared builders read them identically from either source.
    for key in ("item_quantity", "weight_rial", "weight_time", "weight_base",
                "actual_progress", "actual_progress_percent", "physical_progress",
                "planned_progress", "progress_variance", "task_cost",
                "jalali_start", "jalali_finish"):
        value = metrics.get(key)
        fields[key] = value if key.startswith("jalali_") else _num(value)
    return fields


def file_rows(parsed):
    """`{"tasks": [...], "assignments": [...], "snapshot_type": ...}` from a parsed file.

    Assignment rows are produced only for assignments whose task is in the file; the
    importer applies the same rule, and an assignment pointing at a task that is not there
    is an inconsistent file rather than a row to invent a task for.
    """
    resources = _resource_index(parsed)
    tasks_by_uid = {t["uid"]: t for t in parsed.tasks if t["uid"] is not None}

    tasks = [_task_fields(task) for task in parsed.tasks]

    assignments = []
    for assignment in parsed.assignments:
        task = tasks_by_uid.get(assignment["task_uid"])
        if task is None:
            continue
        resource = resources.get(assignment["resource_uid"]) or {}
        row = _task_fields(task)
        # ONE quantity rule for the Finance consumer: an approved column or nothing. The
        # MPXJ Material amount on the assignment is a real field, but it is not the
        # quantity the planners approved for pricing, and the persisted Finance rows
        # already say NULL for this file. A feed that said 3538.11 beside a table that
        # said NULL is exactly the split that let a fake executed value be computed.
        quantity, quantity_unit = approved_quantity(task)
        row.update({
            "assignment_uid": assignment["assignment_uid"],
            "task_uid": assignment["task_uid"],
            "resource_uid": assignment["resource_uid"],
            "units": _num(assignment["units"]),
            "planned_work": _num(assignment["planned_work"]),
            "actual_work": _num(assignment["actual_work"]),
            "remaining_work": _num(assignment["remaining_work"]),
            "planned_quantity": quantity,
            "actual_quantity": None,
            "remaining_quantity": None,
            "quantity_unit": quantity_unit,
            "assignment_work_complete_percent": _num(assignment["work_complete_percent"]),
            "resource_name": resource.get("name"),
            "native_type": resource.get("native_type"),
            "bambo_resource_type": _bambo_type(resource.get("native_type")),
            "resource_quantity_unit": (resource.get("quantity_unit")
                                       or resource.get("material_label")
                                       or resource.get("initials")),
        })
        assignments.append(row)

    # ACTUAL when anything in the file states progress, TARGET otherwise -- the same rule
    # the importer records on msp_file_versions, so the two agree about one file.
    has_progress = any(
        (task["percent_complete"] not in (None, "0", "0.0"))
        or ((task.get("metrics") or {}).get("actual_progress_percent")
            not in (None, "0", "0.0"))
        for task in parsed.tasks)
    return {"tasks": tasks, "assignments": assignments,
            "snapshot_type": "ACTUAL" if has_progress else "TARGET"}
