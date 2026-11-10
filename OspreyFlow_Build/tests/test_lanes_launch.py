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
LEASE = BUILD / "scripts" / "stack_lease.sh"

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
    for lane in ("studio", "case"):
        (lanes / lane).mkdir(parents=True)
    (repo / "OspreyFlow_Build" / "scripts").mkdir(parents=True)
    shutil.copy(HEARTBEAT, repo / "OspreyFlow_Build" / "scripts" / "lanes_heartbeat.sh")
    shutil.copy(LEASE, repo / "OspreyFlow_Build" / "scripts" / "stack_lease.sh")
    # The tables both read (ADR-142 Amendment 3): the lanes, and the two test stacks.
    for table in ("lanes.conf", "lane_stacks.tsv"):
        shutil.copy(BUILD / "scripts" / table, repo / "OspreyFlow_Build" / "scripts" / table)
    # stack_lease.sh asks docker about the dev stack named by this file (a stand-in docker says "down").
    (repo / "OspreyFlow_Core" / "deploy" / "compose").mkdir(parents=True)
    (repo / "OspreyFlow_Core" / "deploy" / "compose" / "dev.yaml").write_text("services: {}\n")
    (lanes / "case" / "BRIEF.md").write_text("# Brief\n\nL3.1: the analyst layer.\n")
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
    docker = bin_dir / "docker"
    docker.write_text("#!/bin/sh\nexit 0\n")  # the stack is down
    docker.chmod(0o755)
    env = {
        **os.environ,
        **_GIT_ENV,
        "OSPREY_WORKTREES": str(base / "wt"),
        "OSPREY_LANES_DIR": str(base / "state"),
        "OSPREY_SETUP_SKIP_ENV": "1",
        "OSPREY_CLAUDE_CMD": "echo not-claude",
        "OSPREY_CLAUDE_CONFIG_DIR": str(base / "claude-config"),
        "OSPREY_ACCOUNTS_FILE": str(base / "accounts.conf"),
        "OSPREY_LEASE_DIR": str(base / "lease"),
        "OSPREY_SWITCH_WAIT": "2",
        "OSPREY_SWITCH_POLL": "1",
        "HOME": str(base / "home"),
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
    }

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(SCRIPT), *args], cwd=repo, env=env, capture_output=True, text=True
        )

    run.repo, run.wt, run.opened, run.bin = repo, base / "wt", opened, bin_dir  # type: ignore[attr-defined]
    run.base, run.env, run.state = base, env, base / "state"  # type: ignore[attr-defined]
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
    assert 'export OSPREY_LANE="studio"' in text  # the port guard lets only the lease's lane reach the stack
    assert 'export OSPREY_PORTS_SLOT="10"' in text  # studio's own Playwright ports (lane_ports.tsv, T2)
    prompt = Path(text.split('$(cat "')[1].split('")')[0]).read_text()
    assert "You are the studio lane, on branch lane/studio." in prompt
    assert "L1.1: phase 4's remainder." in prompt


@pytest.mark.parametrize("lane", ["studio", "case", "admin", "rules", "platform"])
def test_headless_refuses_any_lane_but_docs(launcher, lane) -> None:
    launcher("setup", lane)
    refused = launcher("headless", lane)
    assert refused.returncode == 1
    assert "docs lane only" in refused.stderr


def test_opening_a_lane_leaves_its_pending_nudge_for_the_lane(launcher) -> None:
    """The orchestrator's own beat at open must not read the lane's nudge away (found 7 November
    2026: a resumed glass session never saw the review it was nudged with)."""
    launcher("setup", "studio")
    subprocess.run(
        ["bash", str(HEARTBEAT), "nudge", "studio", "rebase on main"],
        env={**os.environ, "OSPREY_LANES_DIR": str(launcher.wt.parent / "state")},
        check=True, capture_output=True,
    )
    assert launcher("resume", "studio").returncode == 0
    nudge = launcher.wt.parent / "state" / "studio.nudge"
    assert nudge.exists() and "rebase on main" in nudge.read_text()


