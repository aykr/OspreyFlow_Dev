"""The CARRIES row "an upgrade must rebuild when the mapping changes" at install (ADR-150 decision
4): `ospreyflow install` (`harness.apply`) on a deployment that searches with OpenSearch makes
the index again from the graph once its services are up, before it seeds or verifies, so the
indexer is never left on an index made for another mapping (an earlier version's, with no
fingerprint) or on a fresh domain's empty one; and it refuses in words when the rebuild fails. A
deployment that renders no OpenSearch has nothing to rebuild.

Drives the real `harness.apply`, standing in for the preflight checks, the compose commands and
the steps that need a running deployment (health, the gateway's keys, the models, Keycloak's
grants), so nothing reaches Docker."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from harness import apply
from harness.preflight.result import passed

REBUILD = ["exec", "-T", "api", "python", "-m", "scripts.rebuild_search_index"]


def _install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, search: str, fails: bool = False):  # type: ignore[no-untyped-def]
    calls: list[list[str]] = []

    def run(args: list[str], *, stage: str, **_kwargs: object) -> str:
        tail = args[args.index("-f") + 2 :] if "-f" in args else args
        calls.append([stage, *tail])
        if fails and tail == REBUILD:
            raise apply.ApplyFailed(stage, "search index: the graph could not be read")
        return ""

    monkeypatch.setattr(apply, "_run", run)
    monkeypatch.setattr(apply, "answer_localhost_with_loopback", lambda: None)
    monkeypatch.setattr(apply, "ALL_CHECKS", [SimpleNamespace(check=lambda _c: passed("ports"))])
    monkeypatch.setattr(apply, "uploads_ready", lambda _f: "ready")
    monkeypatch.setattr(apply, "stores_moved", lambda _f, _h: SimpleNamespace(services=[]))
    monkeypatch.setattr(apply, "wait_for_health", lambda _f, **_k: {"api": "healthy"})
    monkeypatch.setattr(apply, "move_model_keys_into_gateway", lambda _f: "none")
    monkeypatch.setattr(apply, "_wait_for_models", lambda _f, _c: "none")
    monkeypatch.setattr(apply, "grant_service_account_roles", lambda **_k: None)
    config = tmp_path / "osprey.yaml"
    config.write_text(f"components:\n  search: {search}\n", encoding="utf-8")
    argv = ["--config", str(config), "--out-root", str(tmp_path / "generated"), "--no-build",
            "--skip-verify"]  # fmt: skip
    code = apply.main(argv)
    return code, calls


def _stage(calls: list[list[str]], first: str) -> int:
    return next(i for i, c in enumerate(calls) if c[1:2] == [first])


def test_an_install_that_searches_with_opensearch_rebuilds_the_index_once_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, calls = _install(tmp_path, monkeypatch, search="opensearch")
    assert code == 0
    rebuilt = [i for i, c in enumerate(calls) if c[1:] == REBUILD]
    assert len(rebuilt) == 1, calls
    assert _stage(calls, "up") < rebuilt[0], "after the services are up"


def test_an_install_without_opensearch_rebuilds_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, calls = _install(tmp_path, monkeypatch, search="postgres-fulltext")
    assert code == 0
    assert not any(c[1:] == REBUILD for c in calls)


def test_a_rebuild_that_fails_fails_the_install_in_words(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _calls = _install(tmp_path, monkeypatch, search="opensearch", fails=True)
    assert code != 0
    said = capsys.readouterr()
    assert "search index" in said.out + said.err
