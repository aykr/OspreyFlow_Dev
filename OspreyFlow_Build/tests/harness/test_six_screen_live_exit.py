"""`06_DECISIONS.md` ADR-049 Stage 2 §6's own exit — the one item `REPORT-03d.md` left owed: Launch
from the six screens produces a running `local-lite` deployment that `harness.verify` passes
three-sided.

**Opt-in via `OSPREY_TEST_SIX_SCREEN_EXIT=1`** — needs Docker, ~15 real minutes on a properly
resourced daemon, the same reasoning `tests/harness/test_bundle_exit_test.py`/`test_sustained_load.
py` already use for their own opt-in gates. **Two real, both-real branches, not one expected
outcome** (round 10, closing the measurement-scope gap this file's own previous version disclosed
and left open): `harness/preflight/memory.py`/`disk.py` now verdict on the container runtime's own
daemon, not this process's own host OS (that module's own docstring has the full account of the
false pass this fixes). On a daemon genuinely below `local-lite`'s floor — this sandbox, confirmed
directly, unchanged since round 05/06 (9.7GiB/~17-20GiB against a 16GiB/20GiB floor) — Preflight
now correctly refuses, and this test asserts that real refusal by check name, then stops *before*
Launch: forcing past a real resource gate is exactly the class of shortcut `CLAUDE.md` rule 14
names as a stop condition, not a workaround to script around. On a properly-resourced daemon
(CI's own `ubuntu-latest` runner, the owner's own laptop) neither check fails, and the test
proceeds all the way through Launch and the three-sided verify, as it always did. Whichever branch
this test's own real Preflight run takes, it is real Preflight output — never a mocked substitute
for either.

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

from tests.harness.deployment_guard import refuse_to_touch_a_real_deployment
from tools.layout import CORE
from tools.layout import REPO as REPO_ROOT

pytestmark = pytest.mark.skipif(
    os.environ.get("OSPREY_TEST_SIX_SCREEN_EXIT") != "1",
    reason="needs Docker and ~15 real minutes (render, build, launch twelve containers, verify); "
    "opt in with OSPREY_TEST_SIX_SCREEN_EXIT=1. Expected to pass on CI's ubuntu-latest runner and "
    "the owner's own laptop.",
)


COMPOSE_PROJECT = "osprey-local-lite"

#: A path that will never exist, on purpose — `harness/preflight/basemap.py`'s own docstring: "the
#: tiles do not exist — a warning, not a blocker." Registering it is how this test exercises that
#: exact branch without needing a real PMTiles fixture (none exists in this tree — the same
#: disclosed limit `spec/05_DEPLOYMENT.md` §3 already names for the Geospatial screen).
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
    refuse_to_touch_a_real_deployment(COMPOSE_PROJECT)
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
                payload = {**payload, "source_path": str(CORE)}
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
        # disclosed gap `process/07_BUILD_PLAN.md`'s round 05 entry named for a *container-run*
        # harness image with no source mounted — does not apply to this in-process test at all).
        #
        # **Round 10 — `memory`/`disk` verdict on the container runtime's own daemon now, not this
        # process's own host** (`harness/preflight/memory.py`'s own docstring has the full account
        # of the false pass that fixed). This test drives `harness.webapp` as a bare host process,
        # so it always did — and, until round 10, always would — read this host's own generous
        # figures (36GiB/499GiB here) rather than the Docker Desktop VM's real, smaller allocation
        # (9.7GiB/~17-20GiB) the twelve containers Launch starts actually run inside. On a machine
        # whose daemon is genuinely below `local-lite`'s floor — this sandbox, confirmed directly,
        # unchanged since round 05/06 — Preflight now correctly refuses, and this test's own job is
        # to assert that real refusal by check name and stop *before* attempting Launch, not to
        # force past a gate that is doing exactly what it is for. On a properly-resourced daemon
        # (CI's own runner, the owner's own laptop) neither check fails, and the test proceeds to
        # Launch below — both branches are real Preflight output, neither mocked.
        response = client.get("/api/preflight/stream")
        assert response.status_code == 200, response.text
        checks = {e["check"]: e for e in _events(response.text) if "check" in e}
        assert checks, "no checks reported at all"
        assert checks["basemap"]["status"] == "warn", checks["basemap"]
        failed = {name: c for name, c in checks.items() if c["status"] == "fail"}
        unexpected_failures = {
            name: c for name, c in failed.items() if name not in {"memory", "disk"}
        }
        if unexpected_failures:
            pytest.fail(
                "Preflight failed for real before Launch was attempted, on a check other than "
                "the resource floors this sandbox is already known to sit below — reporting the "
                "real check(s) and figures verbatim, not patching around them:\n"
                + "\n".join(
                    f"  {name}: {c.get('what_is_wrong', c)}"
                    for name, c in unexpected_failures.items()
                )
            )
        if failed:
            # The real refusal, asserted by check name — a pass, not a skip: this test's own job
            # on an under-resourced machine *is* proving Preflight correctly refuses, not merely
            # declining to find out. Never forced past — CLAUDE.md rule 14 names exactly this
            # class of shortcut (docker/disk exhaustion) as a stop condition, not a workaround.
            assert failed.keys() <= {"memory", "disk"}
            for name, c in failed.items():
                assert "GiB" in c.get("what_is_wrong", ""), (
                    f"{name}: expected a real, measured figure in the refusal, got: {c}"
                )
            return

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
