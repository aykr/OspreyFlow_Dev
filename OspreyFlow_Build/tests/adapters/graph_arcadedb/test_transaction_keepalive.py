"""ADR-127 Amendment 20: an open graph transaction is kept alive.

ArcadeDB 26.10.1 expires an HTTP transaction session left idle for 5 to 10 seconds (404 "Remote
transaction session not found or expired"). The client sends each open session a no-op read whenever
`KEEPALIVE_SECONDS` (3) have passed since the session's last call, and stops at commit, at rollback
and when it closes. The idle limit itself is shown against a real store by
`test_a_transaction_idle_for_twenty_seconds_still_commits` (live, below the pure cases). The cases
here run a short interval (0.3 s) over an in-memory transport, which answers as the real server does
where it matters: a command or a commit for a session the server no longer knows is a 404.

What a mistake would do, and the case that catches it:

- no keep-alive at all, so an idle session expires
  (`test_an_idle_session_is_sent_a_keepalive`);
- a keep-alive sent while the session is in use, or just after a real call, which is noise and a
  race (`test_no_keepalive_is_sent_within_the_interval_of_a_real_call`,
  `test_a_session_with_a_call_in_flight_is_not_sent_one`);
- a keep-alive that goes on after commit or rollback, or when the client closes, which would address
  a session the server has ended (`test_none_is_sent_after_commit_or_rollback`,
  `test_the_task_is_stopped_when_the_client_closes`);
- a keep-alive that fails and brings the run down, or is retried for ever
  (`test_a_failed_keepalive_stops_the_task_and_the_next_real_call_reports_the_expiry`);
- a keep-alive recorded among the commands a failed commit replays
  (`test_a_keepalive_is_not_replayed_by_a_retried_commit`).
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from adapters.graph_arcadedb import client as arcadedb_client

INTERVAL = 0.3


class Server:
    """A server that holds sessions open: one it has not heard from in `expire_after` seconds, or
    that has ended, answers a 404 as ArcadeDB does. `seen` is every request, in order. It answers
    after a short delay, and records an `overlap` whenever a request for a session arrives while
    another for the same session is still being answered (ArcadeDB serialises a session's calls
    badly, so the client must not send two at once)."""

    def __init__(self, *, expire_after: float | None = None) -> None:
        self.seen: list[tuple[str, str | None, str]] = []
        self.live: dict[str, float] = {}
        self.expire_after = expire_after
        self.fail_keepalives = False
        self.commit_failures = 0
        self.fail_replay_with: BaseException | None = None
        #: A 503 for the Nth command sent to the first replacement session, once.
        self.replay_503_at: int | None = None
        self._replayed = 0
        self.keepalive_delay = 0.05
        self.delay = 0.02
        self.overlaps: list[str] = []
        self._active: set[str] = set()
        self._count = 0

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        loop_time = asyncio.get_event_loop().time()
        session = request.headers.get("arcadedb-session-id")
        body = request.content.decode() if request.content else ""
        self.seen.append((request.url.path.rsplit("/", 2)[-2], session, body))
        if session is not None:
            if session in self._active:
                self.overlaps.append(body or request.url.path)
            self._active.add(session)
        try:
            await asyncio.sleep(self.keepalive_delay if "SELECT 1" in body else self.delay)
            return self._answer(request, session, body, loop_time)
        finally:
            if session is not None:
                self._active.discard(session)

    def _answer(
        self, request: httpx.Request, session: str | None, body: str, loop_time: float
    ) -> httpx.Response:
        if request.url.path.startswith("/api/v1/begin/"):
            self._count += 1
            self.live[f"s{self._count}"] = loop_time
            return httpx.Response(204, headers={"arcadedb-session-id": f"s{self._count}"})
        if session is not None:
            stamp = self.live.get(session)
            if stamp is None or (
                self.expire_after is not None and loop_time - stamp > self.expire_after
            ):
                return httpx.Response(
                    404, json={"error": "Remote transaction session not found or expired"}
                )
            if self.fail_keepalives and "SELECT 1" in body:
                return httpx.Response(500, json={"error": "keep-alive refused"})
            if session == "s2" and "/command/" in str(request.url):
                if self.fail_replay_with is not None:
                    raise self.fail_replay_with
                self._replayed += 1
                if self.replay_503_at == self._replayed:
                    return httpx.Response(503, json={"error": "try again"})
            self.live[session] = loop_time
        if request.url.path.startswith(("/api/v1/commit/", "/api/v1/rollback/")):
            if self.commit_failures and "/commit/" in request.url.path:
                self.commit_failures -= 1
                return httpx.Response(503, json={"error": "try again"})
            self.live.pop(session or "", None)
            return httpx.Response(204)
        return httpx.Response(200, json={"result": []})

    def keepalives(self, session: str | None = None) -> int:
        return sum(
            1
            for _, s, body in self.seen
            if "SELECT 1" in body and (session is None or s == session)
        )


def client_for(server: Server, **kwargs: Any) -> arcadedb_client.ArcadeDBClient:
    return arcadedb_client.ArcadeDBClient(
        arcadedb_client.ArcadeDBConfig("localhost", 2480, "root", "x", "d"),
        transport=httpx.MockTransport(server),
        **{"keepalive_seconds": INTERVAL, **kwargs},
    )


def held_nothing(client: arcadedb_client.ArcadeDBClient) -> bool:
    """Whether the client holds no entry for any session in any of its maps."""
    return all(not v for v in vars(client).values() if isinstance(v, dict | set))


def test_the_interval_is_three_seconds() -> None:
    """Amendment 20: whenever 3 seconds have passed since the session's last call."""
    assert arcadedb_client.KEEPALIVE_SECONDS == 3.0
    assert (
        arcadedb_client.ArcadeDBClient(arcadedb_client.ArcadeDBConfig())._keepalive_seconds == 3.0
    )


