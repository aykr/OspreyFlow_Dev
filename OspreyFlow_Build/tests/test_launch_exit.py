"""The launcher notices when something it started has stopped, and says why.

Seen on the owner's machine: the Admin console tile said "Starting" for as long as the launcher ran,
with a bouncing "This usually takes about a minute". The console had exited at once, because macOS's
AirPlay Receiver already held its port. The launcher started the process and never looked at it
again, so it waited out its whole grace period for a page that could not appear. Each test below
names what it would catch.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
from scripts import launch

ADDRESS_IN_USE = (
    "INFO:     Application startup complete.\n"
    "ERROR:    [Errno 48] error while attempting to bind on address ('0.0.0.0', 7100): "
    "address already in use\n"
    "INFO:     Application shutdown complete.\n"
)


class Child:
    def __init__(self, log_path: Path, exit_code: int | None = None) -> None:
        self.log_path = log_path
        self.exit_code = exit_code

    def poll(self) -> int | None:
        return self.exit_code


class Spawner:
    """Hands back a child per background start, as the real spawner does."""

    def __init__(self, log_path: Path, log_text: str = "", exit_code: int | None = None) -> None:
        self.log_path = log_path
        log_path.write_text(log_text, encoding="utf-8")
        self.child = Child(log_path, exit_code)
        self.calls: list[list[str]] = []

    def __call__(
        self, argv: Sequence[str], *, cwd: Path, wait: bool = False
    ) -> launch.Handle | None:
        self.calls.append(list(argv))
        return None if wait else self.child


class Prober:
    def __init__(self, answers: dict[str, int | None] | None = None) -> None:
        self.answers = answers or {}

    def __call__(self, url: str) -> int | None:
        return self.answers.get(url)


def _launcher(tmp_path: Path, spawner: Spawner, prober: Prober | None = None) -> launch.Launcher:
    out = tmp_path / "deploy" / "generated" / "local-lite"
    out.mkdir(parents=True)
    (out / "deployment.env").write_text("OSPREY_WORKSPACE_PORT=8080\n", encoding="utf-8")
    (out / "compose.yaml").write_text("name: osprey-local-lite\nservices: {}\n", encoding="utf-8")
    return launch.Launcher(
        repo_root=tmp_path,
        prober=prober or Prober(),
        spawner=spawner,
        frontend_built=True,
        clock=lambda: 0.0,  # never leaves the grace period: only the exit can end "starting"
    )


def _admin_state(launcher: launch.Launcher) -> str:
    return launcher.status()[launch.ADMIN]


def test_a_console_that_is_still_running_reads_starting(tmp_path: Path) -> None:
    """The other side of the same rule: no false alarm while it is genuinely coming up."""
    launcher = _launcher(tmp_path, Spawner(tmp_path / "python.log"))
    launcher.start_in_background("admin")
    launcher.wait_idle()
    assert _admin_state(launcher) == "starting"


def test_a_console_that_has_exited_reads_not_running_not_starting(tmp_path: Path) -> None:
    """Catches the seen defect: still "Starting" long after the process was gone."""
    spawner = Spawner(tmp_path / "python.log", ADDRESS_IN_USE, exit_code=1)
    launcher = _launcher(tmp_path, spawner)
    launcher.start_in_background("admin")
    launcher.wait_idle()
    assert _admin_state(launcher) == "down"


def test_the_tile_says_what_the_log_says_and_where_the_log_is(tmp_path: Path) -> None:
    spawner = Spawner(tmp_path / "python.log", "boom: the reason\n", exit_code=1)
    launcher = _launcher(tmp_path, spawner)
    launcher.start_in_background("admin")
    launcher.wait_idle()
    tiles = launcher.render_tiles(launcher.status())
    assert "boom: the reason" in tiles
    assert str(tmp_path / "python.log") in tiles
    assert "Starting…" not in tiles


def test_a_port_already_in_use_is_named_in_plain_words(tmp_path: Path) -> None:
    """The reason seen: another program held the port. A raw errno is not an explanation."""
    spawner = Spawner(tmp_path / "python.log", ADDRESS_IN_USE, exit_code=1)
    launcher = _launcher(tmp_path, spawner)
    launcher.start_in_background("admin")
    launcher.wait_idle()
    tiles = launcher.render_tiles(launcher.status())
    assert f"already using port {launch.HARNESS_PORT}" in tiles
    assert "Errno 48" not in tiles


def test_pressing_start_again_forgets_the_earlier_failure(tmp_path: Path) -> None:
    spawner = Spawner(tmp_path / "python.log", ADDRESS_IN_USE, exit_code=1)
    launcher = _launcher(tmp_path, spawner)
    launcher.start_in_background("admin")
    launcher.wait_idle()
    spawner.child.exit_code = None  # the second attempt is running
    launcher.start_in_background("admin")
    launcher.wait_idle()
    assert _admin_state(launcher) == "starting"
    assert "already using port" not in launcher.render_tiles(launcher.status())


def test_a_console_that_answers_is_running_whatever_its_process_did(tmp_path: Path) -> None:
    spawner = Spawner(tmp_path / "python.log", "", exit_code=1)
    prober = Prober({f"http://localhost:{launch.HARNESS_PORT}/": 200})
    launcher = _launcher(tmp_path, spawner, prober)
    launcher.start_in_background("admin")
    launcher.wait_idle()
    assert _admin_state(launcher) == "up"


@pytest.mark.parametrize(("code", "state"), [(0, "starting"), (1, "down")])
def test_a_compose_start_that_ends_cleanly_is_not_a_failure(
    tmp_path: Path, code: int, state: str
) -> None:
    """`docker compose up -d --wait` is meant to exit; only a non-zero exit is a failed start."""
    spawner = Spawner(tmp_path / "docker.log", "", exit_code=code)
    launcher = _launcher(tmp_path, spawner)
    launcher.start_in_background("stack")
    launcher.wait_idle()
    assert launcher.status()[launch.GLASS] == state
