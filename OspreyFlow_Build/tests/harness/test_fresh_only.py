"""v0.6.0 is installed fresh (the owner's ruling of 15 November 2026, v0.6.0's item `rf`): no path
moves a deployment of an earlier release onto it, and each says so in the same words before anything
is changed (`harness.fresh_only`).

What a mistake would do, and the case that catches it (rule 12):
- `ospreyflow update` moving a v0.5.2 deployment onto v0.6.0:
  `test_update_refuses_to_move_an_earlier_deployment_onto_v060_and_changes_nothing`;
- an install over a v0.5.2 deployment re-rendering it as v0.6.0:
  `test_an_install_over_an_earlier_deployment_is_refused_before_anything_is_written`;
- the cloud-platform runbook upgrading a namespace that holds v0.5.2:
  `test_the_cloud_platform_runbook_refuses_a_namespace_holding_an_earlier_release`;
- any of them refusing what is allowed (a fresh install, a move within v0.6):
  `..._allows_...` beside each.

Each runs the real path: `update.apply_update` with `test_update_apply`'s stand-in host,
`apply.main` with its stages stood in as `test_apply_search_rebuild` does, and the runbook's own
rendered block in bash with `kubectl` and `helm` stood in on PATH."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from harness import apply, fresh_only
from harness.preflight.result import passed
from harness.render import render
from tools.cp_policy_check import FIXTURES, _resolver

from schemas.deployment import OspreyConfig, generated_folder
from tests.harness.test_update_apply import _Host, _update

CORE = Path(__file__).resolve().parents[3] / "OspreyFlow_Core"
WORDS = "v0.6.0 is installed fresh;"


# --- the rule ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("installed", "installing", "refused"),
    [
        ("v0.5.2", "v0.6.0", True),
        ("v0.4.1", "v0.6.0", True),
        (None, "v0.6.0", True),  # rendered before releases were stamped
        ("dev-abc1234", "v0.6.0", True),  # a checkout before VERSION, so earlier
        ("v0.5.2", "v0.6.0-dev", True),  # v0.6.0's own code, unreleased
        ("v0.6.0", "v0.6.1", False),
        ("v0.6.0-dev", "v0.6.0", False),
        ("v0.5.1", "v0.5.2", False),  # before v0.6.0 nothing changes
    ],
)
def test_the_rule(installed: str | None, installing: str, refused: bool) -> None:
    why = fresh_only.refusal(installed, installing)
    assert (why is not None) is refused, why
    if refused:
        assert why is not None and why.startswith(WORDS) and "unchanged" in why


# --- ospreyflow update ---------------------------------------------------------------------------


def test_update_refuses_to_move_an_earlier_deployment_onto_v060_and_changes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _Host(tmp_path, version="v0.5.2")
    fake.release_tag = "v0.6.0"
    before = {p.name: p.read_bytes() for p in fake.directory.iterdir() if p.is_file()}
    assert _update(fake) == 1
    said = capsys.readouterr().err
    assert WORDS in said and "v0.5.2" in said, said
    assert [a for a in fake.actions if not a.startswith("find ")] == [], (
        "the release looked up, and nothing pulled, backed up or started"
    )
    assert {p.name: p.read_bytes() for p in fake.directory.iterdir() if p.is_file()} == before


def test_update_allows_a_move_within_v06(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _Host(tmp_path, version="v0.6.0")
    fake.release_tag = "v0.6.1"
    _update(fake)
    assert WORDS not in capsys.readouterr().err


# --- an install over an existing deployment ------------------------------------------------------


def _install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, installed: str | None
) -> tuple[int, list[str], Path]:
    import harness.render as rendering

    calls: list[str] = []

    def run(args: list[str], *, stage: str, **_kwargs: object) -> str:
        calls.append(stage)
        return ""

    monkeypatch.setattr(rendering, "release_version", lambda _c: "v0.6.0")
    monkeypatch.setattr(apply, "_run", run)
    monkeypatch.setattr(apply, "answer_localhost_with_loopback", lambda: None)
    monkeypatch.setattr(apply, "ALL_CHECKS", [SimpleNamespace(check=lambda _c: passed("ports"))])
    monkeypatch.setattr(apply, "uploads_ready", lambda _f: "ready")
    monkeypatch.setattr(apply, "stores_moved", lambda _f, _h: SimpleNamespace(services=[]))
    monkeypatch.setattr(apply, "wait_for_health", lambda _f, **_k: {"api": "healthy"})
    monkeypatch.setattr(apply, "move_model_keys_into_gateway", lambda _f: "none")
    monkeypatch.setattr(apply, "_wait_for_models", lambda _f, _c: "none")
    monkeypatch.setattr(apply, "grant_service_account_roles", lambda **_k: None)
    tmp_path.mkdir(parents=True, exist_ok=True)
    config_path = tmp_path / "osprey.yaml"
    config_path.write_text("components:\n  search: postgres-fulltext\n", encoding="utf-8")
    out_root = tmp_path / "generated"
    out_dir = out_root / generated_folder(
        OspreyConfig.model_validate(yaml.safe_load(config_path.read_text()))
    )
    if installed is not None:
        out_dir.mkdir(parents=True)
        (out_dir / "deployment.env").write_text(
            f"OSPREY_RELEASE_VERSION={installed}\nOSPREY_POSTGRES_PASSWORD=kept-secret\n"
        )
    argv = [
        "--config",
        str(config_path),
        "--out-root",
        str(out_root),
        "--no-build",
        "--skip-verify",
    ]
    return apply.main(argv), calls, out_dir


def test_an_install_over_an_earlier_deployment_is_refused_before_anything_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, calls, out_dir = _install(tmp_path, monkeypatch, installed="v0.5.2")
    assert code != 0
    said = capsys.readouterr()
    assert WORDS in said.out + said.err, said
    assert calls == [], "nothing built or started"
    assert (out_dir / "deployment.env").read_text() == (
        "OSPREY_RELEASE_VERSION=v0.5.2\nOSPREY_POSTGRES_PASSWORD=kept-secret\n"
    ), "the deployment's own files untouched"
    assert sorted(p.name for p in out_dir.iterdir()) == ["deployment.env"]


def test_an_install_allows_a_fresh_folder_and_a_v06_deployment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _calls, _out = _install(tmp_path / "fresh", monkeypatch, installed=None)
    assert code == 0
    code, _calls, _out = _install(tmp_path / "again", monkeypatch, installed="v0.6.0")
    assert code == 0
    assert WORDS not in capsys.readouterr().err


# --- the cloud-platform runbook ------------------------------------------------------------------


def _install_md(monkeypatch: pytest.MonkeyPatch) -> str:
    """INSTALL.md as v0.6.0 renders it (the render's version stood in)."""
    import harness.render as rendering

    monkeypatch.setattr(rendering, "release_version", lambda _c: "v0.6.0")
    raw = yaml.safe_load((FIXTURES / "poc.yaml").read_text(encoding="utf-8"))
    return render(OspreyConfig.model_validate(raw), resolver=_resolver).artefacts["INSTALL.md"]


def _the_check(text: str) -> str:
    """INSTALL.md's own block that holds the check, as an operator runs it."""
    from harness.cloud_platform.runbooks import command_blocks

    [block] = [b for b in command_blocks(text, on_the_platform=True) if "harness.fresh_only" in b]
    return block


def _run_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, release: bool, version: str
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fakes = {
        # `helm status` succeeds only where the namespace holds the release.
        "helm": f'[ "$1" = status ] && exit {0 if release else 1}; exit 0\n',
        # The ConfigMap's OSPREY_RELEASE_VERSION, as `-o jsonpath` prints it (nothing, no newline).
        "kubectl": f'case "$*" in *ospreyflow-env*) printf %s "{version}";; esac\n',
    }
    for name, body in fakes.items():
        path = bin_dir / name
        path.write_text("#!/bin/bash\n" + body)
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "NS": "ospreyflow-poc",
        "RELEASE": "ospreyflow",
        "PY": str(CORE / ".venv/bin/python"),
        "PYTHONPATH": ".:packages",
    }
    return subprocess.run(["bash", "-c", _the_check(_install_md(monkeypatch))], cwd=CORE, env=env,
                          capture_output=True, text=True, check=False)  # fmt: skip


def test_the_cloud_platform_runbook_refuses_a_namespace_holding_an_earlier_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    done = _run_check(tmp_path, monkeypatch, release=True, version="v0.5.2")
    assert done.returncode != 0
    assert WORDS in done.stderr and "v0.5.2" in done.stderr, done.stderr
    text = _install_md(monkeypatch)
    assert text.index("harness.fresh_only") < text.index("## 2."), "before anything is changed"


@pytest.mark.parametrize(("release", "version"), [(False, ""), (True, "v0.6.0")])
def test_the_cloud_platform_runbook_allows_a_fresh_namespace_and_a_v06_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, release: bool, version: str
) -> None:
    done = _run_check(tmp_path, monkeypatch, release=release, version=version)
    assert done.returncode == 0, done.stderr
