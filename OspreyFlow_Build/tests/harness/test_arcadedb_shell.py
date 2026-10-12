"""The backup, the restore and the comparison reach ArcadeDB with a tool its pinned image has.

Found taking the owner's backup before the B2e replacement (12 October 2026): ArcadeDB 26.10.1
(ADR-101) ships no `curl` — the renderer's healthcheck already says so and moved to busybox `wget` —
but `harness.backup`, `harness.restore` and `harness.compare` still ran `curl` inside the container,
so the graph could be neither backed up nor restored. Every test passed, because each faked the
command and the fake accepted `curl`. The fake here refuses it, as the real image does
(`sh: curl: not found`, exit 127).

Worse, `compare.total_records` counted any failure as "no such database", so with `curl` gone the
restore's emptiness refusal answered "empty" for a full store.

What a mistake would do, and the case that catches it:
- a graph-store call through a tool the image lacks —
  `test_every_graph_store_call_runs_in_the_pinned_image`;
- the password or a body broken by the shell — `test_the_request_survives_the_shell`;
- a store that cannot be asked counted as empty — `test_a_store_that_cannot_be_asked_is_not_empty`;
- a store without the database not counted as empty — `test_a_store_without_the_database_is_empty`.
"""

from __future__ import annotations

import base64
import json
import shlex
import subprocess
from pathlib import Path
from typing import Any

import pytest
from harness import backup, compare, restore

PASSWORD = "p'a$s w\"d"  # quotes, a dollar and a space: what a shell would mangle


@pytest.fixture
def deployment(tmp_path: Path) -> Path:
    out = tmp_path / "deploy" / "local-lite"
    out.mkdir(parents=True)
    (out / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (out / "deployment.env").write_text(f"OSPREY_ARCADEDB_PASSWORD={PASSWORD}\n", encoding="utf-8")
    return out / "compose.yaml"


class Image:
    """The ArcadeDB 26.10.1 container as far as these calls reach it: busybox `sh` and `wget`, no
    `curl`; a server that holds `databases` and answers its own HTTP API."""

    def __init__(self, databases: list[str], *, answers: bool = True) -> None:
        self.databases = databases
        self.answers = answers
        self.requests: list[dict[str, Any]] = []

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if "sh" not in command:
            return subprocess.CompletedProcess(command, 0, stdout="restore completed\n", stderr="")
        script = command[command.index("-c") + 1]
        out = ""
        for part in script.split(";"):
            words = shlex.split(part.split("||")[0])
            if not words:
                continue
            if words[0] == "curl":
                return subprocess.CompletedProcess(command, 127, stdout="", stderr="sh: curl: not found")
            if words[0] == "wget":
                code, body = self._wget(words)
                if code and "||" not in part:
                    return subprocess.CompletedProcess(command, code, stdout="", stderr=body)
                out += "" if code else body
            elif words[:2] == ["cd", "/home/arcadedb"] or words[0] in ("rm", "./bin/restore.sh"):
                out += "restore completed\n" if "./bin/restore.sh" in part else ""
        return subprocess.CompletedProcess(command, 0, stdout=out, stderr="")

    def _wget(self, words: list[str]) -> tuple[int, str]:
        headers = [words[i + 1] for i, w in enumerate(words) if w == "--header"]
        auth = next(h for h in headers if h.startswith("Authorization: Basic "))
        user, _, password = base64.b64decode(auth.split()[-1]).decode().partition(":")
        if (user, password) != ("root", PASSWORD) or not self.answers:
            return 1, "wget: server returned error: HTTP/1.1 401 Unauthorized"
        body = words[words.index("--post-data") + 1] if "--post-data" in words else None
        url = words[-1]
        self.requests.append({"url": url, "body": json.loads(body) if body else None})
        path = url.removeprefix("http://127.0.0.1:2480")
        if path == "/api/v1/databases":
            return 0, json.dumps({"result": self.databases})
        if path.startswith("/api/v1/server"):
            return 0, json.dumps({"result": "ok"})
        database = path.rsplit("/", 1)[-1]
        if database not in self.databases:
            return 1, "wget: server returned error: HTTP/1.1 400 Bad Request"
        assert body is not None
        sql = json.loads(body)["command"]
        if sql == "BACKUP DATABASE":
            return 0, json.dumps({"result": [{"backupFile": "ospreyflow-backup.zip"}]})
        if "schema:types" in sql:
            return 0, json.dumps({"result": [{"name": "mx_Person", "type": "vertex"}]})
        return 0, json.dumps({"result": [{"n": 494}]})


def test_every_graph_store_call_runs_in_the_pinned_image(
    deployment: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    image = Image(["ospreyflow"])
    monkeypatch.setattr(subprocess, "run", image)
    backup.backup_graph_store(deployment, tmp_path / "set" / "graph.zip", database="ospreyflow")
    assert compare.server_is_ready(deployment)
    assert compare.total_records(deployment, "ospreyflow") == 494
    archive = tmp_path / "graph.zip"
    archive.write_bytes(b"zip")
    restore.restore_graph_store(deployment, archive, database="ospreyflow")
    asked = [r["body"]["command"] if r["body"] else r["url"] for r in image.requests]
    assert "BACKUP DATABASE" in asked
    assert "drop database ospreyflow" in asked and "open database ospreyflow" in asked


def test_the_request_survives_the_shell(
    deployment: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image = Image(["ospreyflow"])
    monkeypatch.setattr(subprocess, "run", image)
    sql = "select from `mx_Person` where name = 'O''Brien'"
    compare._query(deployment, "ospreyflow", sql)
    assert image.requests[-1]["body"] == {"language": "sql", "command": sql}


def test_a_store_that_cannot_be_asked_is_not_empty(
    deployment: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(subprocess, "run", Image(["ospreyflow"], answers=False))
    with pytest.raises(backup.BackupFailed):
        compare.total_records(deployment, "ospreyflow")
    with pytest.raises(backup.BackupFailed):
        restore.graph_store_is_empty(deployment, database="ospreyflow")


def test_a_store_without_the_database_is_empty(
    deployment: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(subprocess, "run", Image([]))
    assert compare.total_records(deployment, "ospreyflow") == 0
    assert restore.graph_store_is_empty(deployment, database="ospreyflow")
