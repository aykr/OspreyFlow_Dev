"""An ArcadeDB Raft cluster is written through its leader, saying `eventual` —
`spec/05_DEPLOYMENT.md` §3b, `spec/06_DECISIONS.md` ADR-101 Amendment 2.

Measured on three `arcadedata/arcadedb:26.10.1` nodes, 14 October 2026: with the Groovy engine
(ADR-101), a Gremlin command is *analysed* before it runs — on a follower to decide whether to
forward it, on the leader unless the request's read consistency is `eventual` — and the analysis
evaluates the script without its parameters. So a command with parameters fails
(`MissingPropertyException`) on every node, and a script that iterates itself ran twice. Sent to the
leader with `X-ArcadeDB-Read-Consistency: eventual`, the same commands bound their parameters and
wrote once.

The fake below refuses what the real cluster refused: a follower refuses a Gremlin command with
parameters, and so does the leader unless the request says `eventual`; a standalone server's
`/api/v1/cluster` answers nothing.
"""

from __future__ import annotations

import json

import httpx
import pytest

# Imported as a module, not by name: this test talks to a fake HTTP transport and needs no live
# service, and `tools/test_file_coverage_check.py` treats an imported `ArcadeDBClient` as one.
from adapters.graph_arcadedb import client as arcadedb_client

_HEADER = "X-ArcadeDB-Read-Consistency"


class _Cluster:
    """`svc` is the Service in front of every node; `arcadedb-N` are the nodes themselves."""

    def __init__(self, leader: str | None = "arcadedb-0", *, standalone: bool = False) -> None:
        self.leader = leader
        self.standalone = standalone
        self.cluster_asks = 0
        self.sent: list[tuple[str, str, str | None]] = []  # (host, path, consistency header)
        self.unreachable: set[str] = set()

    def _refused(self) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": "Cannot execute command",
                "exception": "com.arcadedb.exception.CommandParsingException",
                "detail": "groovy.lang.MissingPropertyException: No such property: x",
            },
        )

    def __call__(self, request: httpx.Request) -> httpx.Response:
        host, path = request.url.host, request.url.path
        if host in self.unreachable:
            raise httpx.ConnectError("connection refused", request=request)
        if path == "/api/v1/cluster":
            self.cluster_asks += 1
            if self.standalone:
                return httpx.Response(204)
            if self.leader is None:
                return httpx.Response(200, json={"implementation": "raft", "leaderId": None})
            return httpx.Response(
                200,
                json={"implementation": "raft", "leaderHttpAddress": f"{self.leader}:2480"},
            )
        consistency = request.headers.get(_HEADER)
        self.sent.append((host, path, consistency))
        if path.startswith("/api/v1/command/"):
            body = json.loads(request.content)
            bound = body.get("language") == "gremlin" and body.get("params")
            on_leader = self.standalone or host == self.leader
            if bound and not (on_leader and (self.standalone or consistency == "eventual")):
                return self._refused()
            return httpx.Response(200, json={"result": [{"result": 42}]})
        if path.startswith("/api/v1/begin/"):
            return httpx.Response(204, headers={"arcadedb-session-id": "s1"})
        return httpx.Response(200, json={"result": ["d"]})


def _client(cluster: _Cluster, *, ha: bool) -> arcadedb_client.ArcadeDBClient:
    config = arcadedb_client.ArcadeDBConfig("svc", 2480, "root", "x", "d", ha=ha)
    return arcadedb_client.ArcadeDBClient(config, transport=httpx.MockTransport(cluster))


async def test_a_cluster_command_goes_to_the_leader_saying_eventual() -> None:
    cluster = _Cluster(leader="arcadedb-2")
    client = _client(cluster, ha=True)
    rows = await client.gremlin("g.inject(x)", params={"x": 42})
    assert rows == [{"result": 42}]
    assert cluster.sent == [("arcadedb-2", "/api/v1/command/d", "eventual")]
    await client.aclose()


async def test_every_kind_of_request_goes_to_the_leader() -> None:
    cluster = _Cluster(leader="arcadedb-1")
    client = _client(cluster, ha=True)
    await client.create_database_if_absent()
    session = await client.begin_transaction()
    await client.gremlin("g.inject(x)", params={"x": 1}, session_id=session)
    await client.commit_transaction(session)
    assert {host for host, _, _ in cluster.sent} == {"arcadedb-1"}
    assert {said for _, _, said in cluster.sent} == {"eventual"}
    await client.aclose()


async def test_a_standalone_server_is_used_as_configured_and_never_asked_for_a_leader() -> None:
    cluster = _Cluster(standalone=True)
    client = _client(cluster, ha=False)
    await client.gremlin("g.inject(x)", params={"x": 42})
    assert cluster.sent == [("svc", "/api/v1/command/d", None)]
    assert cluster.cluster_asks == 0
    await client.aclose()


async def test_a_new_leader_is_followed_once_the_old_answer_is_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cluster = _Cluster(leader="arcadedb-0")
    client = _client(cluster, ha=True)
    await client.gremlin("g.inject(x)", params={"x": 1})
    cluster.leader = "arcadedb-2"
    monkeypatch.setattr(arcadedb_client, "_LEADER_TTL_SECONDS", 0.0)
    await client.gremlin("g.inject(x)", params={"x": 1})
    assert [host for host, _, _ in cluster.sent] == ["arcadedb-0", "arcadedb-2"]
    await client.aclose()


async def test_the_leader_is_trusted_for_a_moment_not_asked_for_on_every_request() -> None:
    cluster = _Cluster(leader="arcadedb-0")
    client = _client(cluster, ha=True)
    for _ in range(5):
        await client.gremlin("g.inject(x)", params={"x": 1})
    assert cluster.cluster_asks == 1
    await client.aclose()


async def test_a_leader_that_cannot_be_reached_is_asked_for_again_on_the_next_request() -> None:
    cluster = _Cluster(leader="arcadedb-0")
    client = _client(cluster, ha=True)
    await client.gremlin("g.inject(x)", params={"x": 1})
    cluster.unreachable.add("arcadedb-0")
    cluster.leader = "arcadedb-1"
    with pytest.raises(httpx.ConnectError):
        await client.gremlin("g.inject(x)", params={"x": 1})
    await client.gremlin("g.inject(x)", params={"x": 1})
    assert cluster.sent[-1][0] == "arcadedb-1"
    await client.aclose()


async def test_a_cluster_with_no_leader_is_said_in_words_and_nothing_is_sent() -> None:
    cluster = _Cluster(leader=None)
    client = _client(cluster, ha=True)
    with pytest.raises(arcadedb_client.ArcadeDBError, match="no leader"):
        await client.gremlin("g.inject(x)", params={"x": 1})
    assert cluster.sent == []
    await client.aclose()


def test_the_cluster_setting_is_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARCADEDB_HA", "true")
    assert arcadedb_client.ArcadeDBConfig.from_env("d").ha is True
    monkeypatch.delenv("ARCADEDB_HA")
    assert arcadedb_client.ArcadeDBConfig.from_env("d").ha is False
