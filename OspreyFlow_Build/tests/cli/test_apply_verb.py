"""`ospreyflow apply` (`06_DECISIONS.md` ADR-137 decision 1 and 2): a changed `osprey.yaml` applied
to the installed deployment, by the harness's own `--reapply`, and nothing else; `ospreyflow models
key` for a provider not yet rendered names it; `deployment.env` is `600` after the verb, `models
key` and `models remove-key`.

What a mistake would do, and the case that catches it (rule 12):
- the verb rendering by some second route, or running an install step (accounts, first admin, demo
  packs, a rebuild) — `test_apply_runs_the_harness_reapply_and_nothing_else`;
- a changed setting applied to no deployment — `test_nothing_installed_is_refused_in_words`;
- a failure reported as success — `test_a_refused_apply_is_reported`;
- the verb, end to end, leaving the secrets file readable by others or the key out of it —
  `test_after_the_verb_the_key_is_kept_and_deployment_env_is_600` (the real harness, in process,
  with Docker stood in for);
- the admin told to run `install` over a running deployment —
  `test_models_key_for_a_provider_not_yet_rendered_names_apply`;
- `models key` or `remove-key` leaving the file as loose as it found it —
  `test_models_key_and_remove_key_leave_deployment_env_600`.
"""

from __future__ import annotations

import stat
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
import yaml

from .conftest import BASE_CONFIG, Rig

GEMINI_KEY = "AIza-gemini-NEVER-PRINTED-0123456789"
GEMINI = {
    "local_only": False,
    "sendable_handling_codes": ["P"],
    "providers": [
        {"name": "gemini", "label": "Gemini", "roles": {"extraction": "gemini-2.5-flash"}}
    ],
    "defaults": {"extraction": "gemini"},
}


def _python(rig: Rig) -> str:
    return str(rig.product / ".venv" / "bin" / "python")