# --- ADR-142 Amendment 1: accounts, pausing and switching -------------------------------------------

_TOKEN = "sk-ant-PLANTED-0000-never-printed"


def _accounts(launcher, extra: str = "") -> Path:
    """Two signed-in accounts, as the owner makes them: each a config directory holding a credential
    file this tooling must never read, copy or print."""
    for name in ("ayan", "client"):
        d = launcher.base / f"claude-{name}"
        d.mkdir(exist_ok=True)
        (d / ".credentials.json").write_text('{"token": "%s-%s"}' % (_TOKEN, name))
    conf = launcher.base / "accounts.conf"
    conf.write_text(
        f"account ayan   = {launcher.base / 'claude-ayan'}\n"
        f"account client = {launcher.base / 'claude-client'}   # the client's subscription\n"
        "orchestrator   = ayan\n"
        "lane studio    = client\n" + extra
    )
    return conf


def _windows(launcher) -> list[str]:
    """The windows the launcher asked Terminal to open (the stand-in osascript also records the
    heartbeat's notifications, which are not windows)."""
    if not launcher.opened.exists():
        return []
    return [line for line in launcher.opened.read_text().splitlines() if "source '" in line]


def _start_script(launcher) -> str:
    script = _windows(launcher)[-1]
    return Path(script.split("source '")[1].split("'")[0]).read_text()


def _prompt(text: str) -> str:
    return Path(text.split('$(cat "')[1].split('")')[0]).read_text()


def test_a_lane_started_with_an_account_runs_under_that_accounts_directory(launcher) -> None:
    _accounts(launcher)
    launcher("setup", "case")
    assert launcher("open", "case", "--account", "client").returncode == 0
    text = _start_script(launcher)
    assert f'export CLAUDE_CONFIG_DIR="{launcher.base / "claude-client"}"' in text
    assert "account client" in text  # the tab's title and the session's first line name it
    # With no --account, the map: case has no line, so the orchestrator's account.
    launcher.opened.unlink()
    (launcher.state / "case.beat").unlink()
    assert launcher("resume", "case").returncode == 0
    assert f'export CLAUDE_CONFIG_DIR="{launcher.base / "claude-ayan"}"' in _start_script(launcher)


def test_an_unknown_account_or_a_missing_directory_is_refused_before_any_session_starts(launcher) -> None:
    conf = _accounts(launcher)
    launcher("setup", "case")
    unknown = launcher("open", "case", "--account", "nobody")
    assert unknown.returncode == 1 and "no account 'nobody'" in unknown.stderr
    conf.write_text(conf.read_text() + f"account gone = {launcher.base / 'not-signed-in'}\n")
    missing = launcher("open", "case", "--account", "gone")
    assert missing.returncode == 1 and "does not exist" in missing.stderr
    assert not launcher.opened.exists()


def _lease(launcher, holder: str, stack: str = "a") -> Path:
    lock = launcher.base / "lease" / ("stack.lease" if stack == "a" else f"stack-{stack}.lease")
    lock.mkdir(parents=True)
    (lock / "info").write_text(f"holder={holder}\nstack={stack}\npurpose=live tests\nsince=2026-11-07T18:00:00Z\n")
    return lock


def _handoff(launcher, lane: str) -> Path:
    h = launcher.wt / lane / "OspreyFlow_Build" / "process" / "lanes" / lane / "HANDOFF.md"
    h.parent.mkdir(parents=True, exist_ok=True)
    h.write_text(f"# {lane} · paused\n\n- Step L3.1, fix 7.\n- Next: the live set.\n")
    return h


def _lane_runs(launcher, lane: str, *args: str) -> subprocess.CompletedProcess[str]:
    """As the lane runs it: from its own worktree, whose scripts are its branch's."""
    return subprocess.run(
        ["bash", str(SCRIPT), *args], cwd=launcher.wt / lane, env=launcher.env,
        capture_output=True, text=True,
    )


