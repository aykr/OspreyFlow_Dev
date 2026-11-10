"""`ospreyflow images push --registry` (`spec/06_DECISIONS.md` ADR-148 decision 8): every image a
`cloud-platform` render names, copied into the namespace's registry, from the render's own plan.

What a mistake would do, and the case that catches it (rule 12):
- a third-party image rebuilt or re-tagged rather than copied by its digest (the values would pin a
  digest the registry does not hold) — `test_theirs_are_copied_by_their_digest`;
- the Conduit pushed with Java on this profile (decision 12) —
  `test_ours_are_built_here_the_conduit_without_java`;
- a push to a registry the values do not pull from —
  `test_a_registry_the_render_does_not_name_is_refused`;
- a failed step followed by the rest — `test_a_failed_step_stops_the_push`.
"""

from __future__ import annotations

import pytest
import yaml
from harness.render import load_config, render
from tools.cp_policy_check import FIXTURES, _resolver

from .conftest import Rig

REGISTRY = "123456789012.dkr.ecr.eu-west-2.amazonaws.com"


@pytest.fixture
def plan(rig: Rig) -> dict[str, object]:
    text = render(load_config(FIXTURES / "production.yaml"), resolver=_resolver).artefacts[
        "images.yaml"
    ]
    folder = rig.product / "deploy" / "generated" / "cloud-platform"
    folder.mkdir(parents=True)
    (folder / "images.yaml").write_text(text, encoding="utf-8")
    loaded = yaml.safe_load(text)
    assert isinstance(loaded, dict)
    return loaded


def test_theirs_are_copied_by_their_digest(rig: Rig, plan: dict[str, object]) -> None:
    assert rig("images", "push", "--registry", REGISTRY) == 0
    copies = [
        c.argv
        for c in rig.runner.calls
        if c.argv[:4] == ["docker", "buildx", "imagetools", "create"]
    ]
    by_target = {argv[5]: argv[6] for argv in copies}
    arcadedb = f"{REGISTRY}/arcadedata/arcadedb:26.10.1"
    assert by_target[arcadedb].startswith("arcadedata/arcadedb:26.10.1@sha256:")
    # A reference given by its digest alone keeps that digest, once, and is pushed under a tag.
    litellm = next(t for t in by_target if "/berriai/litellm:" in t)
    assert by_target[litellm].count("@") == 1
    # No third-party image is ever built.
    built = [c.argv for c in rig.runner.calls if c.argv[:2] == ["docker", "build"]]
    assert not [argv for argv in built if "arcadedb" in " ".join(argv)]


def test_ours_are_built_here_the_conduit_without_java(rig: Rig, plan: dict[str, object]) -> None:
    assert rig("images", "push", "--registry", REGISTRY) == 0
    built = {
        c.argv[c.argv.index("-t") + 1].split(":")[0].rsplit("/", 1)[-1]: c
        for c in rig.runner.calls if c.argv[:2] == ["docker", "build"]
    }  # fmt: skip
    assert {"api", "workspace", "worker", "report-sync", "superset", "ner"} <= set(built)
    api = built["api"].argv
    assert api[api.index("--build-arg") + 1] == "CONDUIT_JAVA=omitted"
    assert all("--build-arg" not in c.argv for name, c in built.items() if name != "api")
    assert built["api"].cwd == rig.product
    pushed = [c.argv[2] for c in rig.runner.calls if c.argv[:2] == ["docker", "push"]]
    assert sorted(pushed) == sorted(c.argv[c.argv.index("-t") + 1] for c in built.values())


def test_a_registry_the_render_does_not_name_is_refused(rig: Rig, plan: dict[str, object]) -> None:
    assert rig("images", "push", "--registry", "other.example.org") != 0
    assert rig.runner.calls == []


def test_a_failed_step_stops_the_push(rig: Rig, plan: dict[str, object]) -> None:
    rig.runner.fail["push"] = 1
    assert rig("images", "push", "--registry", REGISTRY) == 1
    pushes = [c for c in rig.runner.calls if c.argv[:2] == ["docker", "push"]]
    assert len(pushes) == 1
    assert rig.runner.calls[-1].argv[:2] == ["docker", "push"]


def test_a_dry_run_runs_nothing(
    rig: Rig, plan: dict[str, object], capsys: pytest.CaptureFixture[str]
) -> None:
    assert rig("images", "push", "--registry", REGISTRY, "--dry-run") == 0
    assert rig.runner.calls == []
    assert "would build" in capsys.readouterr().out


def test_no_render_is_refused_in_words(rig: Rig, capsys: pytest.CaptureFixture[str]) -> None:
    assert rig("images", "push", "--registry", REGISTRY) != 0
    out = capsys.readouterr()
    assert "render the cloud-platform profile first" in out.out + out.err


def test_the_plan_names_every_image_the_values_run(plan: dict[str, object], rig: Rig) -> None:
    values = yaml.safe_load(
        render(load_config(FIXTURES / "production.yaml"), resolver=_resolver).artefacts[
            "values.yaml"
        ]
    )
    run = {
        c["image"].split("@")[0].split(":sha256-")[0]
        for pod in [*values["workloads"], *values["jobs"]]
        for c in [pod, *pod.get("initContainers", [])]
    }
    planned = {str(i["target"]).split(":sha256-")[0] for i in plan["images"]}  # type: ignore[attr-defined]
    assert run == planned
