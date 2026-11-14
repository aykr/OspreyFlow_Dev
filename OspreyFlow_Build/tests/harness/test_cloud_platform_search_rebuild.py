"""The CARRIES row "an upgrade must rebuild when the mapping changes" on the cloud-platform profile
(ADR-150 decision 4): INSTALL.md's step 5, run in order on a fresh install and on every upgrade,
makes the search index again from the graph once the Conduit and the worker are rolled out, so the
indexer is never left on an index made for another mapping (an earlier version's, with no
fingerprint) or on a fresh domain's empty one. The rebuild is the search-rebuild Job, bounded (five
minutes to start, 30 to finish) and deleted and named when it does not succeed, failing the step.

Step 5's block run as written against stand-ins for helm and kubectl (the seed's own, which answer
the rebuild Job), never a cluster."""

from __future__ import annotations

import subprocess
from pathlib import Path

from harness.cloud_platform.runbooks import command_blocks

from tests.harness.test_cloud_platform_render import _artefacts, _config, _values
from tests.harness.test_cloud_platform_seed import _KUBECTL


def _step_5(fixture: str) -> str:
    text = _artefacts(_config(fixture))["INSTALL.md"]
    step = text[text.index("## 5. The deployment") : text.index("## 6.")]
    [block] = command_blocks(step, on_the_platform=True)
    return block


def _run(tmp_path: Path, fixture: str, scenario: str) -> tuple[int, str, list[str]]:
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "kubectl").write_text(_KUBECTL)
    (bin_ / "helm").write_text('#!/bin/sh\necho "helm $*" >> "$CALLS"\n')
    (bin_ / "sleep").write_text("#!/bin/sh\n")
    for tool in ("kubectl", "helm", "sleep"):
        (bin_ / tool).chmod(0o755)
    calls = tmp_path / "calls"
    calls.write_text("")
    env = {"PATH": f"{bin_}:/usr/bin:/bin", "CALLS": str(calls), "SCENARIO": scenario,
           "NS": "ospreyflow-poc", "RELEASE": "ospreyflow", "CHART": "chart",
           "FOLDER": str(tmp_path)}  # fmt: skip
    done = subprocess.run(
        ["bash", "-c", "set -e\n" + _step_5(fixture)],
        capture_output=True, text=True, timeout=60, env=env, check=False,
    )  # fmt: skip
    return done.returncode, done.stdout + done.stderr, calls.read_text().splitlines()


def test_step_5_rebuilds_the_index_after_the_rollouts(tmp_path: Path) -> None:
    """The poc's runbook (the shape that renders one); its values search with OpenSearch."""
    fixture = "poc"
    assert "searchIndex" in _values(_config(fixture))
    code, said, calls = _run(tmp_path, fixture, "ok")
    assert code == 0, said
    created = [
        i for i, c in enumerate(calls) if "create job --from=cronjob/ospreyflow-search-rebuild" in c
    ]
    rolled = [i for i, c in enumerate(calls) if "rollout status" in c]
    assert len(created) == 1 and rolled and max(rolled) < created[0], calls
    assert calls[0].startswith("helm upgrade --install")


def test_a_rebuild_that_fails_fails_step_5_naming_the_job(tmp_path: Path) -> None:
    code, said, calls = _run(tmp_path, "poc", "rebuild-fails")
    assert code != 0
    assert "search-rebuild-" in said and "failed" in said and "deleted" in said
    assert any("delete job search-rebuild-" in c for c in calls)
