"""The cached-upgrade trap, closed everywhere an image is built (v0.6.0, the owner's word of 15
November 2026; `harness/upgrade_stamp.py` has the finding and the choice).

Each image's last distribution upgrade (`apt-get upgrade`, `apk upgrade`) is one layer whose text
never changes, so a builder holding a cached copy kept the fixes of the day it was made: the
Superset image kept 192 HIGH CVEs Debian had fixed. Every upgrading Dockerfile now keys that
layer on `OSPREY_UPGRADE_STAMP`, and every place that builds passes the day's date. What would
fail, and the case that catches it:

- a Dockerfile whose upgrade does not take the stamp, or a new upgrading Dockerfile without it —
  `test_every_upgrading_dockerfile_keys_its_upgrade_on_the_stamp`;
- a Makefile build without it — `test_every_makefile_build_passes_the_day_s_stamp`;
- a CI or release workflow build without it — `test_every_workflow_build_passes_the_day_s_stamp`
  (the workflows' change is the owner's to apply, `process/lanes/rules/v060-upgrade-stamp/
  workflows_upgrade_stamp.diff`: until it is, this reads them with that diff applied to a copy);
- `ospreyflow start --build`, the harness's install and apply, or the local release building
  without it — the three `..._passes_the_stamp` cases below;
- `ospreyflow images push` (the cloud-platform install's step 3) building one of ours without it, or
  its own copy of the day drifting from `harness.upgrade_stamp`'s —
  `test_images_push_passes_the_stamp` and `test_the_command_s_stamp_is_harness_s`.

Red first: `process/lanes/rules/v060-upgrade-stamp/plants.py`.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from harness.upgrade_stamp import UPGRADE_STAMP_ARG, build_args, upgrade_stamp
from tools.layout import BUILD, CORE

ROOT = BUILD.parent
MAKEFILES = (CORE / "Makefile", BUILD / "Makefile")
WORKFLOWS = (
    ROOT / ".github" / "workflows" / "ci.yml",
    CORE / ".github" / "workflows" / "release.yml",
)
WORKFLOWS_DIFF = BUILD / "process/lanes/rules/v060-upgrade-stamp/workflows_upgrade_stamp.diff"
UPGRADE = re.compile(
    r"\b(apt-get (dist-)?upgrade|apk upgrade|dnf upgrade|yum (update|upgrade)"
    r"|microdnf (update|upgrade))\b"
)
#: The images that upgrade their distribution, by the folder of their Dockerfile (the owner's list).
#: `pages` joined it with its own Dockerfile (ADR-152 R1, slice PL3): a Node image on Debian that takes the
#: day's fixes like the others. `litellm`, the model gateway's own image on Wolfi, takes `apk
#: upgrade`.
EXPECTED = {"api", "ingest", "workspace", "harness", "laurium", "ner", "worker", "report_sync",
            "superset", "pages", "litellm"}  # fmt: skip
TODAY = upgrade_stamp()
STAMPED = f"{UPGRADE_STAMP_ARG}={TODAY}"


def _dockerfiles() -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files", "--", "*Dockerfile", "*Dockerfile.*"], cwd=CORE, check=True,
        capture_output=True, text=True,
    ).stdout.split()  # fmt: skip
    return [CORE / p for p in listed]


def _upgrading() -> list[Path]:
    return [p for p in _dockerfiles() if UPGRADE.search(p.read_text(encoding="utf-8"))]


def docker_builds(text: str) -> list[str]:
    """Each `docker build` / `docker buildx build` command, its continuation lines joined (as
    `test_images_built_fresh.docker_builds`)."""
    joined = re.sub(r"\\\n\s*", " ", text)
    return [
        " ".join(line.split())
        for line in joined.splitlines()
        if re.search(r"docker (buildx )?build\b", line) and not line.strip().startswith("#")
    ]


def stamp_problems(dockerfile_text: str) -> list[str]:
    """Why a Dockerfile's upgrade is not keyed on the stamp, if it is not: the arg declared in the
    final stage before the upgrade step, and named in that step."""
    final = re.split(r"^FROM ", dockerfile_text, flags=re.MULTILINE)[-1]
    steps = re.sub(r"\\\n\s*", " ", final).splitlines()
    problems = []
    upgrade_at = next(
        (i for i, s in enumerate(steps) if s.startswith("RUN ") and UPGRADE.search(s)), None
    )
    if upgrade_at is None:
        return ["no upgrade step in the final stage"]
    declared = [i for i, s in enumerate(steps) if re.match(rf"ARG {UPGRADE_STAMP_ARG}\b", s)]
    if not declared or min(declared) > upgrade_at:
        problems.append(f"ARG {UPGRADE_STAMP_ARG} is not declared before the upgrade")
    if (
        f"${{{UPGRADE_STAMP_ARG}" not in steps[upgrade_at]
        and f"${UPGRADE_STAMP_ARG}" not in steps[upgrade_at]
    ):
        problems.append("the upgrade step does not name the stamp")
    return problems


def test_the_stamp_is_the_utc_day() -> None:
    late = datetime(2026, 11, 15, 23, 59, tzinfo=UTC)
    assert upgrade_stamp(late) == "2026-11-15"
    assert upgrade_stamp(datetime(2026, 11, 16, 0, 0, tzinfo=UTC)) == "2026-11-16"
    assert build_args(late) == ["--build-arg", "OSPREY_UPGRADE_STAMP=2026-11-15"]


def test_the_dockerfile_finder_sees_every_upgrading_image() -> None:
    assert {p.parent.name for p in _upgrading()} == EXPECTED


@pytest.mark.parametrize("dockerfile", _upgrading(), ids=lambda p: p.parent.name)
def test_every_upgrading_dockerfile_keys_its_upgrade_on_the_stamp(dockerfile: Path) -> None:
    assert stamp_problems(dockerfile.read_text(encoding="utf-8")) == [], dockerfile


def test_a_dockerfile_without_the_stamp_is_named() -> None:
    """The check's own red: an upgrade with no stamp, or one declared after it."""
    bare = "FROM debian\nRUN apt-get update && apt-get upgrade -y\n"
    assert stamp_problems(bare) == [
        "ARG OSPREY_UPGRADE_STAMP is not declared before the upgrade",
        "the upgrade step does not name the stamp",
    ]
    late = "FROM debian\nRUN apt-get update && apt-get upgrade -y\nARG OSPREY_UPGRADE_STAMP=\n"
    assert "ARG OSPREY_UPGRADE_STAMP is not declared before the upgrade" in stamp_problems(late)