def test_pausing_a_lane_holding_the_lease_releases_it_before_the_lane_is_paused(launcher) -> None:
    launcher("setup", "case")
    lock = _lease(launcher, "case")
    assert launcher("pause", "case").returncode == 0
    assert "PAUSE REQUESTED" in (launcher.state / "case.nudge").read_text()
    _handoff(launcher, "case")
    (launcher.wt / "case" / "half_done.py").write_text("x = 1\n")
    done = _lane_runs(launcher, "case", "pause-done", "case", "L3.1 fix 7")
    assert done.returncode == 0, done.stderr
    assert not lock.exists()  # released before the beat says paused
    assert "state=paused" in (launcher.state / "case.beat").read_text()
    log = _git(launcher.wt / "case", "log", "-1", "--name-only", "--format=%s")
    assert log.startswith("wip(case): paused at L3.1 fix 7")
    assert "HANDOFF.md" in log and "half_done.py" in log


def test_a_pause_is_refused_while_the_stack_is_still_up(launcher) -> None:
    launcher("setup", "case")
    lock = _lease(launcher, "case")
    (launcher.bin / "docker").write_text("#!/bin/sh\necho 3f1c0a9b2d7e\n")  # up
    _handoff(launcher, "case")
    refused = _lane_runs(launcher, "case", "pause-done", "case", "L3.1")
    assert refused.returncode == 1 and lock.exists()
    assert "state=paused" not in (launcher.state / "case.beat").read_text() if (launcher.state / "case.beat").exists() else True


def test_the_merge_gate_refuses_a_branch_holding_a_wip_commit(launcher) -> None:
    launcher("setup", "case")
    assert launcher("merge-ok", "case").returncode == 0
    _handoff(launcher, "case")
    assert _lane_runs(launcher, "case", "pause-done", "case", "L3.1").returncode == 0
    (launcher.wt / "case" / "after.py").write_text("y = 2\n")
    _git(launcher.wt / "case", "add", "-A")
    _git(launcher.wt / "case", "commit", "-q", "-m", "fix(datasets): a later proper commit")
    refused = launcher("merge-ok", "case")
    assert refused.returncode == 1
    assert "wip(case): paused at L3.1" in refused.stderr


def test_resume_after_a_pause_starts_prompt_r_with_the_handoff_named_first(launcher) -> None:
    _accounts(launcher)
    launcher("setup", "case")
    _handoff(launcher, "case")
    assert _lane_runs(launcher, "case", "pause-done", "case", "L3.1").returncode == 0
    assert launcher("resume", "case", "--account", "client").returncode == 0
    prompt = _prompt(_start_script(launcher))
    first = prompt.splitlines()[0]
    assert "OspreyFlow_Build/process/lanes/case/HANDOFF.md" in first
    assert "You are the case lane, resuming." in prompt


def test_a_lane_that_cannot_answer_is_paused_from_outside_and_nothing_is_committed(launcher) -> None:
    launcher("setup", "case")
    (launcher.wt / "case" / "half_done.py").write_text("x = 1\n")
    head = _git(launcher.wt / "case", "rev-parse", "HEAD")
    assert launcher("pause", "case", "--now").returncode == 0
    assert _git(launcher.wt / "case", "rev-parse", "HEAD") == head
    handoff = (launcher.wt / "case" / "OspreyFlow_Build" / "process" / "lanes" / "case" / "HANDOFF.md").read_text()
    assert "half_done.py" in handoff and "unclean" in handoff
    assert "paused (unclean)" in (launcher.state / "case.beat").read_text()