async def test_an_idle_session_is_sent_a_keepalive() -> None:
    """Catches no keep-alive: a session idle for several intervals still answers, because the
    server is told it is alive, where without it the server's own limit would have expired it."""
    server = Server(expire_after=INTERVAL * 2)
    client = client_for(server)
    tx = await client.begin_transaction()
    await asyncio.sleep(INTERVAL * 5)
    assert server.keepalives(tx) >= 2
    await client.sql("SELECT 2", session_id=tx)  # not expired
    await client.commit_transaction(tx)
    await client.aclose()


async def test_no_keepalive_is_sent_within_the_interval_of_a_real_call() -> None:
    """Catches a keep-alive sent on a timer that ignores the session's own last call: a real call
    every 0.1 s keeps the session in use for a second, and none is sent."""
    server = Server()
    client = client_for(server)
    tx = await client.begin_transaction()
    for _ in range(10):
        await asyncio.sleep(INTERVAL / 3)
        await client.sql("SELECT 2", session_id=tx)
    assert server.keepalives() == 0
    await client.rollback_transaction(tx)
    await client.aclose()


async def test_a_session_with_a_call_in_flight_is_not_sent_one() -> None:
    """A slow real call (longer than the interval) holds the session: no keep-alive is sent beside
    it. Catches a keep-alive that does not take the session's lock."""
    server = Server()
    server.delay = INTERVAL * 3
    client = client_for(server)
    tx = await client.begin_transaction()
    await client.sql("SLOW", session_id=tx)
    assert server.keepalives() == 0
    assert server.overlaps == []
    await client.rollback_transaction(tx)
    await client.aclose()


async def test_no_real_call_starts_while_a_keepalive_is_in_flight() -> None:
    """The other half of the lock: a real call made while a keep-alive is being answered waits for
    it, so the session never has two at once. The fake server records any overlap. Catches a real
    call that does not take the session's lock."""
    server = Server()
    server.keepalive_delay = INTERVAL * 2
    client = client_for(server)
    tx = await client.begin_transaction()
    await asyncio.sleep(INTERVAL + 0.1)  # the keep-alive is now being answered
    assert server.keepalives() == 1
    await client.sql("SELECT 2", session_id=tx)
    await client.commit_transaction(tx)
    assert server.overlaps == []
    await client.aclose()


