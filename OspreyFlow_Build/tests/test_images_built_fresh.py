"""Every image OspreyFlow builds starts from a freshly pulled base (build order step 14, the owner's
answer of 3 November 2026 to open question 21).

Without `--pull`, Docker builds on whatever base image it cached last, so a base's security fixes
never arrive and the trivy gates go red on images nobody changed (step 12b found curl, expat,
pcre2 and brotli this way). Each place that builds an image is held to it here:

- the Makefiles' `docker build` lines — `test_every_docker_build_in_the_makefiles_pulls`;
- the release workflow's `buildx build` lines — `test_every_release_build_pulls`;
- `ospreyflow start --build` (`scripts/refresh.py`) — `test_start_build_pulls_the_bases`;
- `harness.apply`'s build stage — `test_apply_pulls_the_bases_when_it_builds`;
- `tools/release_local.py` — `test_the_local_release_pulls_the_bases`.

And the Glass's own base is a maintained nginx line, not 1.27, which reached end of life in April
2025, nor 1.28, whose images stopped in March 2026 — `test_the_glass_is_served_by_a_maintained_nginx`. The trivy the gates use is the same
version locally and in both workflows — `test_every_trivy_scan_in_the_workflows_names_its_version`.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from tools.layout import BUILD, CORE

ROOT = BUILD.parent
MAKEFILES = (CORE / "Makefile", BUILD / "Makefile")
WORKFLOWS = (
    ROOT / ".github" / "workflows" / "ci.yml",
    CORE / ".github" / "workflows" / "release.yml",
)
TRIVY_VERSION = "v0.76.1"
#: The oldest nginx line still maintained, as of 3 November 2026: 1.30 stable (1.30.6, images of 29
#: October). The owner's answer named 1.28, offered as the stable line; it is not — its last image is of
#: March 2026 and trivy finds five HIGH fixes it never received — so the maintained stable line the
#: answer asked for is 1.30. Raise this when the stable line moves on.
OLDEST_MAINTAINED_NGINX = (1, 30)


def docker_builds(text: str) -> list[str]:
    """Each `docker build` / `docker buildx build` command, its continuation lines joined."""
    joined = re.sub(r"\\\n\s*", " ", text)
    return [
        " ".join(line.split())
        for line in joined.splitlines()
        if re.search(r"docker (buildx )?build\b", line)
        and not line.strip().startswith("#")
    ]


def test_the_build_finder_sees_a_build_and_its_continuation() -> None:
    found = docker_builds(
        "x:\n\tdocker build -f a \\\n\t  --pull -t b .\n# docker build in a comment\n"
    )
    assert found == ["docker build -f a --pull -t b ."]


@pytest.mark.parametrize("makefile", MAKEFILES, ids=lambda p: p.parent.name)
def test_every_docker_build_in_the_makefiles_pulls(makefile: Path) -> None:
    builds = docker_builds(makefile.read_text(encoding="utf-8"))
    assert builds, "the check reads at least one build"
    assert [b for b in builds if "--pull" not in b.split()] == []


def test_every_release_build_pulls() -> None:
    builds = docker_builds(WORKFLOWS[1].read_text(encoding="utf-8"))
    assert len(builds) >= 2
    assert [b for b in builds if "--pull" not in b.split()] == []


def test_start_build_pulls_the_bases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts import refresh

    calls: list[list[str]] = []
    monkeypatch.setattr(
        refresh,
        "files_up_to_date",
        lambda _root: {
            "theme_changed": False,
            "proxy_changed": False,
            "routing_changed": False,
        },
    )
    monkeypatch.setattr(refresh, "_deployment_dir", lambda _root: tmp_path)
    (tmp_path / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    refresh.refresh(
        tmp_path, run=lambda argv: calls.append(list(argv)), register=lambda _a: 0
    )
    builds = [c for c in calls if "build" in c]
    assert builds and all("--pull" in c for c in builds)


def test_apply_pulls_the_bases_when_it_builds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from harness import apply
    from harness.preflight.result import passed

    calls: list[list[str]] = []

    def stop_after_the_build(args: list[str], *, stage: str, **_kwargs: object) -> str:
        calls.append(list(args))
        if stage == "build":
            raise apply.ApplyFailed(stage, "stopped here by the test")
        return ""

    monkeypatch.setattr(apply, "_run", stop_after_the_build)
    monkeypatch.setattr(apply, "answer_localhost_with_loopback", lambda: None)
    monkeypatch.setattr(
        apply, "ALL_CHECKS", [SimpleNamespace(check=lambda _c: passed("ports"))]
    )
    config = tmp_path / "osprey.yaml"
    config.write_text(yaml.safe_dump({}), encoding="utf-8")
    assert (
        apply.main(["--config", str(config), "--out-root", str(tmp_path / "generated")])
        == 1
    )
    builds = [c for c in calls if "build" in c]
    assert builds, "apply reached its build stage"
    assert all("--pull" in c for c in builds)


def test_the_local_release_pulls_the_bases(monkeypatch: pytest.MonkeyPatch) -> None:
    from tools import release_local

    calls: list[list[str]] = []
    monkeypatch.setattr(
        release_local, "_run", lambda cmd, *a, **k: calls.append(list(cmd))
    )
    release_local.build_and_scan("0123456")
    builds = [c for c in calls if c[:2] == ["docker", "build"]]
    assert builds and all("--pull" in c for c in builds)


def test_the_glass_is_served_by_a_maintained_nginx() -> None:
    dockerfile = (CORE / "apps" / "workspace" / "Dockerfile").read_text(
        encoding="utf-8"
    )
    ((major, minor),) = {
        (int(a), int(b))
        for a, b in re.findall(r"^FROM nginx:(\d+)\.(\d+)", dockerfile, re.MULTILINE)
    }
    assert (major, minor) >= OLDEST_MAINTAINED_NGINX
    assert minor % 2 == 0, "a stable line (even minor), not mainline"


def test_every_trivy_scan_in_the_workflows_names_its_version() -> None:
    for workflow in WORKFLOWS:
        steps = [
            step
            for job in yaml.safe_load(workflow.read_text(encoding="utf-8"))[
                "jobs"
            ].values()
            for step in job.get("steps", [])
            if str(step.get("uses", "")).startswith("aquasecurity/trivy-action")
        ]
        assert steps, f"{workflow.name} has a trivy scan"
        assert {str(s.get("with", {}).get("version")) for s in steps} == {
            TRIVY_VERSION
        }, workflow.name


#: Every image we build on a Debian base, by the Dockerfile that builds it.
DEBIAN_BASED = (
    CORE / "services" / "api" / "Dockerfile",
    CORE / "services" / "ingest" / "Dockerfile",
    CORE / "services" / "worker" / "Dockerfile",
    CORE / "services" / "report_sync" / "Dockerfile",
    CORE / "services" / "ner" / "Dockerfile",
    CORE / "deploy" / "superset" / "Dockerfile",
)


@pytest.mark.parametrize("dockerfile", DEBIAN_BASED, ids=lambda p: p.parent.name)
def test_every_debian_image_takes_the_distributions_fixes(dockerfile: Path) -> None:
    """Red before 5 November: the NER image alone had no `apt-get upgrade` in its final stage, so
    when Debian fixed CVE-2026-109518 in apt (3.0.4) before `python:3.12-slim` was rebuilt, the
    release's trivy gate stopped v0.4.11 on that image while every other one had the fix. A fresh
    base (`--pull`) is not enough on its own; the final stage must upgrade what the base holds."""
    text = dockerfile.read_text(encoding="utf-8")
    final_stage = re.split(r"^FROM ", text, flags=re.MULTILINE)[-1]
    assert re.search(r"apt-get update\b.*apt-get upgrade -y", final_stage), dockerfile
