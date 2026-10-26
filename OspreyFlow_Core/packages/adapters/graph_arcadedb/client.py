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

**A Raft cluster** (`ha`, `ARCADEDB_HA`; `05_DEPLOYMENT.md` §3b, ADR-101 Amendment 2) is written
through its leader, every request saying `X-ArcadeDB-Read-Consistency: eventual`. On 26.10.1 with
the Groovy engine, a Gremlin command is analysed before it runs — on a follower to decide whether to
forward it, on the leader unless the request says `eventual` — and the analysis evaluates the script
without its parameters: a command with parameters failed on every node, and a script that iterates
itself ran twice. The leader is found by asking the configured address (the Service in front of
every node) for `/api/v1/cluster`, trusted for `_LEADER_TTL_SECONDS`, and asked for again after a
request that could not reach it. A request that lands on a follower during an election fails in
words; it is never retried here, since a session lives on the server that opened it.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
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
    #: A Raft cluster: written through its leader (the module's docstring).
    ha: bool = False

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
            ha=os.environ.get("ARCADEDB_HA", "").lower() in {"1", "true", "yes"},
        )


#: ADR-127 Amendment 20: ArcadeDB 26.10.1 expires an HTTP transaction session left idle for 5 to 10
#: seconds (404 "Remote transaction session not found or expired"). An open transaction is sent a
#: no-op read whenever this many seconds have passed since its last call.
KEEPALIVE_SECONDS = 3.0

#: ADR-127 Amendment 21: a session no real call has used for this long is no longer kept alive (a
#: transaction the code abandoned, such as a cancelled request's), and ArcadeDB expires it as
#: before.
MAX_KEEPALIVE_IDLE = 30 * 60.0


@dataclass(slots=True)
class _Session:
    """What the client keeps for one open transaction session (ADR-127 Amendments 20 and 21)."""

    #: Held by every real call on the session and by the keep-alive, so they never overlap.
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    opened: float = field(default_factory=time.monotonic)
    #: When a real call last started or finished on it; a keep-alive does not move this.
    last_real: float = field(default_factory=time.monotonic)
    #: When a keep-alive last reached it.
    last_alive: float = 0.0
    task: asyncio.Task[None] | None = None


#: How long a found leader is trusted before the cluster is asked for it again.
_LEADER_TTL_SECONDS = 2.0
_EVENTUAL = {"X-ArcadeDB-Read-Consistency": "eventual"}


class ResultTruncatedError(Exception):
    """The server cut a result short (`CLAUDE.md` rule 2): refused rather than returned."""


