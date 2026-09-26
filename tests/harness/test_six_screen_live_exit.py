"""`06_DECISIONS.md` ADR-049 Stage 2 §6's own exit — the one item `REPORT-03d.md` left owed: Launch
from the six screens produces a running `local-lite` deployment that `harness.verify` passes
three-sided.

**Opt-in via `OSPREY_TEST_SIX_SCREEN_EXIT=1`** — needs Docker, ~15 real minutes, the same reasoning
`tests/harness/test_bundle_exit_test.py`/`test_sustained_load.py` already use for their own opt-in
gates. **Expected to pass on CI's `ubuntu-latest` runner and the owner's own laptop** — not
necessarily on every sandbox: `harness/preflight/memory.py`'s own `context.memory_probe()` and
`disk.py`'s own free-space read measure *this process's own host OS*, not the Docker daemon's — a
real, disclosed measurement-scope gap (out of this round's own scope to fix) that means Preflight
can pass on a machine whose Docker Desktop VM is nonetheless too small for the real stack. Where
that happens, this test reports the real failure at whichever stage it actually occurs — Preflight,
or later, during Launch's own real `docker compose up`/health-wait — never a mocked substitute for
either.

**Drives the six real HTTP routes, not `harness.apply` in-process** (unlike
`tests/harness/test_sustained_load.py`'s own `apply_main` call) — `POST /api/launch/stream` with no
injected `apply_command` is what makes this the live proof `06_DECISIONS.md` asks for: the real,
unstubbed `python -m harness.apply` subprocess `harness/webapp.py`'s own `_launch_events` spawns,
run via a `fastapi.testclient.TestClient`. `TestClient` executes the real ASGI route and the real
subprocess synchronously (no HTTP is faked, only the transport is in-process) — the same idiom this
whole test suite already uses for `harness.webapp`'s other routes; a second, genuinely separate OS
process was judged not to add real coverage over this for the six-screen flow itself, matching how
`test_launch_streams_the_real_subprocess_output_and_completes` already proves a real subprocess
runs synchronously under `TestClient`."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from harness.webapp import create_app

pytestmark = pytest.mark.skipif(
    os.environ.get("OSPREY_TEST_SIX_SCREEN_EXIT") != "1",
    reason="needs Docker and ~15 real minutes (render, build, launch twelve containers, verify); "
    "opt in with OSPREY_TEST_SIX_SCREEN_EXIT=1. Expected to pass on CI's ubuntu-latest runner and "
    "the owner's own laptop.",
)

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PROJECT = "osprey-local-lite"

#: A path that will never exist, on purpose — `harness/preflight/basemap.py`'s own docstring: "the
#: tiles do not exist — a warning, not a blocker." Registering it is how this test exercises that
#: exact branch without needing a real PMTiles fixture (none exists in this tree — the same
#: disclosed limit `docs/05_DEPLOYMENT.md` §3 already names for the Geospatial screen).
NONEXISTENT_PMTILES_PATH = "/tmp/does-not-exist/no-such-basemap.pmtiles"


def _teardown_local_lite_deployment(compose_file: Path) -> None:
    if compose_file.is_file():
        subprocess.run(
            [
                "docker",
                "compose",
                "--env-file",
                str(compose_file.parent / "deployment.env"),
                "-f",
                str(compose_file),
                "down",
                "-v",
                "--remove-orphans",
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
    # Belt and braces, by project name — `compose_file` may not exist yet if Launch never reached
    # the render stage (a Preflight-stage stop, say), but a prior partial `up` still could have.
    subprocess.run(
        ["docker", "compose", "-p", COMPOSE_PROJECT, "down", "-v", "--remove-orphans"],
        capture_output=True,
        text=True,
        timeout=180,
    )


def _events(response_text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in response_text.split("\n\n"):
        if block.startswith("data: "):
            events.append(json.loads(block[len("data: ") :]))
    return events


def test_launch_from_the_six_screens_reaches_a_verified_local_lite_deployment(
    tmp_path: Path,
) -> None:
    if shutil.which("docker") is None:
        pytest.skip("no docker binary on PATH")

    config_path = tmp_path / "osprey.yaml"
    # Not `tmp_path` for `out_root` — found running this test for real, not assumed from
    # `test_sustained_load.py`'s own comment naming the same choice: `harness/render.py`'s own
    # `BUILD_CONTEXT_FROM_OUTPUT_DIR` ("../../../") assumes the rendered output sits at
    # `--out-root`'s own default depth beneath this repository (`deploy/generated/<profile>/`), so
    # a `tmp_path` render's owned-image build fails with `lstat .../apps: no such file or
    # directory` — confirmed directly, the first time this test ran. Real, gitignored generated
    # output (`.gitignore`: `/deploy/generated/`), not a fixture; `config_path` has no such
    # constraint and stays under `tmp_path` so this test never touches the repository's own
    # committed `osprey.yaml`.
    out_root = REPO_ROOT / "deploy" / "generated"
    compose_file = out_root / "local-lite" / "compose.yaml"

    app = create_app(config_path=config_path, out_root=out_root, mode="setup")
    client = TestClient(app, client=("127.0.0.1", 51000))

    try:
        # 1. Profile.
        response = client.put("/api/config", json={"profile": "local-lite"})
        assert response.status_code == 200, response.text
        config = response.json()

        # 2. Components, Models, Governance — accept the defaults, through each screen's own real
        # save route (merge semantics: PUTting a section back unchanged still proves the round
        # trip, `07_BUILD_PLAN.md`'s own §6 exit table cites this shape for each screen already).
        # Round 07: `components.source_path` is declared here too — this test represents a
        # developer's own checkout, not a customer install with nothing to build from, and no
        # screen renders this new field (it is a headless/CLI concept, `harness/apply.py`'s own
        # `--build`), so it is set directly the same way a developer would hand-edit `osprey.yaml`.
        for section in ("components", "models", "governance"):
            payload = config[section]
            if section == "components":
                payload = {**payload, "source_path": str(REPO_ROOT)}
            response = client.put("/api/config", json={section: payload})
            assert response.status_code == 200, response.text

        # 3. Geospatial — register a local provider at a path that does not exist, so `basemap`
        # warns rather than passes clean, and Preflight's own "warning, not blocker" behaviour is
        # exercised for real rather than assumed from the module's own docstring.
        response = client.post(
            "/api/geospatial/register-provider",
            json={
                "provider_id": "six-screen-exit-test",
                "label": "Six-screen exit test provider",
                "pmtiles_path": NONEXISTENT_PMTILES_PATH,
                "make_default": True,
            },
        )
        assert response.status_code == 200, response.text

        # 4. Generate, then confirm, the artefacts.
        response = client.post("/api/artefacts/generate")
        assert response.status_code == 200, response.text
        response = client.post("/api/artefacts/confirm")
        assert response.status_code == 200, response.text

        # 5. Preflight — real ALL_CHECKS, over SSE. The basemap warning must not block; nothing
        # else may fail here (this rendered, freshly-generated tree has a real Dockerfile for
        # every owned service, so `harness/render.py`'s own `MissingDockerfileError` — the real,
        # disclosed gap `docs/07_BUILD_PLAN.md`'s round 05 entry named for a *container-run*
        # harness image with no source mounted — does not apply to this in-process test at all).
        response = client.get("/api/preflight/stream")
        assert response.status_code == 200, response.text
        checks = {e["check"]: e for e in _events(response.text) if "check" in e}
        assert checks, "no checks reported at all"
        assert checks["basemap"]["status"] == "warn", checks["basemap"]
        failed = {name: c for name, c in checks.items() if c["status"] == "fail"}
        if failed:
            pytest.fail(
                "Preflight failed for real before Launch was attempted — reporting the real "
                "check(s) and figures verbatim, not patching around them:\n"
                + "\n".join(
                    f"  {name}: {c.get('what_is_wrong', c)}" for name, c in failed.items()
                )
            )

        # 6. Confirm the Docker target — the real, resolved context, never faked.
        response = client.post("/api/launch/target/confirm")
        assert response.status_code == 200, response.text

        # 7. Launch — no injected `apply_command`: the real, unstubbed `python -m harness.apply`,
        # which itself runs Preflight again (`harness/apply.py`'s own stage 2), builds the three
        # owned images, brings up all twelve containers, waits for health, and runs the three-sided
        # `harness.verify` as its own last stage before reporting success. `"build": True` is
        # round 07's own developer-path opt-in (`components.source_path`'s default is pull mode,
        # which this real checkout is not exercising here — the harness image itself is).
        response = client.post("/api/launch/stream", json={"build": True})
        assert response.status_code == 200, response.text
        lines = [e["line"] for e in _events(response.text) if "line" in e]
        output = "\n".join(lines)

        if "apply: FAILED at stage 'preflight'" in output:
            pytest.fail(
                "Preflight failed inside the real apply subprocess (a second, independent check "
                "from step 5 above, run against the daemon at build/up time) — the real output, "
                "not patched around:\n" + output
            )

        assert "event: complete" in response.text, output
        assert '"returncode": 0' in response.text, (
            "Launch's real subprocess did not exit 0 — the real output, not patched around:\n"
            + output
        )
        assert "service(s) healthy" in output, output
        assert "3/3 assertions green" in output, (
            "harness.verify did not pass three-sided — the real output, not patched around:\n"
            + output
        )
    finally:
        _teardown_local_lite_deployment(compose_file)


def test_admin_access_control_holds_against_a_second_console_mode_instance(tmp_path: Path) -> None:
    """The mode boundary (`06_DECISIONS.md` amendment 22) proven against a second, independently
    constructed app instance in `console` mode — not a re-read of `tests/harness/
    test_webapp_mode.py`'s own already-passing cases, but the same boundary exercised once more
    here because this file is the one place the six screens and the post-launch console are
    proven in the same round, per the brief this test was built against."""
    console_app = create_app(
        config_path=tmp_path / "osprey.yaml", out_root=tmp_path / "generated", mode="console"
    )
    console_client = TestClient(console_app, client=("127.0.0.1", 51001))

    # No token at all: 404, never 401 — R2's own "the endpoint's existence cannot be inferred."
    response = console_client.get("/admin")
    assert response.status_code == 404, response.text

    # A setup-mode instance's own /admin is unconditionally 404 too (the other half of the
    # boundary) — checked here against a fresh instance, not assumed from the fixture above, which
    # never reaches this route at all in its own successful path.
    setup_app = create_app(
        config_path=tmp_path / "osprey-setup.yaml",
        out_root=tmp_path / "generated-setup",
        mode="setup",
    )
    setup_client = TestClient(setup_app, client=("127.0.0.1", 51002))
    response = setup_client.get("/admin")
    assert response.status_code == 404, response.text

    # And the setup-mode instance's own six-screen routes are unreachable from the console
    # instance — the boundary holds in both directions.
    response = console_client.put("/api/config", json={"profile": "local-lite"})
    assert response.status_code == 404, response.text
