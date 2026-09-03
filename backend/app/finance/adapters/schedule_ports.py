"""The boundary a schedule source has to cross before Finance sees anything.

Direction is one-way and deliberate:

    schedule source -> normalization -> ProgressSnapshotInput -> Finance

Finance depends on `ProgressSnapshotInput` and on nothing upstream of it. It has no
importer, no file handling, and no knowledge of any scheduling tool — a grep for `.mpp`,
`mspdi`, or `primavera` across `app/` finds only display strings in dev seed data. That is
the property these protocols exist to keep true: a new source is a new implementation
here, never a new dependency inside Finance.
"""

from typing import Protocol, runtime_checkable

from ..domain.schedule import ProgressSnapshotInput


@runtime_checkable
class ProgressSourceAdapter(Protocol):
    """Anything that can state a project's progress in the normalized contract.

    One method, because that is the whole obligation. Whatever the source is — a
    scheduling file, the BAMBO host, a fixture — Finance's side of the conversation is the
    same, so swapping sources cannot change Finance.
    """

    async def get_snapshot_input(
        self, organization_id: str, project_id: str
    ) -> ProgressSnapshotInput: ...


class MppScheduleAdapter(Protocol):
    """NOT IMPLEMENTED UNTIL A REAL MPP SAMPLE IS AVAILABLE.

    This is the shape a real Microsoft Project reader must satisfy, recorded now so the
    boundary is fixed before anyone writes the reader, and so no one is tempted to reach
    into Finance from the parsing side.

    There is no implementation in this repository, and none should be written from
    documentation alone. Field availability in MPP varies by the version that saved the
    file, by whether a baseline was ever set, and by which columns the planner actually
    filled; a reader written against an assumed layout would produce confident, wrong
    numbers. Every method below therefore stays unimplemented until a real file exists to
    read, at which point `ProgressSnapshotInput`'s nullable fields say exactly what may be
    left unanswered.
    """

    def normalize_project(self, source: object) -> dict: ...

    def normalize_tasks(self, source: object) -> list: ...

    def normalize_resources(self, source: object) -> list: ...

    def normalize_assignments(self, source: object) -> list: ...

    def normalize_dependencies(self, source: object) -> list: ...

    async def get_snapshot_input(
        self, organization_id: str, project_id: str
    ) -> ProgressSnapshotInput: ...


class MppAdapterNotAvailable(NotImplementedError):
    """Raised if anything tries to read a real schedule file through this boundary.

    A stub that returned plausible-looking tasks would be worse than this error: the
    numbers would flow into a financial report and nothing downstream could tell they were
    invented.
    """

    def __init__(self, message="MPP parsing is not implemented; no real sample has been read yet"):
        super().__init__(message)
