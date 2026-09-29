"""`06_DECISIONS.md` ADR-049 Stage 2 §6 part B, item 1 — the Preflight screen's own
`GET /api/preflight/stream`. Server-Sent Events, not a polled job: `harness/webapp.py`'s own
docstring has the reasoning (every check is already a fast, synchronous function of a
`PreflightContext`; there is no job to poll for). Real `harness.preflight.ALL_CHECKS`, run against
a real rendered `deploy/generated/<profile>/` — never a stub of the engine itself."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
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


def test_gpu_is_skipped_on_this_platform_never_shown_as_a_pass(tmp_path: Path) -> None:
    """`05_DEPLOYMENT.md` §2.1's own "skipped-with-reason (never a pass)" — the brief's named
    skipped case, on the real platform this suite actually runs on."""
    config_path = tmp_path / "osprey.yaml"
    out_root = tmp_path / "generated"
    client = _client(config_path, out_root)
    client.put("/api/config", json={"profile": "local-lite"})
    _generate(client)

    events = {e["check"]: e for e in _events(client.get("/api/preflight/stream").text)}
    assert events["gpu"]["status"] == "skip"
    assert events["gpu"]["status"] != "pass"


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
