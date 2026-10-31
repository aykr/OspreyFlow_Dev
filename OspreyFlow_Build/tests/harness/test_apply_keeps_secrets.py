"""ADR-132, the owner's ruling 6: `apply` never replaces a secret `deployment.env` already holds,
and a run its preflight refuses writes nothing to the deployment at all.

Found 31 October 2026: `ospreyflow install` run again over a running deployment rendered fresh
passwords into `deployment.env`, then stopped at preflight (its own port was in use). The running
databases and Keycloak still had the first passwords; the file no longer did, so the deployment
could not sign in to its own stores. These cases drive the real `harness.apply`, standing in only
for the preflight checks and for the compose commands, so nothing reaches Docker.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest
from harness import apply
from harness.preflight.result import failed, passed

SECRET = ("PASSWORD", "SECRET", "SECRET_KEY", "ACCESS_KEY")
PASSES = SimpleNamespace(check=lambda _context: passed("ports"))
REFUSES = SimpleNamespace(
    check=lambda _context: failed(
        "ports", what_is_wrong="8081 is in use", what_to_do="stop what holds it"
    )
)


def _secrets(env: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in env.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            if key.endswith(SECRET):
                found[key] = value
    return found


@pytest.fixture
def preflight(monkeypatch: pytest.MonkeyPatch) -> Callable[[bool], None]:
    """Sets whether the stand-in preflight passes. Past it, the first compose command refuses, so a
    passing run has written the deployment's files and stops before anything starts."""

    def refuse_compose(_args: list[str], *, stage: str, **_kwargs: object) -> str:
        raise apply.ApplyFailed(stage, "no Docker in this test")

    monkeypatch.setattr(apply, "_run", refuse_compose)
    monkeypatch.setattr(apply, "answer_localhost_with_loopback", lambda: None)

    def set_passing(passing: bool) -> None:
        monkeypatch.setattr(apply, "ALL_CHECKS", [PASSES if passing else REFUSES])

    set_passing(True)
    return set_passing


def _apply(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    config = tmp_path / "osprey.yaml"
    if not config.exists():
        config.write_text("{}\n", encoding="utf-8")
    out_root = tmp_path / "generated"
    argv = ["--config", str(config), "--out-root", str(out_root), "--demo-analyst"]
    assert apply.main(argv) != 0, "a stand-in refuses, so apply must stop"
    return out_root / "local-lite" / "deployment.env"


def test_a_second_apply_keeps_every_secret_the_first_wrote(
    tmp_path: Path, preflight: Callable[[bool], None]
) -> None:
    env = _apply(tmp_path)
    first = _secrets(env)
    assert len(first) >= 10, first.keys()

    _apply(tmp_path)

    assert _secrets(env) == first


def test_a_run_its_preflight_refuses_writes_nothing_to_the_deployment(
    tmp_path: Path, preflight: Callable[[bool], None]
) -> None:
    env = _apply(tmp_path)
    folder = env.parent
    # Contents and modification times: a rewrite with the same bytes is still a write.
    def snapshot() -> dict[Path, tuple[bytes, int]]:
        return {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.rglob("*") if p.is_file()}

    before = snapshot()

    preflight(False)
    _apply(tmp_path)

    assert snapshot() == before
    assert not list(folder.parent.glob(".*staging")), "the staging folder is removed"


def test_a_first_run_its_preflight_refuses_leaves_no_deployment(
    tmp_path: Path, preflight: Callable[[bool], None]
) -> None:
    preflight(False)
    env = _apply(tmp_path)
    assert not env.parent.exists()


def test_a_secret_added_after_the_render_is_kept_too(
    tmp_path: Path, preflight: Callable[[bool], None]
) -> None:
    """`register_sign_in` adds the engineer's and report viewer's passwords after the render; their
    Keycloak accounts keep them, so a re-render must not drop them."""
    env = _apply(tmp_path)
    env.write_text(
        env.read_text(encoding="utf-8") + "OSPREY_DEMO_ENGINEER_PASSWORD=engineer-first\n",
        encoding="utf-8",
    )

    _apply(tmp_path)

    assert _secrets(env)["OSPREY_DEMO_ENGINEER_PASSWORD"] == "engineer-first"


def test_a_first_apply_mints_fresh_secrets(
    tmp_path: Path, preflight: Callable[[bool], None]
) -> None:
    """Nothing to keep: two separate deployments get different secrets."""
    first = _secrets(_apply(tmp_path / "a"))
    second = _secrets(_apply(tmp_path / "b"))
    assert first["OSPREY_KEYCLOAK_ADMIN_PASSWORD"] != second["OSPREY_KEYCLOAK_ADMIN_PASSWORD"]
