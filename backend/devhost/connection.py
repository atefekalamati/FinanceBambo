"""A connection handle that survives the database restarting underneath it.

Repositories capture whatever connection object they are handed at wiring time and keep
it for the life of the process. When the development database restarts — recreating the
container, `docker compose up` after Docker Desktop drops out — that captured connection
is closed for good, and every request afterwards fails with "the connection is closed"
until the whole dev host is restarted.

This hands the repositories a stable object instead, and swaps the real connection behind
it. Reconnection happens when a cursor or transaction is acquired, never in the middle of
one: an in-flight statement still fails, and only the next attempt recovers. Retrying a
half-applied write silently would be worse than a visible error.
"""

import asyncio

from psycopg import AsyncConnection, OperationalError


class ReconnectingConnection:
    """Quacks like an AsyncConnection for the two methods the repositories use."""

    def __init__(self, dsn: str):
        self._dsn = dsn
        self._connection: AsyncConnection | None = None
        self._lock = asyncio.Lock()

    async def live(self, force: bool = False) -> AsyncConnection:
        """Return an open connection, opening a fresh one if the current one is gone."""
        async with self._lock:
            if force and self._connection is not None:
                try:
                    await self._connection.close()
                except Exception:
                    pass
                self._connection = None
            if self._connection is None or self._connection.closed:
                # autocommit lets the repositories own their own transaction boundaries;
                # without it psycopg would hold one implicit transaction open forever.
                self._connection = await AsyncConnection.connect(self._dsn, autocommit=True)
            return self._connection

    async def close(self) -> None:
        async with self._lock:
            if self._connection is not None and not self._connection.closed:
                await self._connection.close()
            self._connection = None

    def cursor(self, **kwargs):
        return _Acquire(self, lambda connection: connection.cursor(**kwargs))

    def transaction(self, *args, **kwargs):
        return _Acquire(self, lambda connection: connection.transaction(*args, **kwargs))


class _Acquire:
    """Defers asking for the connection until the `async with` actually runs."""

    def __init__(self, holder: ReconnectingConnection, open_context):
        self._holder, self._open_context, self._context = holder, open_context, None

    async def __aenter__(self):
        try:
            connection = await self._holder.live()
            self._context = self._open_context(connection)
            return await self._context.__aenter__()
        except OperationalError:
            # The connection looked open but the server had gone. Drop it and try once
            # more; a second failure is a real outage and should surface.
            connection = await self._holder.live(force=True)
            self._context = self._open_context(connection)
            return await self._context.__aenter__()

    async def __aexit__(self, *exc_info):
        return await self._context.__aexit__(*exc_info)
