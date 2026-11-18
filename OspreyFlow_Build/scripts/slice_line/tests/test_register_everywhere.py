"""F1, the third protection: the guard registered for every session on this Mac (the owner's ~/.claude/settings.json and
~/.claude-sol/settings.json), through install.sh. The owner's word, 18 November 2026: only with
`install.sh --register-everywhere`; a plain install changes no account's settings. Run as the owner runs it, in a
throwaway home. The last case records what the guard then refuses in one of the owner's own sessions (no seat) in
another repository, as COMMANDS.md says.
"""
from __future__ import annotations

import json
import subprocess

import pytest

from test_gates import SYSPY, sh, world  # noqa: F401  (world is a fixture)

GUARD_PRE = "/usr/bin/python3 $HOME/.ospreyflow/slice-line/bin/guard.py pre"
GUARD_STOP = "/usr/bin/python3 $HOME/.ospreyflow/slice-line/bin/guard.py stop"
OWN = {"model": "opus", "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "mine.sh"}]}]}}


def accounts(w):
    for d in (".claude", ".claude-sol"):
        (w["home"] / d).mkdir(parents=True, exist_ok=True)
        (w["home"] / d / "settings.json").write_text(json.dumps(OWN, indent=2))


def install(w, *args):
    return sh(["bash", str(w["lines"] / "install.sh"), *args], w["repo"], w["env"], check=False)


def commands(settings: dict, event: str) -> list[str]:
    return [h["command"] for e in settings.get("hooks", {}).get(event, []) for h in e.get("hooks", [])]


def test_register_everywhere_is_not_done_by_a_plain_install(world):
    w = world
    accounts(w)
    before = {d: (w["home"] / d / "settings.json").read_bytes() for d in (".claude", ".claude-sol")}
    p = install(w)
    assert p.returncode == 0, p.stdout + p.stderr
    assert {d: (w["home"] / d / "settings.json").read_bytes() for d in before} == before


def test_register_everywhere_adds_the_guard_to_every_account_once_keeping_the_owners_own_settings(world):
    w = world
    accounts(w)
    for _ in range(2):
        p = install(w, "--register-everywhere")
        assert p.returncode == 0, p.stdout + p.stderr
    for d in (".claude", ".claude-sol"):
        s = json.loads((w["home"] / d / "settings.json").read_text())
        assert commands(s, "PreToolUse").count(GUARD_PRE) == 1, s
        assert [e["matcher"] for e in s["hooks"]["PreToolUse"] if GUARD_PRE in json.dumps(e)] == ["*"]
        assert commands(s, "Stop").count(GUARD_STOP) == 1, s
        assert "mine.sh" in commands(s, "PreToolUse") and s["model"] == "opus"   # the owner's own kept
        assert list((w["home"] / d).glob("settings.json.before-slice-line-*")), "a copy of the settings as they were"


def test_register_everywhere_makes_a_settings_file_where_an_account_has_none(world):
    w = world
    (w["home"] / ".claude-sol").mkdir(parents=True)
    p = install(w, "--register-everywhere")
    assert p.returncode == 0, p.stdout + p.stderr
    s = json.loads((w["home"] / ".claude-sol/settings.json").read_text())
    assert commands(s, "PreToolUse") == [GUARD_PRE]


@pytest.mark.parametrize(("cmd", "refused"), [
    ("git push origin main", True), ("git commit -qm x", True), ("bash install.sh", True), ("claude -p x", True),
    ("curl -s https://govuk.ospreyflow.app/", True), ("git status", False), ("ls -la", False),
    ("git commit -qm x  # on another branch", False),
])
def test_register_everywhere_binds_an_unseated_session_in_another_repository_so(world, tmp_path, cmd, refused):
    """What COMMANDS.md tells the owner: the guard's rules for a session with no seat, in a repository not this one."""
    w = world
    other = tmp_path / "another-project"
    other.mkdir()
    sh("git init -q -b main && git commit -q --allow-empty -m init", other, w["env"])
    if "another branch" in cmd:
        sh("git checkout -q -b topic", other, w["env"])
    ev = {"session_id": "owner", "cwd": str(other), "hook_event_name": "PreToolUse", "tool_name": "Bash",
          "tool_input": {"command": cmd}}
    p = subprocess.run([SYSPY, str(w["data"] / "bin/guard.py"), "pre"], input=json.dumps(ev), env=w["env"],
                       capture_output=True, text=True, cwd=str(other))
    assert (p.returncode == 2) is refused, (cmd, p.stderr)
