"""`06_DECISIONS.md` ADR-049 Stage 2 §6 part B, item 1 — the Preflight screen's own
`GET /api/preflight/stream`. Server-Sent Events, not a polled job: `harness/webapp.py`'s own
docstring has the reasoning (every check is already a fast, synchronous function of a
`PreflightContext`; there is no job to poll for). Real `harness.preflight.ALL_CHECKS`, run against
a real rendered `deploy/generated/<profile>/` — never a stub of the engine itself."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from harness.preflight import gpu as gpu_check
from harness.webapp import create_app


def _fake_resolver(image: object) -> str:
    return "sha256:" + f"{abs(hash(image)):064x}"[:64]


def _client(config_path: Path, out_root: Path) -> TestClient:
    app = create_app(config_path=config_path, out_root=out_root, render_resolver=_fake_resolver)
    return TestClient(app, client=("127.0.0.1", 51000))


def _events(response_text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in response_text.split("\n\n"):
        if block.startswith("data: "):
            events.append(json.loads(block[len("data: ") :]))
    return events


def _generate(client: TestClient) -> None:
    response = client.post("/api/artefacts/generate")
    assert response.status_code == 200


def test_the_stream_reports_the_real_failure_when_nothing_has_been_rendered_yet(
    tmp_path: Path,
) -> None:
    """The real headless behaviour (`RenderedOutputMissing`), not an invented one — every check
    that reads the rendered compose file fails with that real message, none of them silently
    skipped."""
    client = _client(tmp_path / "osprey.yaml", tmp_path / "generated")
    response = client.get("/api/preflight/stream")
    assert response.status_code == 200
    events = _events(response.text)
    checks = {e["check"]: e for e in events}
    assert checks["ports"]["status"] == "fail"
    assert "run `python -m harness.render`" in checks["ports"]["what_is_wrong"]


def test_the_stream_reports_every_check_in_order_once_rendered(tmp_path: Path) -> None:
    config_path = tmp_path / "osprey.yaml"
    out_root = tmp_path / "generated"
    client = _client(config_path, out_root)
    client.put("/api/config", json={"profile": "local-lite"})
    _generate(client)

    response = client.get("/api/preflight/stream")
    events = _events(response.text)
    assert [e["check"] for e in events] == [
        "memory",
        "disk",
        "gpu",
        "ports",
        "container-runtime",
        "cluster-connectivity",
        "interpreter",
        "bind-address",
        "basemap",
        "duckdb-lock",
        "oidc-audience",
        # ADR-114 Amendment 41 (gate-b): last in `ALL_CHECKS`; skipped here, the deployment asks no key.
        "access-key",
    ]


def test_basemap_warns_when_a_local_provider_points_at_tiles_not_yet_built(tmp_path: Path) -> None:
    """The brief's own named warning case — a real `map:` section (via the Geospatial screen's own
    `register-provider` route) whose tiles do not exist on disk yet."""
    config_path = tmp_path / "osprey.yaml"
    out_root = tmp_path / "generated"
    client = _client(config_path, out_root)
    client.put("/api/config", json={"profile": "local-lite"})
    client.post(
        "/api/geospatial/register-provider",
        json={
            "provider_id": "osm-local-gb",
            "label": "GB",
            "pmtiles_path": str(tmp_path / "not-built-yet.pmtiles"),
        },
    )
    _generate(client)

    events = {e["check"]: e for e in _events(client.get("/api/preflight/stream").text)}
    assert events["basemap"]["status"] == "warn"
    assert "does not exist yet" in events["basemap"]["what_is_wrong"]


def _gpu_as_this_host_has_it() -> tuple[str, list[str]]:
    """What this host lets anyone read of its GPU, found by the test itself rather than from the
    check: `("none", [])` where no driver can be read (macOS, or no nvidia-smi on PATH), `("broken",
    [])` where nvidia-smi is there but answers with an error, `("read", lines)` where it names the
    driver. Read through `harness.preflight.gpu`'s own `platform`, so a stand-in host below is the
    same host to both."""
    if gpu_check.platform.system() == "Darwin":
        return "none", []
    smi = shutil.which("nvidia-smi")
    if smi is None:
        return "none", []
    done = subprocess.run(
        [smi, "--query-gpu=driver_version,name", "--format=csv,noheader"],
        capture_output=True, text=True, timeout=20, check=False,
    )
    if done.returncode != 0:
        return "broken", []
    return "read", [line.strip() for line in done.stdout.splitlines() if line]


def _assert_gpu_is_shown_as_the_host_has_it(tmp_path: Path, *, only: str | None = None) -> None:
    """Through the Preflight screen's own stream: every check (on a real host), or `only=gpu` on a
    stand-in host, whose other checks would read this machine (the memory check calls docker)."""
    config_path = tmp_path / "osprey.yaml"
    out_root = tmp_path / "generated"
    client = _client(config_path, out_root)
    client.put("/api/config", json={"profile": "local-lite"})
    _generate(client)

    stream = "/api/preflight/stream" + (f"?only={only}" if only else "")
    gpu = {e["check"]: e for e in _events(client.get(stream).text)}["gpu"]
    host, lines = _gpu_as_this_host_has_it()
    if host == "none":
        assert gpu["status"] == "skip", gpu
    elif host == "broken":
        assert gpu["status"] == "fail", gpu
    else:
        assert gpu["status"] == "pass", gpu
        assert lines and all(line in json.dumps(gpu) for line in lines), gpu


def test_gpu_is_skipped_where_none_can_be_read_and_passes_only_where_one_can(tmp_path: Path) -> None:
    """`05_DEPLOYMENT.md` §2.1's own "skipped-with-reason (never a pass)", on the real host this suite
    runs on: a skip where no GPU driver can be read (the Mac, CI's runners), a pass naming the driver
    only where one can (the test server's GPU). This case once demanded a skip everywhere and failed
    on the test server's real GPU (lane/platform-b-live 38fb7a4, ci4/live-preflight.raw.txt)."""
    _assert_gpu_is_shown_as_the_host_has_it(tmp_path)


def _stand_in_host(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, smi: str | None) -> None:
    """A Linux host as the gpu check sees it, with `smi` as its nvidia-smi (none: not on PATH)."""
    monkeypatch.setattr(gpu_check, "platform", SimpleNamespace(system=lambda: "Linux", release=lambda: "6.8"))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    if smi is not None:
        (bin_dir / "nvidia-smi").write_text(f"#!/bin/sh\n{smi}\n")
        (bin_dir / "nvidia-smi").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}/usr/bin{os.pathsep}/bin")


def test_on_a_stand_in_gpu_host_the_gpu_passes_naming_its_driver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The test server's shape, offline: an nvidia-smi that names a driver."""
    _stand_in_host(monkeypatch, tmp_path, "echo '550.54.14, NVIDIA RTX A4000'")
    assert _gpu_as_this_host_has_it() == ("read", ["550.54.14, NVIDIA RTX A4000"])
    _assert_gpu_is_shown_as_the_host_has_it(tmp_path, only="gpu")


def test_on_a_stand_in_host_without_a_readable_gpu_the_gpu_is_skipped_never_passed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CI's runners' shape: Linux, no nvidia-smi. And a driver that answers with an error fails."""
    _stand_in_host(monkeypatch, tmp_path, None)
    assert _gpu_as_this_host_has_it() == ("none", [])
    _assert_gpu_is_shown_as_the_host_has_it(tmp_path, only="gpu")


def test_on_a_stand_in_host_whose_driver_errors_the_gpu_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stand_in_host(monkeypatch, tmp_path, "echo 'NVIDIA-SMI has failed' >&2; exit 9")
    assert _gpu_as_this_host_has_it() == ("broken", [])
    _assert_gpu_is_shown_as_the_host_has_it(tmp_path, only="gpu")


def test_only_re_checks_exactly_one(tmp_path: Path) -> None:
    config_path = tmp_path / "osprey.yaml"
    out_root = tmp_path / "generated"
    client = _client(config_path, out_root)
    client.put("/api/config", json={"profile": "local-lite"})
    _generate(client)

    events = _events(client.get("/api/preflight/stream?only=memory").text)
    assert [e["check"] for e in events] == ["memory"]


def test_an_unknown_check_name_is_a_clean_422_not_a_broken_stream(tmp_path: Path) -> None:
    """Validated before the stream starts — `harness/webapp.py`'s own docstring has the reason: an
    exception raised once a `StreamingResponse` has already sent its 200 is a broken connection to
    the client, not a clean error, so an unknown check name is never let bubble that far."""
    config_path = tmp_path / "osprey.yaml"
    out_root = tmp_path / "generated"
    client = _client(config_path, out_root)
    client.put("/api/config", json={"profile": "local-lite"})
    _generate(client)

    response = client.get("/api/preflight/stream?only=not-a-real-check")
    assert response.status_code == 422
