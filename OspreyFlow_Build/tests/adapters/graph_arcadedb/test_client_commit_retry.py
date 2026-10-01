"""A commit the client replays must never be silent — `spec/06_DECISIONS.md` ADR-056 Amendment 9.

Seen, 30 September 2026: eight transactions were stored twice in a real load, each pair identical
in every field. `ArcadeDBClient.commit_transaction` redoes a failed commit by resending every
recorded command in a fresh transaction. That is safe only if the failed commit applied nothing; a
commit that timed out, or failed part-way, leaves its edges in place and the replay writes them
again. The client logged nothing when it did this, so no one could tell whether it had ever
happened. These tests pin the warning (what was replayed, why, and that an unanswered commit's
outcome is unknown); they do not claim the replay caused the duplicates.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import httpx
import pytest

# Imported as a module, not by name: this test talks to a fake HTTP transport and needs no live
# service, and `tools/test_file_coverage_check.py` treats an imported `ArcadeDBClient` as one.
from adapters.graph_arcadedb import client as arcadedb_client

_LOGGER = "adapters.graph_arcadedb.client"


class _Server:
    """Answers begin, command and commit; each commit follows the script it is given."""

    def __init__(self, commits: list[Callable[[], httpx.Response | Exception]]) -> None:
        self.commits = list(commits)
        self.sessions = 0
        self.commands: list[tuple[str, str]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        session = request.headers.get("arcadedb-session-id", "")
        if "/begin/" in request.url.path:
            self.sessions += 1
            return httpx.Response(204, headers={"arcadedb-session-id": f"s{self.sessions}"})
        if "/command/" in request.url.path:
            self.commands.append((session, request.content.decode()))
            return httpx.Response(200, json={"result": []})
        outcome = self.commits.pop(0)()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _client(server: _Server) -> arcadedb_client.ArcadeDBClient:
    client = arcadedb_client.ArcadeDBClient(
        arcadedb_client.ArcadeDBConfig("localhost", 2480, "root", "x", "d")
    )
    client._http = httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(server))
    return client


def _fail_500() -> httpx.Response:
    return httpx.Response(
        500,
        json={
            "error": "Cannot execute",
            "exception": "com.arcadedb.exception.ConcurrentModificationException",
        },
    )


async def _commit_two_commands(client: arcadedb_client.ArcadeDBClient) -> None:
    session = await client.begin_transaction()
    await client.gremlin("addE one", session_id=session)
    await client.gremlin("addE two", session_id=session)
    await client.commit_transaction(session)


async def test_a_clean_commit_logs_nothing(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger=_LOGGER)
    server = _Server([lambda: httpx.Response(204)])

    await _commit_two_commands(_client(server))

    assert caplog.records == []


async def test_a_replayed_commit_says_what_was_replayed_and_why(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Catches the silent replay: the warning names the failure and the commands resent."""
    caplog.set_level(logging.WARNING, logger=_LOGGER)
    server = _Server([_fail_500, lambda: httpx.Response(204)])

    await _commit_two_commands(_client(server))

    (record,) = caplog.records
    text = record.getMessage()
    assert "ConcurrentModificationException" in text
    assert "2 recorded commands" in text
    assert "attempt 1 of" in text
    assert server.sessions == 2  # the replay really happened, in a second transaction
    assert [s for s, _ in server.commands].count("s2") == 2


async def test_a_commit_that_got_no_answer_is_logged_as_unknown_not_as_failed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A timeout does not say the commit failed: the server may have applied it. Replaying it then
    writes every edge again, so the log must say the outcome is unknown."""
    caplog.set_level(logging.WARNING, logger=_LOGGER)
    server = _Server([lambda: httpx.ReadTimeout("no answer"), lambda: httpx.Response(204)])

    await _commit_two_commands(_client(server))

    (record,) = caplog.records
    text = record.getMessage()
    assert "UNKNOWN" in text
    assert "ReadTimeout" in text
    assert "2 recorded commands" in text


async def test_the_last_attempt_failing_still_raises_after_logging_each_replay(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger=_LOGGER)
    server = _Server([_fail_500, _fail_500, _fail_500])

    with pytest.raises(Exception, match="ArcadeDB error 500"):
        await _commit_two_commands(_client(server))

    assert len(caplog.records) == 2  # attempts 1 and 2 are replayed; attempt 3 is the last