@pytest.mark.parametrize("makefile", MAKEFILES, ids=lambda p: p.parent.name)
def test_every_makefile_build_passes_the_day_s_stamp(makefile: Path) -> None:
    text = makefile.read_text(encoding="utf-8")
    assert re.search(r"^UPGRADE_STAMP \?= \$\(shell date -u \+%F\)$", text, re.MULTILINE)
    builds = docker_builds(text)
    assert builds
    assert [b for b in builds if "--build-arg OSPREY_UPGRADE_STAMP=$(UPGRADE_STAMP)" not in b] == []


def _workflow_texts(tmp_path: Path) -> dict[str, str]:
    """The workflows as the repository has them, or, until the owner applies the lane's diff, with
    that diff applied to a copy (so the diff itself is what is checked)."""
    texts = {p.name: p.read_text(encoding="utf-8") for p in WORKFLOWS}
    if all(UPGRADE_STAMP_ARG in t for t in texts.values()):
        return texts
    for p in WORKFLOWS:
        copy = tmp_path / p.relative_to(ROOT)
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(p, copy)
    subprocess.run(["git", "apply", str(WORKFLOWS_DIFF)], cwd=tmp_path, check=True)
    return {p.name: (tmp_path / p.relative_to(ROOT)).read_text(encoding="utf-8") for p in WORKFLOWS}


