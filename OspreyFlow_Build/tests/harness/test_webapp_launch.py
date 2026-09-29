"""`06_DECISIONS.md` ADR-049 Stage 2 §6 part B, item 5 — Launch. `harness/webapp.py`'s own
docstring has the full reasoning: `POST /api/launch/stream` runs `python -m harness.apply` (or, in
every test here, a small real subprocess `apply_command` substitutes for it) as a real subprocess
and streams its own real stdout — never a second progress model. `apply_command` is the same kind
of injectable seam `render_resolver`/`docker_context_resolver` already are, so this suite never
needs a real Docker daemon or a twelve-container stack to prove the plumbing; `tests/harness/
test_harness_image.py` is where the real subprocess (the real CLI, unstubbed) gets its own opt-in,
real-Docker proof."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from harness.webapp import create_app


def _fake_resolver(image: object) -> str:
    return "sha256:" + f"{abs(hash(image)):064x}"[:64]


def _client(
    config_path: Path,
    out_root: Path,
    *,
    docker_context: str = "desktop-linux",
    apply_command: list[str] | None = None,
) -> TestClient:
    app = create_app(
        config_path=config_path,
        out_root=out_root,
        render_resolver=_fake_resolver,
        docker_context_resolver=lambda: docker_context,
        apply_command=apply_command,
    )
    return TestClient(app, client=("127.0.0.1", 51000))


def _prepare(client: TestClient) -> None:
    client.put("/api/config", json={"profile": "local-lite"})
    client.post("/api/artefacts/generate")


def _events(response_text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in response_text.split("\n\n"):
        if block.startswith("data: "):
            events.append(json.loads(block[len("data: ") :]))
    return events


def test_launch_refuses_until_the_artefacts_are_confirmed(tmp_path: Path) -> None:
    client = _client(tmp_path / "osprey.yaml", tmp_path / "generated")
    _prepare(client)
    response = client.post("/api/launch/stream", json={})
    assert response.status_code == 422
    assert "Confirm the generated artefacts" in response.json()["detail"]


def test_launch_refuses_until_the_docker_target_is_confirmed(tmp_path: Path) -> None:
    client = _client(tmp_path / "osprey.yaml", tmp_path / "generated")
    _prepare(client)
    client.post("/api/artefacts/confirm")
    response = client.post("/api/launch/stream", json={})
    assert response.status_code == 422
    assert "Confirm the Docker target" in response.json()["detail"]


def test_get_launch_target_reports_the_real_docker_context(tmp_path: Path) -> None:
    client = _client(tmp_path / "osprey.yaml", tmp_path / "generated", docker_context="my-context")
    response = client.get("/api/launch/target")
    assert response.status_code == 200
    assert response.json() == {"docker_context": "my-context", "confirmed": False}


def test_confirming_the_target_is_reflected_in_a_later_read(tmp_path: Path) -> None:
    client = _client(tmp_path / "osprey.yaml", tmp_path / "generated", docker_context="my-context")
    client.post("/api/launch/target/confirm")
    assert client.get("/api/launch/target").json()["confirmed"] is True


def test_a_changed_docker_context_needs_reconfirmation(tmp_path: Path) -> None:
    """The guard's own real value: confirming once must not silently authorise Launch forever if
    the machine (or the operator's own `docker context use`) changes underneath it."""
    config_path = tmp_path / "osprey.yaml"
    out_root = tmp_path / "generated"
    current = {"value": "context-a"}
    app = create_app(
        config_path=config_path,
        out_root=out_root,
        render_resolver=_fake_resolver,
        docker_context_resolver=lambda: current["value"],
    )
    client = TestClient(app, client=("127.0.0.1", 51000))
    _prepare(client)
    client.post("/api/artefacts/confirm")
    client.post("/api/launch/target/confirm")

    current["value"] = "context-b"
    response = client.post("/api/launch/stream", json={})
    assert response.status_code == 422
    assert "Confirm the Docker target" in response.json()["detail"]


def test_launch_streams_the_real_subprocess_output_and_completes(tmp_path: Path) -> None:
    fake_apply = [
        sys.executable,
        "-c",
        "import sys\n"
        "print('apply: local-lite ready in 3s')\n"
        "print('  the Glass:   http://127.0.0.1:8080/')\n"
        "sys.exit(0)\n",
    ]
    client = _client(tmp_path / "osprey.yaml", tmp_path / "generated", apply_command=fake_apply)
    _prepare(client)
    client.post("/api/artefacts/confirm")
    client.post("/api/launch/target/confirm")

    response = client.post("/api/launch/stream", json={})
    assert response.status_code == 200
    events = _events(response.text)
    lines = [e["line"] for e in events]
    assert "apply: local-lite ready in 3s" in lines
    assert "event: complete" in response.text
    assert '"returncode": 0' in response.text


def test_launch_streams_a_nonzero_exit_verbatim(tmp_path: Path) -> None:
    fake_apply = [
        sys.executable,
        "-c",
        "import sys\n"
        "print(\"apply: FAILED at stage 'build'\")\n"
        "sys.exit(1)\n",
    ]
    client = _client(tmp_path / "osprey.yaml", tmp_path / "generated", apply_command=fake_apply)
    _prepare(client)
    client.post("/api/artefacts/confirm")
    client.post("/api/launch/target/confirm")

    response = client.post("/api/launch/stream", json={})
    assert response.status_code == 200
    lines = [e["line"] for e in _events(response.text)]
    assert "apply: FAILED at stage 'build'" in lines
    assert '"returncode": 1' in response.text


def test_launch_passes_seed_and_demo_analyst_through_to_the_real_argv(tmp_path: Path) -> None:
    """A thin argv builder, not a second implementation — proven by having the fake `apply` print
    its own real `sys.argv` back, the same way a real headless-equivalence test would."""
    fake_apply = [sys.executable, "-c", "import sys\nprint(' '.join(sys.argv[1:]))\n"]
    client = _client(tmp_path / "osprey.yaml", tmp_path / "generated", apply_command=fake_apply)
    _prepare(client)
    client.post("/api/artefacts/confirm")
    client.post("/api/launch/target/confirm")

    response = client.post(
        "/api/launch/stream", json={"seed": "hmp,fixture-corp", "demo_analyst": True}
    )
    lines = [e["line"] for e in _events(response.text)]
    argv_line = next(line for line in lines if "--profile" in line)
    assert "--seed hmp,fixture-corp" in argv_line
    assert "--demo-analyst" in argv_line
    assert "--profile local-lite" in argv_line