class ArcadeDBClient:
    def __init__(
        self,
        config: ArcadeDBConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        keepalive_seconds: float | None = KEEPALIVE_SECONDS,
        max_keepalive_idle: float = MAX_KEEPALIVE_IDLE,
    ) -> None:
        self._config = config
        #: `None` turns the keep-alive off (the live test's plant, nothing else).
        self._keepalive_seconds = keepalive_seconds
        self._max_keepalive_idle = max_keepalive_idle
        #: Each open session, from its begin to the commit or rollback being sent.
        self._sessions: dict[str, _Session] = {}
        self._transport = transport
        self._http = self._client_for(config.base_url)
        # A cluster: the configured address (`_service`) answers which node leads, and `_http` is
        # pointed at that node; earlier leaders' clients are closed with this one.
        self._service = self._http
        self._leader: str | None = None
        self._leader_found_at = 0.0
        self._earlier: list[httpx.AsyncClient] = []
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
        sessions = list(self._sessions.values())
        tasks = [t.task for t in sessions if t.task is not None]
        self._sessions.clear()
        for session in sessions:
            self._cancel_task(session)
        await asyncio.gather(*tasks, return_exceptions=True)
        for client in {id(c): c for c in (*self._earlier, self._service, self._http)}.values():
            await client.aclose()

    def _client_for(self, base_url: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=base_url,
            auth=(self._config.username, self._config.password),
            timeout=30.0,
            headers=_EVENTUAL if self._config.ha else None,
            transport=self._transport,
        )

    async def _follow_leader(self) -> None:
        if self._leader and time.monotonic() - self._leader_found_at < _LEADER_TTL_SECONDS:
            return
        resp = await self._service.get("/api/v1/cluster")
        self._raise_for_error(resp)
        said = resp.json() if resp.content else {}
        address = said.get("leaderHttpAddress")
        if not address:
            raise ArcadeDBError(
                "the ArcadeDB cluster has no leader at present (an election may be under way); "
                "nothing was sent"
            )
        if address != self._leader:
            if self._http is not self._service:
                self._earlier.append(self._http)
            self._http = self._client_for(f"http://{address}")
            self._leader = address
        self._leader_found_at = time.monotonic()

    async def _post(
        self, path: str, *, ends_session: bool = False, **kwargs: Any
    ) -> httpx.Response:
        """Every real call. One on an open session holds the session's lock (so no keep-alive is
        beside it) and records itself as the session's last real call. `ends_session` (commit and
        rollback) removes the session before releasing the lock, so a keep-alive waiting for it
        finds it gone; one already sent has finished, since this call waited for the lock."""
        session_id = (kwargs.get("headers") or {}).get("arcadedb-session-id")
        session = self._sessions.get(session_id) if session_id is not None else None
        if session is None or session_id is None:
            return await self._send(path, **kwargs)
        async with session.lock:
            session.last_real = time.monotonic()
            try:
                return await self._send(path, **kwargs)
            finally:
                session.last_real = time.monotonic()
                if ends_session and self._sessions.get(session_id) is session:
                    del self._sessions[session_id]
                    self._cancel_task(session)

    @staticmethod
    def _cancel_task(session: _Session) -> None:
        task, session.task = session.task, None
        if task is not None and task is not asyncio.current_task():
            task.cancel()

    async def _send(self, path: str, **kwargs: Any) -> httpx.Response:
        if self._config.ha:
            await self._follow_leader()
        try:
            return await self._http.post(path, **kwargs)
        except httpx.TransportError:
            # Asked for again next time: the leader may have gone.
            self._leader_found_at = 0.0
            raise

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
        resp = await self._post("/api/v1/server", json={"command": command})
        self._raise_for_error(resp)
        return resp.json().get("result")

    # --- transactions ------------------------------------------------------

    async def begin_transaction(self) -> str:
        resp = await self._post(f"/api/v1/begin/{self._config.database}")
        self._raise_for_error(resp)
        session_id = resp.headers.get("arcadedb-session-id")
        if not session_id:
            raise ArcadeDBError("ArcadeDB did not return a session id for the new transaction")
        self._tx_log[str(session_id)] = []
        session = _Session()
        self._sessions[str(session_id)] = session
        if self._keepalive_seconds is not None:
            session.task = asyncio.create_task(self._keep_alive(str(session_id), session))
        return str(session_id)

    def _discard_session(self, session_id: str) -> None:
        """Forgets a session whose commit or rollback was never sent (a replay that failed)."""
        session = self._sessions.pop(session_id, None)
        self._tx_log.pop(session_id, None)
        if session is not None:
            self._cancel_task(session)

    async def _keep_alive(self, session_id: str, session: _Session) -> None:
        """Sends the session a no-op read whenever `_keepalive_seconds` have passed since its last
        call (ADR-127 Amendment 20), under the session's lock, so never beside a real call. Not
        recorded among the commands a failed commit replays. It stops, saying nothing, when one
        fails (the transaction's next real call reports the expiry, as it would without a
        keep-alive); and, with a warning, once no real call has used the session for
        `_max_keepalive_idle` (Amendment 21), when ArcadeDB expires it as before."""
        assert self._keepalive_seconds is not None
        interval = self._keepalive_seconds
        try:
            while self._sessions.get(session_id) is session:
                now = time.monotonic()
                if now - session.last_real > self._max_keepalive_idle:
                    _log.warning(
                        "arcadedb: no longer keeping session %s alive: no call has used it for "
                        "%.0f s and it has been open %.0f s; ArcadeDB will expire it",
                        session_id,
                        now - session.last_real,
                        now - session.opened,
                    )
                    # Nothing is held for the life of the process: ArcadeDB expires the session,
                    # so a later commit of it is refused (404, not retried) and has nothing to
                    # replay.
                    self._discard_session(session_id)
                    return
                idle = now - max(session.last_real, session.last_alive)
                if idle < interval:
                    await asyncio.sleep(interval - idle)
                    continue
                async with session.lock:
                    if self._sessions.get(session_id) is not session:
                        return
                    if time.monotonic() - max(session.last_real, session.last_alive) < interval:
                        continue
                    resp = await self._send(
                        f"/api/v1/command/{self._config.database}",
                        json={"language": "sql", "command": "SELECT 1", "limit": -1},
                        headers={"arcadedb-session-id": session_id},
                    )
                    if resp.status_code >= 400:
                        return
                    session.last_alive = time.monotonic()
        except Exception:  # noqa: BLE001 - a keep-alive that fails ends quietly (docstring)
            return

    async def _commit_once(self, session_id: str) -> None:
        resp = await self._post(
            f"/api/v1/commit/{self._config.database}",
            ends_session=True,
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
                    try:
                        for language, command, params in pending_replay:
                            await self.command(language, command, params=params, session_id=current)
                    except BaseException as failure:
                        # Whatever the replay raises (a cancellation included), the replacement
                        # session is not left with a keep-alive on it. An error that is retried
                        # hands the retry the WHOLE list being replayed, not the prefix this
                        # session completed: the next attempt replays all of it into a new session.
                        self._discard_session(current)
                        if isinstance(failure, ArcadeDBError | httpx.TransportError):
                            self._tx_log[current] = list(pending_replay)
                        raise
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
        try:
            resp = await self._post(
                f"/api/v1/rollback/{self._config.database}",
                ends_session=True,
                headers={"arcadedb-session-id": session_id},
            )
        finally:
            self._tx_log.pop(session_id, None)
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
        rows = await self.command("gremlin", command, params=params, session_id=session_id)
        return [_gremlin_row(row) for row in rows]

    async def command(
        self,
        language: str,
        command: str,
        *,
        params: Mapping[str, Any] | None = None,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        # Every row (`-1`): left out, the server stops at 20,000 and says so only in `truncated`, so
        # a larger read came back cut as if whole (rule 2, measured on 26.10.1). The port's reads
        # bound themselves: the working set's caps are counted first, and bulk reads page.
        body: dict[str, Any] = {"language": language, "command": command, "limit": -1}
        if params:
            body["params"] = dict(params)
        headers = {"arcadedb-session-id": session_id} if session_id else None
        resp = await self._post(
            f"/api/v1/command/{self._config.database}", json=body, headers=headers
        )
        self._raise_for_error(resp)
        answer = resp.json()
        if answer.get("truncated"):
            raise ResultTruncatedError(
                f"ArcadeDB returned {answer.get('returned', '?')} rows and said there were more "
                f"(limit {answer.get('limit', '?')}); a cut result is never passed on as whole"
            )
        result = answer.get("result", [])
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


def _is_entries(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(e, dict) and e.keys() == {"key", "value"} for e in value)
    )


def _gremlin_value(value: Any) -> Any:
    """A Gremlin map as ArcadeDB 26 sends it, a list of `{"key", "value"}` entries, as the dict
    ArcadeDB 25.5.1 sent. A later entry wins, as it did there: `elementMap()` lists the record id
    (`T.id`, `#1:0`) before the `id` property, and the property is the element's id here."""
    if _is_entries(value):
        return {e["key"]: _gremlin_value(e["value"]) for e in value}
    return value


def _gremlin_row(row: Any) -> Any:
    """ArcadeDB 26 wraps a map result in `{"result": [entries]}`; 25.5.1 returned the map itself.
    A scalar (`{"result": 6}`) is left as it is."""
    if isinstance(row, dict) and row.keys() == {"result"} and _is_entries(row["result"]):
        return _gremlin_value(row["result"])
    return row
