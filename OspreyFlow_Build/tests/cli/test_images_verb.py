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

from pathlib import Path

import pytest
import yaml
from harness.render import load_config, render
from tools.cp_policy_check import FIXTURES, _resolver

from .conftest import FakeRunner, Rig

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
    # Report sync and Superset are not on the profile until their step after P10 (ADR-148
    # Amendment 8), so their images are not built for it.
    assert {"api", "workspace", "worker", "ner"} <= set(built)
    assert not {"report-sync", "superset"} & set(built)
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


# ---- what a real registry refuses ---------------------------------------------------------------


class RegistryRefuses(FakeRunner):
    """ECR as it refuses (CLAUDE.md rule 15: a fake models the dependency's refusals): a push or a
    copy into a repository that does not exist ("name unknown": ECR never makes one on push; the
    namespace's Terraform does, `ecr.tf`), and anything at all before the person has signed in
    ("no basic auth credentials")."""

    def __init__(self, repositories: set[str], *, signed_in: bool = True) -> None:
        super().__init__()
        self.repositories, self.signed_in, self.refused = repositories, signed_in, []

    def __call__(self, argv, *, env=None, cwd=None):  # type: ignore[no-untyped-def]
        code = super().__call__(argv, env=env, cwd=cwd)
        target = None
        if argv[:2] == ["docker", "push"]:
            target = argv[2]
        elif argv[:4] == ["docker", "buildx", "imagetools", "create"]:
            target = argv[argv.index("--tag") + 1]
        if target is None:
            return code
        repository = target.removeprefix(REGISTRY + "/").split("@")[0].rsplit(":", 1)[0]
        if not self.signed_in or repository not in self.repositories:
            self.refused.append(target)
            return 1
        return code


def _ecr_repositories() -> set[str]:
    import re

    text = render(load_config(FIXTURES / "production.yaml"), resolver=_resolver).artefacts[
        "terraform/ecr.tf"
    ]
    return set(re.findall(r'^\s+"([a-z0-9._/-]+)",$', text, re.M))


def test_every_image_goes_to_a_repository_the_terraform_makes(
    rig: Rig, plan: dict[str, object]
) -> None:
    registry = RegistryRefuses(_ecr_repositories())
    rig.runner = registry
    assert rig("images", "push", "--registry", REGISTRY) == 0, registry.refused
    assert registry.refused == []
    assert len([c for c in registry.calls if c.argv[:2] != ["docker", "build"]]) == len(
        plan["images"]  # type: ignore[arg-type]
    )


def test_a_registry_not_signed_in_to_stops_the_push_at_once_saying_so(
    rig: Rig, plan: dict[str, object], capsys: pytest.CaptureFixture[str]
) -> None:
    registry = RegistryRefuses(_ecr_repositories(), signed_in=False)
    rig.runner = registry
    assert rig("images", "push", "--registry", REGISTRY) == 1
    assert len(registry.refused) == 1
    assert "sign in to it first" in capsys.readouterr().out


def test_ours_are_built_for_the_platform_s_nodes(rig: Rig, plan: dict[str, object]) -> None:
    """The platform's nodes are amd64: an image of ours built on an arm64 Mac without a platform
    is arm64, and never starts there (`exec format error`)."""
    assert rig("images", "push", "--registry", REGISTRY) == 0
    builds = [c.argv for c in rig.runner.calls if c.argv[:2] == ["docker", "build"]]
    assert builds and all(
        argv[argv.index("--platform") + 1] == "linux/amd64"
        for argv in builds
        if "--platform" in argv
    )
    assert all("--platform" in argv for argv in builds)
    rig.runner.calls.clear()
    assert rig("images", "push", "--registry", REGISTRY, "--platform", "linux/arm64") == 0
    builds = [c.argv for c in rig.runner.calls if c.argv[:2] == ["docker", "build"]]
    assert all(argv[argv.index("--platform") + 1] == "linux/arm64" for argv in builds)


def test_no_plan_is_refused_with_a_command_that_renders_it(tmp_path: Path) -> None:
    """The refusal's words name a command that works as given, from OspreyFlow_Core (the
    orchestrator's D2c finding 3: `python -m harness.render` alone fails without the packages on
    its path)."""
    import shlex
    import subprocess

    from ospreyflow.home import CommandRefused
    from ospreyflow.images import read_plan

    with pytest.raises(CommandRefused) as refused:
        read_plan(tmp_path)
    words = str(refused.value)
    command = words.split("from OspreyFlow_Core: ", 1)[1]
    environment, *argv = shlex.split(command)
    name, _, value = environment.partition("=")
    core = Path(__file__).resolve().parents[3] / "OspreyFlow_Core"
    done = subprocess.run(
        [*argv, "--help"], cwd=core, env={"PATH": "/usr/bin:/bin", name: value},
        capture_output=True, text=True, check=False, timeout=120,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr
    assert "usage: python -m harness.render" in done.stdout


def test_a_third_party_image_named_by_tag_alone_is_never_copied(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    """The D2c guide's finding (b): a plan rendered with the image's registry out of reach names a
    third-party image by its tag, and a copy by tag pins nothing the values can name. The push
    refuses before any step runs, saying how to render it by digest."""
    text = render(
        load_config(FIXTURES / "production.yaml"), resolver=lambda ref: None, allow_unpinned=True
    ).artefacts["images.yaml"]
    folder = rig.product / "deploy" / "generated" / "cloud-platform"
    folder.mkdir(parents=True)
    (folder / "images.yaml").write_text(text, encoding="utf-8")
    assert rig("images", "push", "--registry", REGISTRY) != 0
    assert not rig.runner.calls
    out = capsys.readouterr()
    assert "by its tag alone" in out.out + out.err
