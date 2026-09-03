"""One place where a scheduling tool's identifiers become BAMBO external identifiers.

Finance already stores `activity_external_id` and `assignment_external_id` on estimate
lines, but nothing has ever decided what they look like — the columns are plain nullable
text with no format check, and the values arrive from whatever fed them. When a real
schedule source is connected, the mapping has to be decided once and applied in one
place, or two importers will disagree about which id belongs to which activity.

This module is that place. It is deliberately *not* wired into persistence: no migration
enforces the shape, no repository normalises on write, and no existing value is rewritten.
Until the production identifier convention is confirmed against real data, applying it to
stored rows would be a guess with a backfill attached.

WHY THE TASK ID IS NOT USED
Microsoft Project exposes both an ID and a UID per task. The ID is the row position and
renumbers whenever anyone inserts, deletes, or outdents a task; the UID is assigned once
and survives. Keying financial history to a row position would silently re-point an
estimate line's progress the first time a planner reorders the schedule, so only UID is
accepted here.
"""

import re

ACTIVITY_PREFIX = "ACT-"
ASSIGNMENT_PREFIX = "ASG-"

#: A proposal, not an enforced schema. See the module docstring.
EXTERNAL_ID_PATTERN = re.compile(r"^(ACT|ASG)-[A-Za-z0-9._-]+$")


class ExternalIdentifierError(ValueError):
    """The value cannot be turned into a stable external identifier."""


def _normalize_uid(value) -> str:
    if value is None:
        raise ExternalIdentifierError("a schedule UID is required")
    if isinstance(value, bool):
        # bool is an int subclass; True would silently become "1".
        raise ExternalIdentifierError("a boolean is not a schedule UID")
    text = str(value).strip()
    if not text:
        raise ExternalIdentifierError("a schedule UID is required")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", text):
        raise ExternalIdentifierError("a schedule UID may not contain separators or spaces")
    return text


def activity_external_id(task_uid) -> str:
    """`ACT-{TaskUID}` — the proposed convention, applied centrally so it can change once."""
    return ACTIVITY_PREFIX + _normalize_uid(task_uid)


def assignment_external_id(assignment_uid) -> str:
    """`ASG-{AssignmentUID}`, on the same terms as `activity_external_id`."""
    return ASSIGNMENT_PREFIX + _normalize_uid(assignment_uid)


def is_conventional(value) -> bool:
    """Whether a stored identifier already follows the proposed convention.

    Existing rows predate any convention, so this reports rather than enforces: it is what
    a future production audit would count with, not a validator anything must pass.
    """
    return bool(value) and EXTERNAL_ID_PATTERN.fullmatch(str(value)) is not None
