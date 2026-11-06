"""`scripts/lanes_launch.sh` (ADR-142 decision 10): the orchestrator's launcher for the lanes.

Rule 15: the launcher runs as the orchestrator runs it, from the root of a real git repository (a
small one in `tmp_path`, with the tracked `OspreyFlow_Core/osprey.yaml` the owner edits locally); a
running session is planted as a real process named `claude` whose working directory is the
worktree, as a lane's is; `osascript` is a stand-in that records what it is asked to open, so a test
never opens a Terminal window; and Claude Code itself is never started.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

BUILD = Path(__file__).resolve().parents[1]
SCRIPT = BUILD / "scripts" / "lanes_launch.sh"
HEARTBEAT = BUILD / "scripts" / "lanes_heartbeat.sh"

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
}


def _git(cwd: Path, *args: str) -> str:
    env = {**os.environ, **_GIT_ENV}
    return subprocess.run(
        ["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def launcher(tmp_path: Path):
    base = tmp_path.resolve()
    repo = base / "repo"
    (repo / "OspreyFlow_Core").mkdir(parents=True)
    lanes = repo / "OspreyFlow_Build" / "process" / "lanes"
    (lanes / "studio").mkdir(parents=True)
    (repo / "OspreyFlow_Build" / "scripts").mkdir(parents=True)
    shutil.copy(HEARTBEAT, repo / "OspreyFlow_Build" / "scripts" / "lanes_heartbeat.sh")
    (repo / "OspreyFlow_Core" / "osprey.yaml").write_text("models:\n  local_only: true\n")
    (lanes / "PROMPT_L.md").write_text("You are the <lane> lane, on branch lane/<lane>.\n")
    (lanes / "PROMPT_R.md").write_text("You are the <lane> lane, resuming.\n")
    (lanes / "studio" / "BRIEF.md").write_text("# Brief\n\nL1.1: phase 4's remainder.\n")
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    # The owner's local, never-committed edit, as on the real checkout.
    (repo / "OspreyFlow_Core" / "osprey.yaml").write_text("models:\n  local_only: false\n")

    bin_dir = base / "bin"
    bin_dir.mkdir()
    opened = base / "opened.log"
    osascript = bin_dir / "osascript"
    osascript.write_text(f'#!/bin/sh\nprintf "%s\\n" "$2" >> "{opened}"\n')
    osascript.chmod(0o755)
    env = {
        **os.environ,
        **_GIT_ENV,
        "OSPREY_WORKTREES": str(base / "wt"),
        "OSPREY_LANES_DIR": str(base / "state"),
        "OSPREY_SETUP_SKIP_ENV": "1",
        "OSPREY_CLAUDE_CMD": "echo not-claude",
        "OSPREY_CLAUDE_CONFIG_DIR": str(base / "claude-config"),
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
    }

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(SCRIPT), *args], cwd=repo, env=env, capture_output=True, text=True
        )

    run.repo, run.wt, run.opened, run.bin = repo, base / "wt", opened, bin_dir  # type: ignore[attr-defined]
    return run


@pytest.fixture
def session_in(launcher):
    """A process named `claude` whose working directory is the given directory, as a lane's is."""
    fake = launcher.bin / "claude"
    fake.write_text("#!/bin/bash\nsleep 60\n")
    fake.chmod(0o755)
    procs: list[subprocess.Popen[bytes]] = []

    def start(cwd: Path) -> None:
        procs.append(subprocess.Popen(["bash", str(fake)], cwd=cwd))
        time.sleep(0.3)

    yield start
    for p in procs:
        p.kill()
        p.wait()


def test_setup_leaves_osprey_yaml_marked_so_git_add_all_cannot_stage_it(launcher) -> None:
    done = launcher("setup", "studio")
    assert done.returncode == 0, done.stderr
    wt = launcher.wt / "studio"
    assert (wt / "OspreyFlow_Core" / "osprey.yaml").read_text() == "models:\n  local_only: false\n"
    _git(wt, "add", "-A")
    assert _git(wt, "diff", "--cached", "--name-only") == ""
    assert _git(wt, "rev-parse", "--abbrev-ref", "HEAD").strip() == "lane/studio"


def test_open_refuses_when_a_session_is_running_in_the_worktree(launcher, session_in) -> None:
    launcher("setup", "studio")
    session_in(launcher.wt / "studio" / "OspreyFlow_Core")
    assert launcher("alive", "studio").stdout.strip() == "yes"
    refused = launcher("open", "studio")
    assert refused.returncode == 1
    assert "already running" in refused.stderr
    assert not launcher.opened.exists()


def test_a_session_in_a_sibling_folder_is_not_the_lanes(launcher, session_in) -> None:
    launcher("setup", "studio")
    sibling = launcher.wt / "studio-old"
    sibling.mkdir(parents=True)
    session_in(sibling)
    assert launcher("alive", "studio").stdout.strip() == "no"


def test_open_with_no_session_opens_one_window_on_the_lanes_prompt(launcher) -> None:
    launcher("setup", "studio")
    opened = launcher("open", "studio")
    assert opened.returncode == 0, opened.stderr
    [script] = launcher.opened.read_text().splitlines()
    start = Path(script.split("source '")[1].split("'")[0])
    text = start.read_text()
    assert f'cd "{launcher.wt / "studio"}"' in text
    assert "export CLAUDE_CONFIG_DIR=" in text
    prompt = Path(text.split('$(cat "')[1].split('")')[0]).read_text()
    assert "You are the studio lane, on branch lane/studio." in prompt
    assert "L1.1: phase 4's remainder." in prompt


@pytest.mark.parametrize("lane", ["studio", "glass", "case"])
def test_headless_refuses_any_lane_but_docs(launcher, lane) -> None:
    launcher("setup", lane)
    refused = launcher("headless", lane)
    assert refused.returncode == 1
    assert "docs lane only" in refused.stderr