async def test_a_session_with_no_real_call_is_not_kept_alive_past_the_bound(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Amendment 21: an abandoned transaction (a cancelled request's) is not kept open for the life
    of the process. Once no real call has used the session for `max_keepalive_idle` the keep-alive
    stops, and says so with the session's age. Catches a keep-alive whose own sends count as use."""
    server = Server()
    client = client_for(server, max_keepalive_idle=INTERVAL * 3)
    await client.begin_transaction()
    with caplog.at_level("WARNING", logger="adapters.graph_arcadedb.client"):
        await asyncio.sleep(INTERVAL * 6)
    sent = server.keepalives()
    assert 1 <= sent <= 4, "kept alive for the bound, then not"
    await asyncio.sleep(INTERVAL * 3)
    assert server.keepalives() == sent
    assert any("no longer keeping session s1 alive" in r.message for r in caplog.records)
    assert any("open " in r.message for r in caplog.records)
    assert held_nothing(client), "an abandoned session is not held for the life of the process"
    await client.aclose()


async def test_a_real_call_restarts_the_bound() -> None:
    """The bound is the time since a real call, so a session in use is kept alive indefinitely."""
    server = Server()
    client = client_for(server, max_keepalive_idle=INTERVAL * 3)
    tx = await client.begin_transaction()
    for _ in range(4):
        await asyncio.sleep(INTERVAL * 2)
        await client.sql("SELECT 2", session_id=tx)
    assert client._sessions[tx].task is not None and not client._sessions[tx].task.done()
    await client.rollback_transaction(tx)
    await client.aclose()


@pytest.mark.parametrize("keepalive", [INTERVAL, None])
@pytest.mark.parametrize("ending", ["commit", "rollback"])
async def test_no_entry_is_left_in_any_map_after_commit_or_rollback(
    ending: str, keepalive: float | None
) -> None:
    """Amendment 21: the session's bookkeeping goes once the commit or rollback has been sent, and
    nothing re-adds it, with the keep-alive on or off. Catches an entry left behind (the client
    would grow for the life of the process) in `_sessions` or the replay log."""
    server = Server()
    client = client_for(server, keepalive_seconds=keepalive)
    tx = await client.begin_transaction()
    await client.sql("SELECT 2", session_id=tx)
    await asyncio.sleep(INTERVAL * 1.5)
    if ending == "commit":
        await client.commit_transaction(tx)
    else:
        await client.rollback_transaction(tx)
    assert held_nothing(client), vars(client)
    await client.aclose()


async def test_an_entry_is_removed_even_when_the_commit_or_rollback_fails() -> None:
    server = Server()
    client = client_for(server)
    tx = await client.begin_transaction()
    server.live.clear()  # expired: the commit answers 404, which is not retried
    with pytest.raises(arcadedb_client.ArcadeDBError):
        await client.commit_transaction(tx)
    assert held_nothing(client)
    tx = await client.begin_transaction()
    server.live.clear()
    with pytest.raises(arcadedb_client.ArcadeDBError):
        await client.rollback_transaction(tx)
    assert held_nothing(client)
    await client.aclose()


@pytest.mark.parametrize(
    "failure", [asyncio.CancelledError(), ValueError("replay failed")], ids=["cancelled", "value"]
)
async def test_a_retried_commits_replacement_session_stops_its_keepalive(
    failure: BaseException,
) -> None:
    """A failed commit is retried in a replacement session; if the replay into it raises anything
    (a cancellation included), the replacement is not left with a keep-alive. Catches a task left
    on a session nothing will ever commit."""
    server = Server()
    client = client_for(server)
    tx = await client.begin_transaction()
    await client.sql("SELECT 3", session_id=tx)
    server.commit_failures = 1
    server.fail_replay_with = failure
    with pytest.raises(type(failure)):
        await client.commit_transaction(tx)
    assert held_nothing(client), vars(client)
    sent = server.keepalives("s2")
    await asyncio.sleep(INTERVAL * 3)
    assert server.keepalives("s2") == sent == 0
    await client.aclose()


@pytest.mark.parametrize("ending", ["commit", "rollback"])
async def test_none_is_sent_after_commit_or_rollback(ending: str) -> None:
    """Catches a task left running past the transaction: it would address a session the server has
    ended, and fail every interval for the life of the process."""
    server = Server()
    client = client_for(server)
    tx = await client.begin_transaction()
    await asyncio.sleep(INTERVAL * 2)
    before = server.keepalives()
    assert before >= 1
    if ending == "commit":
        await client.commit_transaction(tx)
    else:
        await client.rollback_transaction(tx)
    after_end = server.keepalives()
    await asyncio.sleep(INTERVAL * 4)
    assert server.keepalives() == after_end
    assert held_nothing(client)
    await client.aclose()


async def test_the_task_is_stopped_when_the_client_closes() -> None:
    """Catches a task that outlives the client: closing with a transaction open ends its task."""
    server = Server()
    client = client_for(server)
    await client.begin_transaction()
    await asyncio.sleep(INTERVAL * 2)
    tasks = [t.task for t in client._sessions.values() if t.task is not None]
    assert tasks and not any(t.done() for t in tasks)
    await client.aclose()
    assert all(t.done() for t in tasks)
    sent = server.keepalives()
    await asyncio.sleep(INTERVAL * 3)
    assert server.keepalives() == sent


async def test_a_failed_keepalive_stops_the_task_and_the_next_real_call_reports_the_expiry() -> (
    None
):
    """A keep-alive that fails ends the task (it is not retried for ever, and it does not raise into
    whatever the run is doing); the transaction's next real call reports what the server says, as
    it would without a keep-alive."""
    server = Server()
    server.fail_keepalives = True
    client = client_for(server)
    tx = await client.begin_transaction()
    await asyncio.sleep(INTERVAL * 4)
    assert server.keepalives() == 1, "one attempt, then the task stops"
    server.live.clear()  # the server has expired the session
    with pytest.raises(arcadedb_client.ArcadeDBError) as raised:
        await client.sql("SELECT 2", session_id=tx)
    assert raised.value.status_code == 404
    await client.aclose()


async def test_a_keepalive_is_not_replayed_by_a_retried_commit() -> None:
    """A failed commit is retried by replaying every command the client sent under the session into
    a new one; a keep-alive is not one of them, and the replacement session is kept alive and
    ended like the first."""
    server = Server()
    client = client_for(server)
    tx = await client.begin_transaction()
    await client.sql("SELECT 3", session_id=tx)
    await asyncio.sleep(INTERVAL * 2)
    assert server.keepalives(tx) >= 1
    server.commit_failures = 1
    await client.commit_transaction(tx)
    replayed = [body for path, s, body in server.seen if s == "s2" and path == "command"]
    assert len(replayed) == 1 and "SELECT 3" in replayed[0] and "SELECT 1" not in replayed[0]
    sent = server.keepalives()
    await asyncio.sleep(INTERVAL * 3)
    assert server.keepalives() == sent
    assert held_nothing(client)
    await client.aclose()


async def test_a_replay_that_fails_part_way_is_retried_whole() -> None:
    """A retried commit replays every command into a replacement session. When that replay fails
    part-way with a retryable error (a 503 on the second of three), the next attempt replays all
    three, in order, and commits them. Catches a retry handed only the commands the failed session
    completed, which would commit a prefix and lose the rest without a word."""
    server = Server()
    client = client_for(server, keepalive_seconds=None)
    tx = await client.begin_transaction()
    for n in (31, 32, 33):
        await client.sql(f"SELECT {n}", session_id=tx)
    server.commit_failures = 1
    server.replay_503_at = 2
    await client.commit_transaction(tx)
    replayed = [b for path, sid, b in server.seen if sid == "s3" and path == "command"]
    assert len(replayed) == 3
    for n, body in zip((31, 32, 33), replayed, strict=True):
        assert f"SELECT {n}" in body
    commits = [sid for path, sid, _ in server.seen if path == "commit"]
    assert commits == ["s1", "s3"], "the replacement that took every command is the one committed"
    assert held_nothing(client)
    await client.aclose()