def test_every_workflow_build_passes_the_day_s_stamp(tmp_path: Path) -> None:
    for name, text in _workflow_texts(tmp_path).items():
        yaml.safe_load(text)  # still a workflow
        builds = docker_builds(text)
        assert len(builds) >= 2, name
        missing = [
            b for b in builds if f'--build-arg {UPGRADE_STAMP_ARG}="$(date -u +%F)"' not in b
        ]
        assert missing == [], (name, missing)


def test_start_build_passes_the_stamp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import refresh

    calls: list[list[str]] = []
    monkeypatch.setattr(refresh, "files_up_to_date", lambda _root: {
        "theme_changed": False, "proxy_changed": False, "routing_changed": False,
    })  # fmt: skip
    monkeypatch.setattr(refresh, "_deployment_dir", lambda _root: tmp_path)
    (tmp_path / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    refresh.refresh(tmp_path, run=lambda argv: calls.append(list(argv)), register=lambda _a: 0)
    builds = [c for c in calls if "build" in c]
    assert builds and all(STAMPED in c for c in builds), builds


def test_apply_passes_the_stamp_when_it_builds(
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
    monkeypatch.setattr(apply, "ALL_CHECKS", [SimpleNamespace(check=lambda _c: passed("ports"))])
    config = tmp_path / "osprey.yaml"
    config.write_text(yaml.safe_dump({}), encoding="utf-8")
    assert apply.main(["--config", str(config), "--out-root", str(tmp_path / "generated")]) == 1
    builds = [c for c in calls if "build" in c]
    assert builds and all(STAMPED in c for c in builds), builds


def test_the_local_release_passes_the_stamp(monkeypatch: pytest.MonkeyPatch) -> None:
    from tools import release_local

    calls: list[list[str]] = []
    monkeypatch.setattr(release_local, "_run", lambda cmd, *a, **k: calls.append(list(cmd)))
    release_local.build_and_scan("0123456")
    builds = [c for c in calls if c[:3] == ["docker", "buildx", "build"]]  # the product workflow's scan build
    assert builds and all(STAMPED in c for c in builds), builds


# ---- `ospreyflow images push` (the cloud-platform install's step 3, and R1's) -----------------------------
# Found preparing v0.6.0's package step (platform-b, 15 November 2026): the one builder the client's
# cloud-platform install runs passed only the profile's build args, so its upgrade layer was the cached one.


def test_images_push_passes_the_stamp() -> None:
    """Each image of ours it builds takes the day's stamp, beside the profile's own build args; a
    third-party image is copied by digest, never built, so it takes none."""
    from ospreyflow import images

    plan = {"images": [
        {"target": "reg/ospreyflow/api:abc", "dockerfile": "services/api/Dockerfile", "context": ".",
         "build_args": {"CONDUIT_JAVA": "omitted"}},
        {"target": "reg/ospreyflow/laurium:abc", "dockerfile": "Dockerfile", "context": "services/laurium"},
        {"target": "reg/valkey:8.0", "source": "valkey/valkey@sha256:" + "0" * 64},
    ]}  # fmt: skip
    commands = [command for _words, command in images.steps(plan)]
    builds = [c for c in commands if c[:2] == ["docker", "build"]]
    assert len(builds) == 2 and all(STAMPED in c for c in builds), builds
    assert "CONDUIT_JAVA=omitted" in builds[0]
    assert not any(STAMPED in c for c in commands if c[:2] != ["docker", "build"])


@pytest.mark.parametrize("now", [
    datetime(2026, 11, 15, 12, 0, tzinfo=UTC),
    datetime(2026, 11, 15, 23, 59, 59, tzinfo=UTC),
    # A builder in another timezone, already the 16th locally: the stamp is still the UTC day.
    datetime.fromisoformat("2026-11-16T01:30:00+05:00"),
])  # fmt: skip
def test_the_command_s_stamp_is_harness_s(now: datetime) -> None:
    """The command depends on nothing but the standard library and PyYAML (ADR-114 decision 3), so it
    computes the stamp itself: held here to one value with `harness.upgrade_stamp`."""
    from ospreyflow import images

    assert images.UPGRADE_STAMP_ARG == UPGRADE_STAMP_ARG
    assert images.upgrade_stamp(now) == upgrade_stamp(now)
