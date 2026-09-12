"""What Core calls the people whose ids Finance stores.

Finance keeps actors as bare UUIDs on purpose -- see `app.finance.domain.actors`. This is the
one adapter that turns them back into names, and it reads Core's own `users` table rather
than any Finance table, so no name is ever copied into Finance's schema and none can drift
from the host's.

WHY `display_name` AND NOTHING ELSE
`users` also carries `email` and `phone`. Neither is a fallback here. A finance page showing
`admin@bambo.local` because a display name was blank would put a contact address on screen
for every reader of every invoice, which is a disclosure nobody asked for to solve a cosmetic
problem. A user with no display name simply has no name, the lookup omits them, and the
caller renders the id it already had.

WHY INACTIVE USERS ARE STILL NAMED
`is_active` is deliberately not filtered. A confirmed invoice names who confirmed it, and
that fact does not change when the person later leaves -- hiding the name of a deactivated
user would blank out exactly the historical records an audit most wants to read.

WHY A MISSING TABLE IS NOT AN ERROR
Finance must run on a host with no Core at all; `devhost` wires this adapter only when a Core
connection exists, but the table can still be absent on a Finance-only database. The probe
below asks once, remembers, and answers `{}` forever after -- so the pages keep working and
every actor renders as an id, which is exactly the behaviour that existed before this adapter
was written.
"""

from uuid import UUID

from psycopg.rows import dict_row

#: Names for a batch of ids in one round trip. `= ANY` rather than an IN-list built by string
#: interpolation: the ids arrive as text from the JSON boundary and are cast once, here, where
#: a malformed one fails as a cast instead of reaching the query as SQL.
_NAMES = """
    SELECT id, display_name
      FROM users
     WHERE id = ANY(%(ids)s::uuid[])
       AND display_name IS NOT NULL
       AND btrim(display_name) <> ''
"""

_TABLE_PRESENT = "SELECT to_regclass('users') IS NOT NULL AS present"


class CoreActorDirectory:
    """`ActorDirectory` backed by Core's `users` table on the shared database."""

    def __init__(self, connection):
        self._connection = connection
        #: None until the first lookup asks. Tri-state on purpose: "not yet asked" is a
        #: different thing from "asked, and there is no such table".
        self._present: bool | None = None

    async def _rows(self, sql, params):
        async with self._connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(sql, params)
            return await cursor.fetchall()

    async def _table_present(self) -> bool:
        if self._present is None:
            try:
                rows = await self._rows(_TABLE_PRESENT, {})
                self._present = bool(rows and rows[0]["present"])
            except Exception:  # noqa: BLE001 -- see the module docstring
                # A database that will not answer even this cannot answer the lookup either.
                # Remembering the refusal keeps one unreachable host from adding a failed
                # query to every page load.
                self._present = False
        return self._present

    async def names(self, user_ids) -> dict[str, str]:
        """Map id -> display name for those ids Core knows, omitting the rest.

        Ids that are not well-formed UUIDs are dropped before the query rather than allowed
        to fail it: one bad value in a fifty-row page would otherwise cost the whole page its
        names, and a value that is not an id names nobody in any case.
        """
        wanted = set()
        for value in (user_ids or ()):
            if value is None:
                continue
            try:
                wanted.add(str(UUID(str(value))))
            except (ValueError, AttributeError, TypeError):
                continue
        if not wanted or not await self._table_present():
            return {}
        try:
            rows = await self._rows(_NAMES, {"ids": sorted(wanted)})
        except Exception:  # noqa: BLE001
            # A lookup is a decoration. A host that cannot answer it gets pages full of ids,
            # which is what it had before, not a 500 on a report somebody needs.
            return {}
        return {str(row["id"]): row["display_name"] for row in rows}
