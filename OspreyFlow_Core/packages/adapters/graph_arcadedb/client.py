"""Thin async HTTP client over ArcadeDB's REST API.

ArcadeDB's TinkerPop bridge is reached through its `/api/v1/command`
endpoint with `language: gremlin` — this container does not run a separate
Gremlin Server/WebSocket listener by default, so this is the actual
transport `local-lite`'s single ArcadeDB container offers. The Gremlin
*content* still never leaves the Vault: the Conduit only ever calls typed
`GraphPort` methods, and the traversal strings are built and sent
server-side, by this adapter, from the bounded builders in `builders.py`.

A transaction commit that fails with a transient server-side error (see
`_NON_RETRYABLE_COMMIT_EXCEPTIONS` below) is retried by redoing the whole
transaction, not by re-sending the failed commit: ArcadeDB's commit is
all-or-nothing, so a failed commit means nothing from that transaction
was applied, and every command already went through this client with its
values already substituted (the builders never re-roll a random id at
execution time), so replaying the exact same recorded commands in a fresh
transaction reproduces the identical write. This client keeps that replay
log; callers never see it — `commit_transaction` either succeeds or
raises, same as before.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

import httpx

_log = logging.getLogger(__name__)


class ArcadeDBError(Exception):
    """An ArcadeDB command failed — surfaced with the server's own message.

    `exception_class` is the server's own `exception` field (e.g.
    `com.arcadedb.exception.SchemaException`) when the body is JSON shaped
    that way — ArcadeDB returns the same HTTP status (usually 500, sometimes
    503) for both a permanent command error and a transient server-side
    failure, so callers that need to tell those apart (see `schema.py`'s
    DDL retry) key off this instead of `status_code`."""

    def __init__(
        self, message: str, *, status_code: int | None = None, exception_class: str | None = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.exception_class = exception_class


_COMMIT_MAX_ATTEMPTS = 3
_COMMIT_BACKOFF_BASE_SECONDS = 0.2

# Retry policy for a failed COMMIT — deliberately not the same denylist
# `schema.py` uses for DDL. There, `ConcurrentModificationException` on a
# schema statement is a real conflict that should fail fast. Here it is
# the opposite: it is ArcadeDB's optimistic-concurrency check catching two
# transactions that touched overlapping data, and the whole point of this
# retry is to redo the transaction after the other one has released its
# lock. So it is retryable for a commit even though it is not for DDL.
# What stays non-retryable is a failure a replay would reproduce forever:
# a malformed command (a real bug in the generated Gremlin/SQL, per
# `builders.py`) or a genuine unique-constraint violation on caller data
# (the write really does collide with something already committed, not
# with an in-flight sibling transaction).
_NON_RETRYABLE_COMMIT_EXCEPTIONS = frozenset(
    {
        "com.arcadedb.exception.SchemaException",
        "com.arcadedb.query.sql.parser.ParseException",
        "com.arcadedb.exception.DuplicatedKeyException",
    }
)


@dataclass(frozen=True, slots=True)
class ArcadeDBConfig:
    host: str = "localhost"
    http_port: int = 2480
    username: str = "root"
    password: str = "playwithdata123"
    database: str = "ospreyflow"

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.http_port}"

    @classmethod
    def from_env(cls, database: str) -> ArcadeDBConfig:
        """CI and local `docker run` both read connection info from the
        environment — see the `conformance` job in `.github/workflows/ci.yml`."""
        return cls(
            host=os.environ.get("ARCADEDB_HOST", "localhost"),
            http_port=int(os.environ.get("ARCADEDB_HTTP_PORT", "2480")),
            username=os.environ.get("ARCADEDB_USERNAME", "root"),
            password=os.environ.get("ARCADEDB_ROOT_PASSWORD", "playwithdata123"),
            database=database,
        )


class ArcadeDBClient:
    def __init__(self, config: ArcadeDBConfig) -> None:
        self._config = config
        self._http = httpx.AsyncClient(
            base_url=config.base_url,
            auth=(config.username, config.password),
            timeout=30.0,
        )
        # Every command issued against an open transaction, in order, so a
        # failed commit can be retried by replaying them into a fresh
        # transaction rather than re-sending the dead commit. Keyed by
        # session id; entries are dropped on commit (success or final
        # failure) and on rollback so this never grows across a session's
        # lifetime.
        self._tx_log: dict[str, list[tuple[str, str, dict[str, Any] | None]]] = {}

    @property
    def database(self) -> str:
        return self._config.database

    async def aclose(self) -> None:
        await self._http.aclose()

    # --- server / database lifecycle ------------------------------------

    async def create_database_if_absent(self) -> None:
        databases = await self._server_command("list databases")
        if self._config.database not in databases:
            await self._server_command(f"create database {self._config.database}")

    async def drop_database(self) -> None:
        await self.drop_database_named(self._config.database)

    async def list_databases(self) -> list[str]:
        """Server-level, independent of `self._config.database` — used by
        `testing.py`'s stale-database sweep, which operates on the whole
        server, not one test's own database."""
        return cast("list[str]", await self._server_command("list databases"))

    async def drop_database_named(self, name: str) -> None:
        databases = await self._server_command("list databases")
        if name in databases:
            await self._server_command(f"drop database {name}")

    async def _server_command(self, command: str) -> Any:
        resp = await self._http.post("/api/v1/server", json={"command": command})
        self._raise_for_error(resp)
        return resp.json().get("result")

    # --- transactions ------------------------------------------------------

    async def begin_transaction(self) -> str:
        resp = await self._http.post(f"/api/v1/begin/{self._config.database}")
        self._raise_for_error(resp)
        session_id = resp.headers.get("arcadedb-session-id")
        if not session_id:
            raise ArcadeDBError("ArcadeDB did not return a session id for the new transaction")
        self._tx_log[str(session_id)] = []
        return str(session_id)

    async def _commit_once(self, session_id: str) -> None:
        resp = await self._http.post(
            f"/api/v1/commit/{self._config.database}",
            headers={"arcadedb-session-id": session_id},
        )
        self._raise_for_error(resp)

    async def commit_transaction(self, session_id: str) -> None:
        """A commit is all-or-nothing on ArcadeDB's side: if this fails,
        nothing from `session_id`'s transaction was applied. On a failure
        classified as transient (see `_NON_RETRYABLE_COMMIT_EXCEPTIONS`),
        this redoes the whole transaction — begins a fresh session, resends
        every command this client sent under the failed one, in the same
        order, then commits that — rather than retrying the dead commit
        call itself, which would just fail the same way again. A
        non-retryable failure, or the last attempt, is raised as-is."""
        current = session_id
        pending_replay: list[tuple[str, str, dict[str, Any] | None]] | None = None
        for attempt in range(1, _COMMIT_MAX_ATTEMPTS + 1):
            try:
                if pending_replay is not None:
                    # Begins its own log entry for `current`; a failure
                    # here or in the replay below is classified and
                    # retried exactly like a failed commit itself — a
                    # replayed command failing is no less a sign of a
                    # transient conflict than the commit that triggered it.
                    current = await self.begin_transaction()
                    for language, command, params in pending_replay:
                        await self.command(language, command, params=params, session_id=current)
                    pending_replay = None
                await self._commit_once(current)
                self._tx_log.pop(current, None)
                return
            except ArcadeDBError as exc:
                non_retryable = (
                    exc.status_code is None
                    or exc.status_code < 500
                    or exc.exception_class in _NON_RETRYABLE_COMMIT_EXCEPTIONS
                )
                if non_retryable or attempt == _COMMIT_MAX_ATTEMPTS:
                    self._tx_log.pop(current, None)
                    raise
                _log.warning(
                    "arcadedb: commit of session %s failed (%s: %s); replaying its %d recorded "
                    "commands in a new transaction (attempt %d of %d)",
                    current,
                    exc.status_code,
                    exc.exception_class,
                    len(self._tx_log.get(current, [])),
                    attempt,
                    _COMMIT_MAX_ATTEMPTS,
                )
            except httpx.TransportError as exc:
                if attempt == _COMMIT_MAX_ATTEMPTS:
                    self._tx_log.pop(current, None)
                    raise
                # A commit that got no answer may still have been applied. Replaying it then writes
                # every edge in it a second time, so this is logged as unknown, never as failed.
                _log.warning(
                    "arcadedb: commit of session %s got no answer (%s); its outcome is UNKNOWN, "
                    "and replaying its %d recorded commands in a new transaction can write them "
                    "twice (attempt %d of %d)",
                    current,
                    type(exc).__name__,
                    len(self._tx_log.get(current, [])),
                    attempt,
                    _COMMIT_MAX_ATTEMPTS,
                )

            await asyncio.sleep(_COMMIT_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
            pending_replay = self._tx_log.pop(current, [])

    async def rollback_transaction(self, session_id: str) -> None:
        self._tx_log.pop(session_id, None)
        resp = await self._http.post(
            f"/api/v1/rollback/{self._config.database}",
            headers={"arcadedb-session-id": session_id},
        )
        self._raise_for_error(resp)

    # --- commands ------------------------------------------------------

    async def sql(
        self,
        command: str,
        *,
        params: Mapping[str, Any] | None = None,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return await self.command("sql", command, params=params, session_id=session_id)

    async def gremlin(
        self,
        command: str,
        *,
        params: Mapping[str, Any] | None = None,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return await self.command("gremlin", command, params=params, session_id=session_id)

    async def command(
        self,
        language: str,
        command: str,
        *,
        params: Mapping[str, Any] | None = None,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        body: dict[str, Any] = {"language": language, "command": command}
        if params:
            body["params"] = dict(params)
        headers = {"arcadedb-session-id": session_id} if session_id else None
        resp = await self._http.post(
            f"/api/v1/command/{self._config.database}", json=body, headers=headers
        )
        self._raise_for_error(resp)
        result = resp.json().get("result", [])
        if not isinstance(result, list):
            raise ArcadeDBError(f"unexpected ArcadeDB response shape: {result!r}")
        # Recorded only once the command has actually succeeded, and only
        # for a session this client itself opened (`begin_transaction`
        # seeds the log entry) — an unrecognised session_id is silently
        # not logged rather than growing an entry commit_transaction will
        # never clean up.
        if session_id is not None and session_id in self._tx_log:
            self._tx_log[session_id].append((language, command, dict(params) if params else None))
        return result

    @staticmethod
    def _raise_for_error(resp: httpx.Response) -> None:
        if resp.status_code >= 400:
            exception_class: str | None = None
            try:
                exception_class = resp.json().get("exception")
            except ValueError:
                pass
            raise ArcadeDBError(
                f"ArcadeDB error {resp.status_code}: {resp.text}",
                status_code=resp.status_code,
                exception_class=exception_class,
            )
