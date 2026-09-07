# -*- coding: utf-8 -*-
"""Progress read straight from the MPP file -- no database, no MSP tables.

This is the adapter that makes Finance independent of MSP/Core. It fills the same
``ProgressSnapshotProvider`` port that ``CoreProgressSnapshotProvider`` fills, so Finance
neither knows nor cares which one the host wired: it asks the port for a snapshot and gets
the same feed shape either way.

WHY THIS EXISTS
The schedule file is the external source of truth for what was planned and how far it has
got. Reading it does not require `msp_tasks`, `msp_snapshots`, `msp_task_metrics` or a
bridge row -- those are MSP/Core's own persistence of the same file, useful to MSP and
irrelevant to a Finance calculation. A deployment that runs Finance alone must still be
able to read the file, and this adapter is how.

ONE READER, ONE SHAPE
The parsing is `MpxjMppReader` -- the same reader the MSP importer uses, not a second
one -- and the feed rows are built by the same `task_row` / `assignment_row` functions the
Core adapter uses. Only the SOURCE of the rows differs: parsed file records here, SELECTed
database rows there. That is deliberate; two shaping implementations would be two
definitions of what a feed row means.

IDENTITY WITHOUT A DATABASE
A file-backed snapshot has no `msp_snapshots.id` to be named by, so its identity is the
file's SHA-256 -- the content itself. It is stable (the same bytes always answer to the
same id), it is honest (a different file is a different snapshot) and it needs no table.
`hostSnapshotId` is null, because there is no host snapshot: saying otherwise would invent
an MSP identity that does not exist.
"""

import asyncio
from datetime import date, datetime

from .mpp_files import resolve_import_file
from .mpp_progress_shape import file_rows
from .progress import (ACTIVITY_CODE_FIELDS, STATUS_READY, assignment_row, task_row)

#: What the feed calls a snapshot that came from a file rather than from MSP's tables.
SOURCE_TYPE_FILE = "mpp_file"


class MppFileProgressProvider:
    """`ProgressSnapshotProvider` over a schedule file. Reads nothing else.

    ``import_root`` and ``file_name`` say which file; both come from configuration, never
    from a request, and the path gate in `mpp_files` is the same one the importer uses.
    The parse is cached by (path, sha256): re-reading a 2 MB schedule through a JVM on
    every request would make a report page take seconds, and the sha is what makes the
    cache safe -- change the file and the key changes with it.
    """

    def __init__(self, reader, *, import_root, file_name=None,
                 activity_code_fields=ACTIVITY_CODE_FIELDS, max_size_mb=100):
        self._reader = reader
        self._import_root = import_root
        #: A fixed name pins every project to one file (single-project deployments and
        #: tests). Left None, the file is the project's own `<project_id>.mpp` -- the
        #: same convention the importer and the periodic tick already use, so there is
        #: one naming rule and one configured root, not a second competing setting.
        self._file_name = file_name
        self._activity_code_fields = tuple(activity_code_fields)
        self._max_size_mb = max_size_mb
        self._cache = {}

    def _name_for(self, project_id):
        return self._file_name or ("%s.mpp" % project_id)

    # ------------------------------------------------------------------------- reading
    async def _parse(self, project_id):
        """The resolved file and its parsed contents, or a raised MppFileError.

        Errors are NOT swallowed into an empty feed. A missing file, a wrong extension or
        a corrupt schedule each raise their own coded error, because a report that quietly
        says "nothing" about a file nobody could read is the worst of the three outcomes.
        """
        resolved = resolve_import_file(self._import_root, self._name_for(project_id),
                                       self._max_size_mb)
        cached = self._cache.get(resolved.sha256)
        if cached is None:
            cached = await asyncio.to_thread(self._reader.read, resolved.path)
            # Keyed by content, so an edited file is re-read and an unchanged one is not.
            # Bounded, because a long-lived host must not accumulate parsed schedules.
            if len(self._cache) >= 4:
                self._cache.pop(next(iter(self._cache)))
            self._cache[resolved.sha256] = cached
        return resolved, cached

    def _envelope(self, resolved, parsed, organization_id, project_id):
        rows = file_rows(parsed)
        if rows["assignments"]:
            feed = [assignment_row(row, self._activity_code_fields)
                    for row in rows["assignments"]]
        else:
            feed = [task_row(row, self._activity_code_fields) for row in rows["tasks"]]
        return {
            "snapshot": {
                "organizationId": str(organization_id) if organization_id else None,
                "projectId": project_id,
                # The file's own content identity. No database row is being named.
                "progressSnapshotId": resolved.sha256,
                "hostSnapshotId": None,
                "hostFileVersionId": None,
                "sourceFileVersionId": None,
                "sourceFileNameSafe": resolved.relative_name,
                # The file states no reporting date of its own that we have confirmed a
                # calendar for, so the date the bytes were last written is used and said
                # to be that -- never a Jalali string converted on a guess.
                "reportingDate": date.fromtimestamp(
                    resolved.path.stat().st_mtime).isoformat(),
                "status": STATUS_READY,
                "snapshotType": rows["snapshot_type"],
                "sourceType": SOURCE_TYPE_FILE,
                "importedBy": None,
                "importedAt": datetime.fromtimestamp(
                    resolved.path.stat().st_mtime).isoformat(),
            },
            "assignments": feed,
        }

    # -------------------------------------------------------------------- the port API
    async def current_snapshot(self, organization_id, project_id, as_of=None):
        resolved, parsed = await self._parse(project_id)
        return self._envelope(resolved, parsed, organization_id, project_id)

    async def get_snapshot(self, organization_id, project_id, snapshot_id):
        """The file, when the caller names its content id -- otherwise None.

        None rather than an error for an unknown id: this provider has issued exactly one
        identifier, and a caller asking for any other is asking for a snapshot it does not
        have. That is the same answer the Core adapter gives for an id it never issued.
        """
        resolved, parsed = await self._parse(project_id)
        if str(snapshot_id) != resolved.sha256:
            return None
        return self._envelope(resolved, parsed, organization_id, project_id)