def test_no_output_log_or_commit_holds_anything_from_an_account_directory(launcher) -> None:
    _accounts(launcher, "fallback case = ayan\n")
    launcher("setup", "case")
    outputs = [
        launcher("open", "case", "--account", "client"),
        launcher("pause", "case", "--now"),
        launcher("fallback-switch", "case"),
        launcher("orchestrator", "--account", "ayan"),
    ]
    _handoff(launcher, "case")
    outputs.append(_lane_runs(launcher, "case", "pause-done", "case", "L3.1"))
    seen = "".join(o.stdout + o.stderr for o in outputs)
    for f in [*launcher.state.rglob("*"), launcher.opened]:
        if f.is_file():
            seen += f.read_text(errors="replace")
    seen += _git(launcher.wt / "case", "log", "-p", "--all")
    assert _TOKEN not in seen
    assert "claude-ayan" in seen  # the directory is named, which is allowed; its contents are not


def test_watch_never_switches_a_lane_without_the_owners_fallback_line(launcher) -> None:
    """Amendment 1 decision 6. The watch's own pass runs the real launcher; with no fallback line a
    lane at its usage limit is listed for the owner and no window opens; with one, it is switched once."""
    _accounts(launcher)
    launcher("setup", "case")
    hb_env = {**launcher.env, "OSPREY_LANES": "case", "OSPREY_WATCH_PASSES": "1",
              "OSPREY_LAUNCHER": str(SCRIPT), "TERM": "dumb"}

    def watch() -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(HEARTBEAT), "watch", "0"], cwd=launcher.repo,
                              env=hb_env, capture_output=True, text=True)

    subprocess.run(["bash", str(HEARTBEAT), "beat", "case", "blocked", "usage limit"],
                   env=hb_env, check=True, capture_output=True)
    shown = watch()
    assert "case stopped at its usage limit on account" in shown.stdout
    assert _windows(launcher) == []
    assert not (launcher.state / "case.fallback-used").exists()

    conf = launcher.base / "accounts.conf"
    conf.write_text(conf.read_text() + "fallback case = client\n")
    watch()
    assert (launcher.state / "case.fallback-used").exists()
    assert f'export CLAUDE_CONFIG_DIR="{launcher.base / "claude-client"}"' in _start_script(launcher)
    # Once only: blocked at the limit again, the next pass does not switch it a second time.
    subprocess.run(["bash", str(HEARTBEAT), "beat", "case", "blocked", "usage limit"],
                   env=hb_env, check=True, capture_output=True)
    before = _windows(launcher)
    watch()
    assert _windows(launcher) == before and len(before) == 1



# --- Six lanes and two stacks (ADR-142 Amendment 3, 8 November 2026) -----------------------------------


@pytest.mark.parametrize("lane", ["admin", "rules", "platform", "case-b", "studio-b", "rules-b"])
def test_the_new_lanes_are_known(launcher, lane: str) -> None:
    assert launcher("setup", lane).returncode == 0
    assert (launcher.wt / lane).is_dir()


def test_the_retired_glass_lane_is_refused(launcher) -> None:
    """Glass was split into admin and rules: opening it again would start a seventh lane no table lists
    (red against the four-lane launcher, which knew glass)."""
    refused = launcher("setup", "glass")
    assert refused.returncode == 2 and "Unknown lane 'glass'" in refused.stderr
    assert "admin" in refused.stderr and "platform" in refused.stderr


def test_pausing_a_lane_holding_stack_b_releases_stack_b(launcher) -> None:
    launcher("setup", "case")
    lock = _lease(launcher, "case", "b")
    _handoff(launcher, "case")
    done = _lane_runs(launcher, "case", "pause-done", "case", "L3.2")
    assert done.returncode == 0, done.stderr
    assert not lock.exists()


def test_an_unclean_pause_names_the_stack_still_held(launcher) -> None:
    launcher("setup", "case")
    _lease(launcher, "case", "b")
    assert launcher("pause", "case", "--now").returncode == 0
    handoff = (launcher.wt / "case" / "OspreyFlow_Build" / "process" / "lanes" / "case" / "HANDOFF.md").read_text()
    assert "still holds the lease on test stack b" in handoff
