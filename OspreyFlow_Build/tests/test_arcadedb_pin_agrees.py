"""Every place that starts an ArcadeDB names the version the renderer pins, runs our Gremlin, and
probes it with a tool the image has (ADR-101 and its Amendment 1).

What a mistake would do, as it did: the pin moved to 26.10.1 in `harness/render.py` and
`deploy/compose/dev.yaml`, and CI and the Makefile's note stayed on 25.5.1, still probing with `curl`,
which 26.10.1's image does not have, so CI's store would never report healthy and would still run
the version whose indexes lose records. Each case reads the files as they are, not a copy."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "OspreyFlow_Core"


def _pinned() -> str:
    text = (CORE / "harness" / "render.py").read_text(encoding="utf-8")
    (tag,) = set(re.findall(r'"(arcadedata/arcadedb:[^"]+)"', text))
    return tag


def _ci_services() -> list[dict[str, object]]:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    return [
        job["services"]["arcadedb"]
        for job in workflow["jobs"].values()
        if isinstance(job, dict) and "arcadedb" in (job.get("services") or {})
    ]


def test_every_arcadedb_image_named_is_the_renderers_pin() -> None:
    pinned = _pinned()
    named = {
        "deploy/compose/dev.yaml": re.findall(
            r"arcadedata/arcadedb:\S+",
            (CORE / "deploy/compose/dev.yaml").read_text(encoding="utf-8"),
        ),
        "Makefile": re.findall(
            r"arcadedata/arcadedb:\S+", (CORE / "Makefile").read_text(encoding="utf-8")
        ),
        ".github/workflows/ci.yml": [s["image"] for s in _ci_services()],
    }
    assert named[".github/workflows/ci.yml"], (
        "CI starts no ArcadeDB: the reader of ci.yml is wrong"
    )
    for where, tags in named.items():
        assert tags, f"{where} names no ArcadeDB image"
        assert {t.strip("`\"'") for t in tags} == {pinned}, (
            f"{where}: {tags} is not {pinned}"
        )


def test_every_ci_arcadedb_runs_our_gremlin_and_probes_with_wget() -> None:
    for service in _ci_services():
        env = service["env"]
        assert "-Darcadedb.gremlin.engine=groovy" in str(env["JAVA_OPTS"]).split()  # type: ignore[index]
        options = str(service["options"])
        assert "curl" not in options and "wget" in options, options
