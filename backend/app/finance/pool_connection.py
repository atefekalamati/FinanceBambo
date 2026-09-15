"""Repository-compatible connection facade over a pool owned by the BAMBO host."""

from contextvars import ContextVar
import sys


class HostPoolConnection:
    """Acquire per operation and pin one connection for an explicit transaction.

    The supplied pool must expose ``connection(timeout=...)`` as an async context manager,
    which is the contract of psycopg_pool and can also be adapted by the host.  This class
    does not create or close the pool and therefore does not compete with the host lifespan.
    """

    def __init__(self, pool, *, timeout_seconds: float = 5.0):
        if timeout_seconds <= 0:
            raise ValueError("database pool timeout must be positive")
        self.pool = pool
        self.timeout_seconds = timeout_seconds
        self._current = ContextVar("finance_pool_connection", default=None)

    def cursor(self, **kwargs):
        return _CursorLease(self, kwargs)

    def transaction(self, *args, **kwargs):
        return _TransactionLease(self, args, kwargs)


class _CursorLease:
    def __init__(self, owner, kwargs):
        self.owner, self.kwargs = owner, kwargs
        self.lease = self.cursor_context = None

    async def __aenter__(self):
        connection = self.owner._current.get()
        if connection is None:
            self.lease = self.owner.pool.connection(timeout=self.owner.timeout_seconds)
            connection = await self.lease.__aenter__()
        try:
            self.cursor_context = connection.cursor(**self.kwargs)
            return await self.cursor_context.__aenter__()
        except BaseException:
            if self.lease is not None:
                await self.lease.__aexit__(*sys.exc_info())
            raise

    async def __aexit__(self, *error):
        suppress = await self.cursor_context.__aexit__(*error)
        if self.lease is not None:
            pool_suppress = await self.lease.__aexit__(*error)
            return bool(suppress or pool_suppress)
        return suppress


class _TransactionLease:
    def __init__(self, owner, args, kwargs):
        self.owner, self.args, self.kwargs = owner, args, kwargs
        self.lease = self.transaction_context = self.token = None

    async def __aenter__(self):
        if self.owner._current.get() is not None:
            raise RuntimeError("nested Finance transaction is not supported")
        self.lease = self.owner.pool.connection(timeout=self.owner.timeout_seconds)
        connection = await self.lease.__aenter__()
        self.token = self.owner._current.set(connection)
        try:
            self.transaction_context = connection.transaction(*self.args, **self.kwargs)
            return await self.transaction_context.__aenter__()
        except BaseException:
            self.owner._current.reset(self.token)
            await self.lease.__aexit__(*sys.exc_info())
            raise

    async def __aexit__(self, *error):
        try:
            suppress = await self.transaction_context.__aexit__(*error)
        finally:
            self.owner._current.reset(self.token)
        pool_suppress = await self.lease.__aexit__(*error)
        return bool(suppress or pool_suppress)