def test_apply_runs_the_harness_reapply_and_nothing_else(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    rig.install_deployment()
    assert rig("apply") == 0
    assert rig.runner.argvs() == [
        [_python(rig), "-m", "harness.apply", "--reapply",
         "--config", str(rig.product / "osprey.yaml"),
         "--out-root", str(rig.deployment.parent)]
    ]  # fmt: skip
    words = {w for argv in rig.runner.argvs() for w in argv}
    assert not words & {"harness.register_sign_in", "harness.first_admin", "--demo-analyst",
                        "--seed", "--build", "install", "scripts.demo_packs"}  # fmt: skip
    assert "applied" in capsys.readouterr().out


def test_apply_with_the_option_spelling_is_the_verb(rig: Rig) -> None:
    rig.install_deployment()
    assert rig("--apply") == 0
    assert len(rig.runner.with_word("--reapply")) == 1


def test_nothing_installed_is_refused_in_words(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    assert rig("apply") == 1
    assert "Nothing is installed here yet" in capsys.readouterr().err
    assert rig.runner.calls == []


def test_a_refused_apply_is_reported(rig: Rig, capsys: pytest.CaptureFixture[str]) -> None:
    rig.install_deployment()
    rig.runner.fail["--reapply"] = 1
    assert rig("apply") == 1
    assert "apply the changed settings" in capsys.readouterr().err


class InProcessHarness:
    """A runner that runs `harness.apply` in this process, as the real runner would in a child: the
    terminal's environment reaches it, and Docker is stood in for (`apply._run`)."""

    def __init__(self, environ: Mapping[str, str]) -> None:
        self.environ = dict(environ)
        self.compose: list[list[str]] = []

    def __call__(
        self, argv: Sequence[str], *, env: Mapping[str, str] | None = None, cwd: Path | None = None
    ) -> int:
        from harness import apply

        assert list(argv[1:3]) == ["-m", "harness.apply"], argv
        return apply.main(list(argv[3:]), environ=self.environ, ask_secret=None)


def test_after_the_verb_the_key_is_kept_and_deployment_env_is_600(
    rig: Rig, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from harness import apply
    from harness.preflight.result import passed

    calls: list[list[str]] = []

    def no_docker(args: list[str], *, stage: str, **_kwargs: object) -> str:
        calls.append(list(args))
        if "up" not in args and "ps" not in args:
            raise apply.ApplyFailed(stage, "no Docker in this test")
        return ""

    monkeypatch.setattr(apply, "_run", no_docker)
    monkeypatch.setattr(apply, "answer_localhost_with_loopback", lambda: None)
    monkeypatch.setattr(apply, "ALL_CHECKS", [type("P", (), {"check": staticmethod(
        lambda _c: passed("ports"))})])  # fmt: skip
    config = rig.product / "osprey.yaml"
    out_root = rig.deployment.parent
    # The first install, by the real harness, stopped at its first build.
    assert apply.main(["--config", str(config), "--out-root", str(out_root), "--no-build",
                       "--skip-verify"]) in (0, 1)  # fmt: skip
    env_file = rig.deployment / "deployment.env"
    env_file.chmod(0o644)  # as the owner's two deployments were before ADR-137
    config.write_text(yaml.safe_dump({**BASE_CONFIG, "models": GEMINI}), encoding="utf-8")

    rig.env["OSPREY_MODEL_KEY_GEMINI"] = GEMINI_KEY
    harness = InProcessHarness(rig.env)
    from ospreyflow.main import main

    code = main(
        ["apply"], runner=harness, probes=rig.probes,
        home_env={"OSPREYFLOW_HOME": str(rig.product), **rig.env},
        recorded_home=lambda: None, capture=rig.capture, ask=rig.ask,
        ask_secret=rig.ask_secret, open_url=rig.opened.append,
    )  # fmt: skip
    assert code == 0
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
    assert f"OSPREY_MODEL_KEY_GEMINI={GEMINI_KEY}\n" in env_file.read_text(encoding="utf-8")
    out = capsys.readouterr()
    assert GEMINI_KEY not in out.out + out.err


def _installed_with(rig: Rig, rendered: dict[str, object], wanted: dict[str, object]) -> Path:
    """`rendered`: the models the deployment runs (its own copy of osprey.yaml); `wanted`: the
    product's osprey.yaml, as the admin has edited it."""
    rig.install_deployment()
    (rig.deployment / "osprey.yaml").write_text(
        yaml.safe_dump({**BASE_CONFIG, "models": rendered}), encoding="utf-8"
    )
    (rig.product / "osprey.yaml").write_text(
        yaml.safe_dump({**BASE_CONFIG, "models": wanted}), encoding="utf-8"
    )
    return rig.deployment / "deployment.env"


def test_models_key_for_a_provider_not_yet_rendered_names_apply(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    env_file = _installed_with(rig, {"local_only": True}, GEMINI)
    rig.env["OSPREY_MODEL_KEY_GEMINI"] = GEMINI_KEY
    assert rig("models", "key", "gemini") == 1
    err = capsys.readouterr().err
    assert "ospreyflow apply" in err
    assert "install" not in err
    assert GEMINI_KEY not in env_file.read_text(encoding="utf-8")
    assert rig.runner.calls == []


def test_models_key_for_a_provider_enabled_nowhere_still_says_how_to_enable_it(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    _installed_with(rig, {"local_only": True}, {"local_only": True})
    assert rig("models", "key", "gemini") == 1
    err = capsys.readouterr().err
    assert "models.providers in osprey.yaml" in err and "ospreyflow apply" in err
    assert "install" not in err


def test_models_key_and_remove_key_leave_deployment_env_600(rig: Rig) -> None:
    env_file = _installed_with(rig, GEMINI, GEMINI)
    env_file.chmod(0o644)
    rig.env["OSPREY_MODEL_KEY_GEMINI"] = GEMINI_KEY
    assert rig("models", "key", "gemini") == 0
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
    env_file.chmod(0o644)
    assert rig("models", "remove-key", "gemini") == 0
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600


if sys.platform == "win32":  # pragma: no cover - modes are POSIX
    pytestmark = pytest.mark.skip("file modes are POSIX")
