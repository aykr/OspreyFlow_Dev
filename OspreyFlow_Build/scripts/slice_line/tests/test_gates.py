"""Every gate of the slice line, shown refusing a planted violation (rule 15), and letting the ordinary case through.

Each violation takes the shape the gate meets at its real call site: the guard and the stop gate get the JSON a
Claude Code hook gets on stdin and run under /usr/bin/python3, as the hook runs them; the merge, push, board and
start scripts run as subprocesses in a throwaway repository with its own bare origin. Keys and the owner's
address are assembled at run time, so this file holds none of them.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1]
SYSPY = "/usr/bin/python3"
OWNER = "owner" + "@" + "example.test"
KEY_AWS = "AKIA" + "ABCDEFGHIJKLMNOP"
KEY_ANT = "sk-" + "ant-" + "api03-" + "x" * 40
KEY_PEM = "-----BEGIN " + "RSA PRIVATE KEY-----"


def sh(cmd, cwd, env=None, check=True, input=None):
    p = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True, input=input, shell=isinstance(cmd, str))
    if check and p.returncode != 0:
        raise AssertionError(f"{cmd} failed: {p.stdout}\n{p.stderr}")
    return p


# ------------------------------------------------------------------ fixtures


@pytest.fixture
def world(tmp_path):
    """A throwaway repository shaped like this one, its bare origin, a fake home and a fake claude."""
    home = tmp_path / "home"
    data = home / ".ospreyflow" / "slice-line"
    (data / "bin").mkdir(parents=True)
    (data / "records").mkdir()
    for f in ("guard.py", "stop_check.py", "usage_hook.py"):
        shutil.copy(SRC / f, data / "bin" / f)
    (data / "emails.sha256").write_text(hashlib.sha256(OWNER.encode()).hexdigest() + "\n")
    fake_claude = tmp_path / "claude"
    fake_claude.write_text('#!/bin/sh\necho \'{"loggedIn": true}\'\n')
    fake_claude.chmod(0o755)
    env = {**os.environ, "HOME": str(home), "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_AUTHOR_NAME": "t",
           "GIT_AUTHOR_EMAIL": "t@t.invalid", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t.invalid",
           "OSPREY_PUSH_NO_CI_CHECK": "1", "OSPREY_CLAUDE_BIN": str(fake_claude),
           "OSPREY_SLICE_WT_ROOT": str(tmp_path / "wt")}
    for k in ("OSPREY_SLICE_HOME", "OSPREY_SEAT", "OSPREY_SLICE", "OSPREY_SLICE_WORKTREE", "OSPREY_STATUS_FILE"):
        env.pop(k, None)
    origin = tmp_path / "origin.git"
    sh(["git", "init", "-q", "--bare", "-b", "main", str(origin)], tmp_path, env)
    repo = tmp_path / "repo"
    lines = repo / "OspreyFlow_Build/scripts/slice_line"
    shutil.copytree(SRC, lines, ignore=shutil.ignore_patterns("tests", "__pycache__"))
    gate = lines / "merge_slice.py"  # the full gate's stand-in, in this copy only: TEST_GATE's exit code
    gate.write_text(gate.read_text().replace("FULL_GATE = full_gate",
                                             "FULL_GATE = lambda t, b, l: (os.environ.get('TEST_GATE_LOG') and "
                                             "l.open('a').write(open(os.environ['TEST_GATE_LOG']).read()) and 0) or "
                                             "(os.environ.get('TEST_LIVE_NOTE') and "
                                             "l.with_suffix('.live.json').write_text(os.environ['TEST_LIVE_NOTE']) and 0) "
                                             "or int(os.environ.get('TEST_GATE', '0'))"))
    v062 = repo / "OspreyFlow_Build/process/lanes/v062"
    v062.mkdir(parents=True)
    real = SRC.parents[1] / "process/lanes/v062"
    shutil.copy(real / "dial.yaml", v062 / "dial.yaml")
    shutil.copy(real / "accounts.yaml", v062 / "accounts.yaml")
    shutil.copy(real / "live_step.yaml", v062 / "live_step.yaml")
    (v062 / "slices.tsv").write_text(
        "id\tbuild\twhat\tafter\ttrack\tbranch\tenv\tacceptance_files\tacceptance\tchecks\n"
        "S1\tCO1\tA test slice\t-\t1\t-\tnone\taccept.sh\tsh accept.sh\ttrue\n"
        "S2\tZZ9\tNot in the plan\t-\t1\t-\tnone\taccept2.sh\tsh accept2.sh\ttrue\n")
    (repo / "OspreyFlow_Core").mkdir()
    (repo / "OspreyFlow_Core/Makefile").write_text("all:\n")
    (repo / "OspreyFlow_Core/osprey.yaml").write_text("a: 1\n")
    (repo / "OspreyFlow_Build/Makefile").write_text("ci:\n")
    (repo / ".github/workflows").mkdir(parents=True)
    (repo / ".github/workflows/ci.yml").write_text("on: push\n")
    (repo / ".claude").mkdir()
    (repo / ".claude/settings.json").write_text("{}\n")
    (repo / "README.md").write_text("x\n")
    (repo / ".gitignore").write_text("Claude outputs/\n")
    dash = repo / "Claude outputs/ospreyflow_build_plan_2026-11-17/dashboard"
    dash.mkdir(parents=True)
    (dash / "index.html").write_text('const N=[\n["BL1",9,1,"None","x",[],""],\n["CO1",6,1,"None","y",["BL2"],""]\n];')
    sh("git init -q -b main && git add -A && git commit -q -m init", repo, env)
    sh(["git", "remote", "add", "origin", str(origin)], repo, env)
    sh("git push -q origin main", repo, env)
    (data / "origin.url").write_text(str(origin) + "\n")
    (repo / "OspreyFlow_Core/osprey.yaml").write_text("a: 2\n")  # the owner's local change, as on this Mac
    return {"tmp": tmp_path, "home": home, "data": data, "repo": repo, "origin": origin, "env": env,
            "lines": lines, "py": sys.executable}


def guard(w, tool, tool_input, cwd=None, seat=None, wt=None, mode="pre", event=None):
    env = dict(w["env"])
    if seat:
        env["OSPREY_SEAT"] = seat
    if wt:
        env["OSPREY_SLICE_WORKTREE"] = str(wt)
    ev = event or {"session_id": "s", "cwd": str(cwd or w["repo"]), "hook_event_name": "PreToolUse",
                   "tool_name": tool, "tool_input": tool_input}
    p = subprocess.run([SYSPY, str(w["data"] / "bin/guard.py"), mode], input=json.dumps(ev), env=env,
                       capture_output=True, text=True)
    return p


def refused(p):
    return p.returncode == 2 and "Slice line guard refused" in p.stderr


def bash(w, cmd, **kw):
    return guard(w, "Bash", {"command": cmd}, **kw)


# ------------------------------------------------------------------ guard: the owner's files


def test_edits_to_the_core_makefile_and_ci_yml_are_refused(world):
    w = world
    assert refused(guard(w, "Edit", {"file_path": str(w["repo"] / "OspreyFlow_Core/Makefile"), "old_string": "a", "new_string": "b"}))
    assert refused(guard(w, "Write", {"file_path": str(w["repo"] / ".github/workflows/ci.yml"), "content": "x"}))
    assert refused(bash(w, "sed -i '' 's/all/x/' Makefile", cwd=w["repo"] / "OspreyFlow_Core"))
    assert refused(bash(w, "printf x >> OspreyFlow_Core/Makefile"))
    assert refused(bash(w, "python3 -c \"open('.github/workflows/ci.yml','w').write('x')\""))
    # not a blanket refusal: the Build Makefile, and reading the Core one, go through
    assert guard(w, "Edit", {"file_path": str(w["repo"] / "OspreyFlow_Build/Makefile"), "old_string": "a", "new_string": "b"}).returncode == 0
    assert bash(w, "cat OspreyFlow_Core/Makefile | head -3").returncode == 0


def test_staging_osprey_yaml_or_data_is_refused(world):
    w = world
    sh("git checkout -q -b lane/x", w["repo"], w["env"])
    (w["repo"] / "OspreyFlow_Core/data").mkdir()
    (w["repo"] / "OspreyFlow_Core/data/real.csv").write_text("x\n")
    for cmd in ("git add -A", "git add .", "git add OspreyFlow_Core/osprey.yaml", "git commit -am wip",
                "git add OspreyFlow_Core/data/real.csv", "cd OspreyFlow_Core && git add osprey.yaml"):
        assert refused(bash(w, cmd)), cmd
    assert bash(w, "git add README.md").returncode == 0


# ------------------------------------------------------------------ guard: pushing, remotes, repositories


def test_push_new_remotes_and_visibility_changes_are_refused(world):
    w = world
    for cmd in ("git push origin main", "git push", "git -C . push backup lane/x", "git push --force origin main",
                "git remote add evil https://example.invalid/x.git", "git remote set-url origin https://example.invalid/y",
                "gh repo create mine --public", "gh repo edit --visibility public",
                "gh api -X PATCH repos/o/r -f private=false",
                "bash OspreyFlow_Build/scripts/slice_line/push_main.sh"):
        assert refused(bash(w, cmd)), cmd
    assert bash(w, "git fetch -q origin").returncode == 0


# ------------------------------------------------------------------ guard: a builder outside its worktree


def test_a_builder_cannot_edit_outside_its_own_worktree(world):
    w = world
    wt = w["tmp"] / "wt" / "slice-S1"
    sh(["git", "worktree", "add", "-q", "-b", "lane/slice-S1", str(wt), "main"], w["repo"], w["env"])
    other = w["tmp"] / "wt" / "slice-S9"
    sh(["git", "worktree", "add", "-q", "-b", "lane/slice-S9", str(other), "main"], w["repo"], w["env"])
    b = {"seat": "builder", "wt": wt, "cwd": wt}
    assert refused(guard(w, "Write", {"file_path": str(w["repo"] / "README.md"), "content": "x"}, **b))
    assert refused(guard(w, "Edit", {"file_path": str(other / "README.md"), "old_string": "x", "new_string": "y"}, **b))
    assert refused(bash(w, f"cd {w['repo']} && echo x > README.md", **b))
    assert refused(bash(w, f"echo x > {other}/README.md", **b))
    assert refused(bash(w, f"git -C {w['repo']} status", **b))
    assert refused(bash(w, "GIT_DIR=../repo/.git git log", **b))
    assert refused(bash(w, "git checkout main", **b))
    assert refused(bash(w, "git switch -c elsewhere", **b))
    # its own worktree, a temporary folder and a program run by absolute path are fine
    assert guard(w, "Write", {"file_path": str(wt / "new.py"), "content": "x = 1\n"}, **b).returncode == 0
    assert bash(w, "echo x > notes.txt && git add notes.txt && git commit -qm 'feat: x'", **b).returncode == 0
    assert bash(w, f"{SYSPY} -c 'print(1)' > /tmp/slice-out.txt", **b).returncode == 0
    assert bash(w, "git checkout -- README.md", **b).returncode == 0


# ------------------------------------------------------------------ guard: main


def test_nothing_writes_main_but_the_merge_script(world):
    w = world
    for cmd in ("git commit -m x", "git merge lane/x", "git reset --hard HEAD~1", "git cherry-pick abc",
                "git pull", "cd OspreyFlow_Build && git commit -m x"):
        assert refused(bash(w, cmd)), cmd
    wt = w["tmp"] / "wt" / "slice-S1"
    sh(["git", "worktree", "add", "-q", "-b", "lane/slice-S1", str(wt), "main"], w["repo"], w["env"])
    for cmd in ("git update-ref refs/heads/main HEAD", "git branch -f main HEAD", "git fetch . HEAD:main",
                "git checkout -B main"):
        assert refused(bash(w, cmd, cwd=wt)), cmd
    assert bash(w, "git commit --allow-empty -qm 'chore: on a lane'", cwd=wt).returncode == 0
    script = f"{w['py']} OspreyFlow_Build/scripts/slice_line/merge_slice.py merge S1"
    assert bash(w, script).returncode == 0
    assert refused(bash(w, script + " && git commit -m x"))
    assert refused(bash(w, script, seat="builder", wt=wt, cwd=wt))


# ------------------------------------------------------------------ guard: credentials and the owner's address


def test_a_credential_or_the_owners_address_is_refused_in_files_commands_and_messages(world):
    w = world
    for content in (KEY_AWS, KEY_ANT, KEY_PEM, "AIza" + "B" * 35, "password = 'Zx81" + "q" * 22 + "'"):
        assert refused(guard(w, "Write", {"file_path": str(w["repo"] / "x.txt"), "content": content})), content[:8]
    assert refused(guard(w, "Write", {"file_path": str(w["repo"] / "x.md"), "content": "Contact " + OWNER.upper()}))
    assert refused(bash(w, f"git commit -qm 'thanks {OWNER}'"))
    assert refused(guard(w, "SendMessage", {"to": "conductor", "message": "key is " + KEY_ANT}))
    assert refused(guard(w, "mcp__claude_ai_Claude_Docs__batch", {"batch": [{"text": OWNER}]}))
    stop = guard(w, None, None, mode="stop", event={"session_id": "s", "hook_event_name": "Stop",
                                                    "last_assistant_message": "Done. Mail " + OWNER})
    assert json.loads(stop.stdout)["decision"] == "block"
    # a synthetic fixture address and the dev stack's short password are not the owner's and not keys
    assert guard(w, "Write", {"file_path": str(w["repo"] / "f.json"), "content": "analyst@example.org playwithdata123"}).returncode == 0
    assert guard(w, None, None, mode="stop", event={"last_assistant_message": "All green."}).stdout == ""


# ------------------------------------------------------------------ guard: the GOV.UK demo and airbyte


def test_the_govuk_demo_and_airbyte_are_refused(world):
    w = world
    for cmd in ("ssh ospreyflow-test docker ps --filter name=osprey-small", "curl -s https://govuk.ospreyflow.app/healthz",
                "ssh ospreyflow-test 'cd /opt/ospreyflow-v0.6.0 && ospreyflow status'", "curl -s localhost:8000/api/v1/health",
                "docker logs airbyte-abctl-control-plane", "abctl local status", "docker run -p 8000:8000 x",
                "ssh ospreyflow-test docker restart osprey-test-b-pg"):
        assert refused(bash(w, cmd)), cmd
    assert refused(guard(w, "WebFetch", {"url": "https://govuk.ospreyflow.app/", "prompt": "x"}))
    assert refused(guard(w, "mcp__playwright__browser_navigate", {"url": "http://127.0.0.1:8000/"}))
    assert bash(w, "curl -s localhost:8090/healthz").returncode == 0
    assert bash(w, "OspreyFlow_Build/scripts/stack_lease.sh offline case -- make -k test SKIP_JS=1").returncode == 0


# ------------------------------------------------------------------ guard: the line protects itself


def test_the_line_its_records_settings_and_owner_files_are_refused(world):
    w = world
    v062 = w["repo"] / "OspreyFlow_Build/process/lanes/v062"
    for path in (w["repo"] / ".claude/settings.json", w["lines"] / "guard.py", v062 / "dial.yaml", v062 / "accounts.yaml",
                 v062 / "live_step.yaml", w["data"] / "records/S1/verify-abc.json", w["data"] / "bin/guard.py",
                 w["repo"] / "Claude outputs/ospreyflow_build_plan_2026-11-17/dashboard/status.js"):
        assert refused(guard(w, "Write", {"file_path": str(path), "content": "x"})), path
    for cmd in (f"echo '{{}}' > {w['data']}/records/S1/verify-abc.json", "echo x > OspreyFlow_Build/process/lanes/v062/dial.yaml",
                f"OSPREY_SLICE_HOME=/tmp/forged {w['py']} OspreyFlow_Build/scripts/slice_line/merge_slice.py merge S1",
                f"{w['py']} OspreyFlow_Build/scripts/slice_line/refreeze.py S1", "bash OspreyFlow_Build/scripts/slice_line/install.sh",
                "claude -p 'do it'", "CLAUDE_CONFIG_DIR=~/.claude-sol ~/.local/bin/claude -p x",
                "claude --settings '{\"disableAllHooks\": true}' -p x"):
        assert refused(bash(w, cmd)), cmd


def test_read_only_seats_and_the_conductor_are_confined(world):
    w = world
    for seat in ("verifier", "scout"):
        assert refused(guard(w, "Write", {"file_path": "/tmp/x.txt", "content": "x"}, seat=seat))
        assert refused(bash(w, "pytest -q", seat=seat))
        assert refused(bash(w, "git diff main && rm -rf x", seat=seat))
    assert bash(w, "git diff main...HEAD", seat="verifier").returncode == 0
    v062 = w["repo"] / "OspreyFlow_Build/process/lanes/v062"
    assert refused(guard(w, "Write", {"file_path": str(w["repo"] / "OspreyFlow_Core/services/x.py"), "content": "x"}, seat="conductor"))
    assert refused(bash(w, "echo x > OspreyFlow_Core/services/x.py", seat="conductor"))
    assert guard(w, "Write", {"file_path": str(v062 / "slices/S1.md"), "content": "# S1\n"}, seat="conductor").returncode == 0


def test_the_guard_fails_closed(world):
    p = guard(world, "Bash", ["not", "an", "object"])
    assert refused(p) and "the guard failed" in p.stderr


# ------------------------------------------------------------------ a builder cannot stop on red


def stop_gate(w, wt, slice_id="S1"):
    env = {**w["env"], "OSPREY_SEAT": "builder", "OSPREY_SLICE": slice_id, "OSPREY_SLICE_WORKTREE": str(wt)}
    ev = {"session_id": "b1", "hook_event_name": "Stop", "stop_hook_active": False, "last_assistant_message": "done"}
    p = subprocess.run([SYSPY, str(w["data"] / "bin/stop_check.py")], input=json.dumps(ev), env=env,
                       capture_output=True, text=True, cwd=str(wt))
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout) if p.stdout.strip() else None


def started(w, slice_id="S1"):
    p = sh([w["py"], str(w["lines"] / "slice_start.py"), slice_id], w["repo"], w["env"], check=False)
    return p, w["tmp"] / "wt" / f"slice-{slice_id}"


def test_a_red_builder_cannot_stop_and_gets_the_failures_only(world):
    w = world
    p, wt = started(w)
    assert p.returncode == 0, p.stdout + p.stderr
    checks = "\n".join([f"echo 'tests/test_a.py::test_{i} PASSED'" for i in range(200)] +
                       ["echo 'FAILED tests/test_a.py::test_planted - AssertionError: the planted fault'", "exit 1"])
    (wt / "accept.sh").write_text(checks + "\n")
    sh("git add accept.sh && git commit -qm 'test: red'", wt, w["env"])
    out = stop_gate(w, wt)
    assert out and out["decision"] == "block"
    assert "the planted fault" in out["reason"] and "PASSED" not in out["reason"]
    (wt / "accept.sh").write_text("exit 0\n")
    out = stop_gate(w, wt)  # uncommitted work is red too
    assert out and "uncommitted" in out["reason"]
    sh("git commit -qam 'feat: green'", wt, w["env"])
    assert stop_gate(w, wt) is None
    tip = sh("git rev-parse HEAD", wt).stdout.strip()
    rec = json.loads((w["data"] / f"records/S1/tests-{tip}.json").read_text())
    assert rec["green"] and rec["commit"] == tip


def test_a_builder_red_six_times_is_let_go_as_stopped_never_green(world):
    w = world
    p, wt = started(w)
    (wt / "accept.sh").write_text("echo 'FAILED x'; exit 1\n")
    sh("git add accept.sh && git commit -qm 'test: red'", wt, w["env"])
    for _ in range(5):
        assert stop_gate(w, wt)["decision"] == "block"
    assert stop_gate(w, wt) is None
    assert json.loads((w["data"] / "records/S1/red_stop.json").read_text())["red_stops"] == 6
    tip = sh("git rev-parse HEAD", wt).stdout.strip()
    assert not (w["data"] / f"records/S1/tests-{tip}.json").exists()


# ------------------------------------------------------------------ the merge script


def verified(w, wt, tip, transcript_names_tip=True):
    t = w["tmp"] / "transcript.jsonl"
    t.write_text(json.dumps({"type": "assistant", "text": f"pass {tip if transcript_names_tip else 'x'}"}) + "\n")
    (w["data"] / f"records/S1/verify-{tip}.json").write_text(json.dumps({
        "slice": "S1", "commit": tip, "verdict": "pass",
        "passes": [{"pass": "acceptance", "verdict": "pass", "commit": tip, "session": "v-1", "transcript": str(t)}]}))


def built(w, accept="test -f feature.txt", feature=True, extra=None):
    p, wt = started(w)
    assert p.returncode == 0, p.stdout + p.stderr
    (wt / "accept.sh").write_text(accept + "\n")
    sh("git add accept.sh && git commit -qm 'test: S1 acceptance, red'", wt, w["env"])
    if feature:
        (wt / "feature.txt").write_text("done\n")
    for path, text in (extra or {}).items():
        (wt / path).parent.mkdir(parents=True, exist_ok=True)
        (wt / path).write_text(text)
    sh("git add -A . ':!OspreyFlow_Core/osprey.yaml' && git commit -q --allow-empty -m 'feat: S1'", wt, w["env"])
    return wt, sh("git rev-parse HEAD", wt).stdout.strip()


def merge(w, gate="0", live_note="", gate_log=""):
    env = {**w["env"], "TEST_GATE": gate, "TEST_LIVE_NOTE": live_note, "TEST_GATE_LOG": gate_log}
    p = sh([w["py"], str(w["lines"] / "merge_slice.py"), "merge", "S1"], w["repo"], env, check=False)
    return p


def main_sha(w):
    return sh("git rev-parse main", w["repo"]).stdout.strip()


def test_the_merge_script_refuses_a_branch_with_no_verifier_record(world):
    w = world
    wt, tip = built(w)
    before = main_sha(w)
    p = merge(w)
    assert p.returncode == 1 and "no verifier record" in p.stderr and main_sha(w) == before


def test_the_merge_script_refuses_a_record_for_an_older_commit(world):
    w = world
    wt, tip = built(w)
    verified(w, wt, tip)
    (wt / "more.txt").write_text("x\n")
    sh("git add more.txt && git commit -qm 'feat: more'", wt, w["env"])
    before = main_sha(w)
    p = merge(w)
    assert p.returncode == 1 and "no verifier record" in p.stderr and main_sha(w) == before


def test_the_merge_script_refuses_a_verifier_that_never_saw_the_commit(world):
    w = world
    wt, tip = built(w)
    verified(w, wt, tip, transcript_names_tip=False)
    p = merge(w)
    assert p.returncode == 1 and "never names" in p.stderr


def test_the_merge_script_refuses_a_red_branch(world):
    w = world
    wt, tip = built(w, feature=False)  # the acceptance test is still red at the tip
    verified(w, wt, tip)
    before = main_sha(w)
    p = merge(w)
    assert p.returncode == 1 and "acceptance is red on the merge result" in p.stderr and main_sha(w) == before


def test_the_merge_script_refuses_an_acceptance_test_that_was_never_red(world):
    w = world
    wt, tip = built(w, accept="true")
    verified(w, wt, tip)
    p = merge(w)
    assert p.returncode == 1 and "never red" in p.stderr


def test_the_merge_script_refuses_when_the_full_gate_is_red(world):
    w = world
    wt, tip = built(w)
    verified(w, wt, tip)
    before = main_sha(w)
    p = merge(w, gate="2")
    assert p.returncode == 1 and "full gate is red" in p.stderr and main_sha(w) == before


@pytest.mark.parametrize("path", ["OspreyFlow_Core/Makefile", ".github/workflows/ci.yml", "OspreyFlow_Core/data/x.csv",
                                  ".claude/agents/x.md", "OspreyFlow_Build/scripts/slice_line/guard.py",
                                  "OspreyFlow_Build/process/lanes/v062/dial.yaml",
                                  "OspreyFlow_Build/process/lanes/v062/live_step.yaml"])
def test_the_merge_script_refuses_a_branch_touching_a_protected_path(world, path):
    w = world
    wt, tip = built(w, extra={path: "changed\n"})
    verified(w, wt, tip)
    p = merge(w)
    assert p.returncode == 1 and "protected paths" in p.stderr and path in p.stderr


def test_the_merge_script_refuses_a_changed_frozen_command(world):
    w = world
    wt, tip = built(w)
    verified(w, wt, tip)
    tsv = w["repo"] / "OspreyFlow_Build/process/lanes/v062/slices.tsv"
    tsv.write_text(tsv.read_text().replace("sh accept.sh\ttrue", "true\ttrue"))
    sh("git commit -qam 'docs: loosen S1' --trailer 'Slice-Records: yes'", w["repo"], w["env"])
    p = merge(w)
    assert p.returncode == 1 and "no longer matches its frozen" in p.stderr


def test_the_merge_script_holds_one_merge_at_a_time(world):
    w = world
    wt, tip = built(w)
    verified(w, wt, tip)
    with (w["data"] / "merge.lock").open("w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        p = merge(w)
    assert p.returncode == 1 and "another merge is running" in p.stderr


def test_a_verified_green_slice_merges_pushes_and_shows_done_with_evidence(world):
    w = world
    wt, tip = built(w)
    verified(w, wt, tip)
    p = merge(w)
    assert p.returncode == 0, p.stderr
    done = json.loads(p.stdout)
    assert main_sha(w) == done["merge"]
    assert sh(["git", "ls-remote", str(w["origin"]), "refs/heads/main"], w["repo"]).stdout.split()[0] == done["merge"]
    assert done["push"]["exit"] == 0
    status = (w["repo"] / "Claude outputs/ospreyflow_build_plan_2026-11-17/dashboard/status.js").read_text()
    body = json.loads(status.split("window.OSPREY_STATUS = ", 1)[1].rstrip().rstrip(";"))
    co1 = body["builds"]["CO1"]
    assert co1["state"] == "done" and done["merge"][:7] in co1["evidence"] and done["acceptance_run"] in co1["evidence"]


def test_records_mode_commits_only_the_records_folder_and_never_the_owners_files(world):
    w = world
    v062 = w["repo"] / "OspreyFlow_Build/process/lanes/v062"
    rec = [w["py"], str(w["lines"] / "merge_slice.py"), "records", "-m", "docs(process): note"]
    (w["repo"] / "README.md").write_text("changed\n")
    p = sh(rec + ["README.md"], w["repo"], w["env"], check=False)
    assert p.returncode == 1 and "only OspreyFlow_Build/process/lanes/v062/" in p.stderr
    sh("git checkout -- README.md", w["repo"])
    (v062 / "dial.yaml").write_text("current: sprint\n")
    p = sh(rec + ["OspreyFlow_Build/process/lanes/v062/dial.yaml"], w["repo"], w["env"], check=False)
    assert p.returncode == 1 and "owner's file" in p.stderr
    sh("git checkout -- OspreyFlow_Build/process/lanes/v062/dial.yaml", w["repo"])
    (v062 / "NOTES.md").write_text("a note\n")
    p = sh(rec + ["OspreyFlow_Build/process/lanes/v062/NOTES.md"], w["repo"], w["env"], check=False)
    assert p.returncode == 0, p.stderr
    assert "Slice-Records: yes" in sh("git log -1 --format=%B", w["repo"]).stdout


# ------------------------------------------------------------------ the push script


def test_the_push_script_refuses_anything_but_a_merge_written_main_to_origin(world):
    w = world
    push = str(w["lines"] / "push_main.sh")
    sh("git commit -q --allow-empty -m 'hand commit'", w["repo"], w["env"])
    p = sh([push], w["repo"], w["env"], check=False)
    assert p.returncode == 2 and "not written by the merge script" in p.stdout
    sh("git commit -q --allow-empty -m 'm' --trailer 'Slice-Merge: S1'", w["repo"], w["env"])
    sh(["git", "remote", "set-url", "origin", str(w["tmp"] / "elsewhere.git")], w["repo"], w["env"])
    p = sh([push], w["repo"], w["env"], check=False)
    assert p.returncode == 2 and "not the recorded remote" in p.stdout
    sh(["git", "remote", "set-url", "origin", str(w["origin"])], w["repo"], w["env"])
    sh("git checkout -q -b lane/x", w["repo"], w["env"])
    p = sh([push], w["repo"], w["env"], check=False)
    assert p.returncode == 2 and "not on main" in p.stdout


# ------------------------------------------------------------------ the board and the status file


def board_module(w):
    env = {**w["env"]}
    code = ("import sys, json; sys.path.insert(0, %r); import board as b\n" % str(w["lines"]))
    return env, code


def run_py(w, code):
    return subprocess.run([w["py"], "-c", code], env=w["env"], cwd=str(w["repo"]), capture_output=True, text=True)


def test_the_status_file_refuses_done_without_its_evidence(world):
    w = world
    _, head = board_module(w)
    cases = {
        "no merge record": "b.entry('done', evidence='commit abc1234')",
        "no verifier pass": "b.entry('done', evidence='commit abc1234; test run m.log', merged={'merge':'abc1234ff','tip':'t','acceptance_run':'m.log'}, verify=None)",
        "evidence without the run": "b.entry('done', evidence='commit abc1234', merged={'merge':'abc1234ff','tip':'t','acceptance_run':'m.log'}, verify={'verdict':'pass','commit':'t'})",
        "stopped with no decision": "b.entry('stopped')",
        "an unknown state": "b.entry('ready')",
    }
    for why, call in cases.items():
        p = run_py(w, head + call)
        assert p.returncode != 0 and "BadEntry" in p.stderr, why
    ok = run_py(w, head + "print(b.entry('done', evidence='commit abc1234 on main; test run m.log', merged={'merge':'abc1234ff','tip':'t','acceptance_run':'m.log'}, verify={'verdict':'pass','commit':'t'})['state'])")
    assert ok.stdout.strip() == "done", ok.stderr


def test_a_forged_done_never_reaches_the_status_file(world):
    """A merge record with no verifier pass behind it: the board reports it and leaves the build out."""
    w = world
    wt, tip = built(w)
    (w["data"] / "records/S1/merged.json").write_text(json.dumps({"merge": tip, "tip": tip, "acceptance_run": "m.log"}))
    p = sh([w["py"], str(w["lines"] / "board.py")], w["repo"], w["env"], check=False)
    assert "not shown as done" in p.stderr
    status = (w["repo"] / "Claude outputs/ospreyflow_build_plan_2026-11-17/dashboard/status.js").read_text()
    assert '"state": "done"' not in status


@pytest.mark.parametrize(("name", "body", "said"), [
    # the dry run's shape (17 November 2026): a merge record with no acceptance_run stopped the whole board
    ("merged.json", '{"merge": "@TIP@", "tip": "@TIP@"}', "merge record skipped"),
    ("merged.json", '{"merge": ', "merged.json is unreadable"),
    ("merged.json", '["@TIP@"]', "merged.json is not a JSON object"),
    ("state.json", "not json", "state.json is unreadable"),
    ("frozen.json", '{"branch": 5}', "its records could not be read"),
], ids=["merge-record-incomplete", "merge-record-not-json", "merge-record-a-list", "state-not-json",
        "frozen-branch-not-a-name"])
def test_a_bad_or_incomplete_record_is_skipped_and_reported_and_the_board_goes_on(world, name, body, said):
    w = world
    wt, tip = built(w)
    rec = w["data"] / "records/S1" / name
    status_file = w["repo"] / "Claude outputs/ospreyflow_build_plan_2026-11-17/dashboard/status.js"

    def board():
        p = sh([w["py"], str(w["lines"] / "board.py")], w["repo"], w["env"], check=False)
        rows = {ln.split()[0]: ln for ln in p.stdout.splitlines() if ln.startswith(("S1 ", "S2 "))}
        builds = status_file.read_text().split('"builds":', 1)[1] if status_file.exists() else ""
        return p, rows, builds

    kept = rec.read_bytes() if rec.exists() else None
    if kept is not None:
        rec.unlink()
    _, without_rows, without_builds = board()  # the board with that record simply absent
    if kept is not None:
        rec.write_bytes(kept)
    rec.write_text(body.replace("@TIP@", tip))
    p, rows, builds = board()
    assert p.returncode == 0 and "Traceback" not in p.stderr, p.stderr
    assert "REPORT TO OWNER: S1: " in p.stderr and said in p.stderr, p.stderr
    assert "S2" in rows, rows                        # every other slice still on the board
    assert '"state": "done"' not in builds
    if name == "frozen.json":                        # nothing of S1 can be read: shown as such, nothing written
        assert "records unreadable" in rows["S1"] and '"CO1"' not in builds, (rows, builds)
    else:                                            # skipped: S1 shown from its other records, as without it
        assert rows["S1"] == without_rows["S1"] and builds.split('"updated"')[0] == without_builds.split('"updated"')[0]


def test_a_slice_whose_build_id_is_not_in_the_plan_is_reported_not_started(world):
    p, _ = started(world, "S2")
    assert p.returncode != 0 and "REPORT TO OWNER" in (p.stdout + p.stderr)
    assert not (world["data"] / "records/S2").exists()


def test_the_status_file_is_written_whole_with_a_rename(world):
    src = (SRC / "board.py").read_text()
    assert "os.replace(tmp, path)" in src and "tmp.write_text(text)" in src


# ------------------------------------------------------------------ the dial and the accounts


def test_no_gate_reads_the_dial(world):
    for f in ("guard.py", "stop_check.py", "merge_slice.py", "push_main.sh", "usage_hook.py"):
        text = (SRC / f).read_text()
        assert "dial" not in text.replace("dial.yaml", ""), f
        assert "seat_settings" not in text and "current_setting" not in text, f


@pytest.mark.parametrize("setting", ["thrift", "balanced", "sprint"])
def test_every_dial_setting_meets_the_same_merge_gate(world, setting):
    w = world
    dial = w["repo"] / "OspreyFlow_Build/process/lanes/v062/dial.yaml"
    dial.write_text(dial.read_text().replace("current: auto", f"current: {setting}"))
    wt, tip = built(w)
    p = merge(w)
    assert p.returncode == 1 and "no verifier record" in p.stderr


def test_an_account_near_its_limit_starts_no_new_slice(world):
    w = world
    acc = w["data"] / "accounts"
    acc.mkdir()
    (acc / "default.json").write_text(json.dumps({"windows": {"seven_day": {"utilization": 0.97, "resetsAt": 4102444800}}}))
    p, _ = started(w)
    assert p.returncode != 0 and "97% of its seven-day limit" in (p.stdout + p.stderr)
    assert not (w["data"] / "records/S1/frozen.json").exists()


def test_a_signed_out_account_starts_nothing(world):
    w = world
    Path(w["env"]["OSPREY_CLAUDE_BIN"]).write_text('#!/bin/sh\necho \'{"loggedIn": false}\'\n')
    p, _ = started(w)
    assert p.returncode != 0 and "signed out" in (p.stdout + p.stderr)


def test_the_accounts_file_holds_names_only():
    text = (SRC.parents[1] / "process/lanes/v062/accounts.yaml").read_text()
    assert "@" not in text and "sk-" not in text and "token:" not in text


def test_a_seat_refuses_to_start_without_the_guard(world):
    w = world
    p, _ = started(w)
    assert p.returncode == 0, p.stdout + p.stderr
    run = [w["py"], str(w["lines"] / "run_seat.py"), "builder", "S1"]
    out = sh(run, w["repo"], w["env"], check=False)  # nothing installed: no manifest
    assert out.returncode == 3 and "the guard is not installed" in out.stderr
    data = w["data"]
    m = {f: hashlib.sha256((data / "bin" / f).read_bytes()).hexdigest() for f in ("guard.py", "stop_check.py", "usage_hook.py")}
    (data / "manifest.json").write_text(json.dumps(m))
    (data / "bin/guard.py").write_text("import sys; sys.exit(0)\n")  # a guard that refuses nothing
    out = sh(run, w["repo"], w["env"], check=False)
    assert out.returncode == 3 and "differs from the install manifest" in out.stderr


# ------------------------------------------------------------------ the full gate itself (not its stand-in)
# The merge cases above replace FULL_GATE with TEST_GATE's exit code. These run the real full_gate, in a
# subprocess as merge_slice.py runs it, against fake uv, npm, node and make that record what they were given:
# the arguments, the folder, VIRTUAL_ENV, the ports and slot, the node and python a bare call would reach.

FAKE = r'''#!/bin/sh
printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "@NAME@" "$*" "$PWD" "${VIRTUAL_ENV:-}" \
  "${ARCADEDB_HTTP_PORT:-}/${OSPREY_PORTS_SLOT:-}" "$(node --version 2>/dev/null)" "$(command -v python)" \
  "${UV_PYTHON:-}" >> "@LOG@"
@EXTRA@
'''


def fake(path, name, log, extra=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(FAKE.replace("@NAME@", name).replace("@LOG@", str(log)).replace("@EXTRA@", extra))
    path.chmod(0o755)


@pytest.fixture
def gate(world):
    """A merge tree shaped like this repository's, CI's Node 22 and a Node 24, and the main checkout's own venv."""
    w, t = world, world["tmp"]
    calls = t / "calls.tsv"
    tree = t / "tree"
    (tree / ".github/workflows").mkdir(parents=True)
    (tree / ".github/workflows/ci.yml").write_text(
        'env:\n  UV_PYTHON: "3.12"\njobs:\n  a:\n    steps:\n      - uses: actions/setup-node@v4\n        with: { node-version: "22" }\n'
        '  b:\n    steps:\n      - uses: actions/setup-node@v4\n        with:\n          node-version: "22"\n')
    (tree / "OspreyFlow_Core").mkdir()
    (tree / "OspreyFlow_Build/scripts").mkdir(parents=True)
    (tree / "OspreyFlow_Build/scripts/lane_ports.tsv").write_text("# lane\tslot\nmerger\t13\ncase\t5\n")
    bin_ = t / "fakebin"
    venv_py = 'mkdir -p .venv/bin && cp "$0.python" .venv/bin/python' 
    fake(bin_ / "uv", "uv", calls, f'[ "$1" = sync ] && {venv_py}\nexit 0')
    fake(bin_ / "uv.python", "python", calls,
         '[ "$1" = --version ] && { echo "Python ${FAKE_VENV_PYTHON:-3.12.9}"; exit 0; }\n'
         'echo "$0" >> "' + str(t / "pythons.txt") + '"\n'
         'for f in ${FAKE_LIVE:-}; do echo "$f"; done\nexit 0')
    # the server's run queue, as ssh reads it: FAKE_QUEUE lines, one per check (the last repeats), "first|makes"
    fake(bin_ / "ssh", "ssh", calls,
         'n=$(wc -l < "' + str(t / "ssh.count") + '" 2>/dev/null || echo 0); echo x >> "' + str(t / "ssh.count") + '"\n'
         '[ -n "${FAKE_SSH_EXIT:-}" ] && exit "$FAKE_SSH_EXIT"\n'
         'row=$(printf "%s\\n" ${FAKE_QUEUE:-"|"} | awk -v n="$n" \'{r[NR]=$0} END {print (n+1 <= NR) ? r[n+1] : r[NR]}\')\n'
         'first=${row%%|*}; makes=${row#*|}\n'
         '[ -n "$first" ] && echo "$first"; echo "<<end>>"; [ -n "$makes" ] && echo "$makes"; exit 0')
    lease = w["repo"] / "OspreyFlow_Build/scripts/stack_lease.sh"
    fake(lease, "lease", calls, '[ "$1" = "${FAKE_LEASE_FAIL:-}" ] && exit 1\nexit 0')
    (w["repo"] / "OspreyFlow_Build/scripts/lane_stack_hosts.tsv").write_text("# stack\thost\nb\ttestbox\nc\ttestbox\n")
    shutil.copy(w["repo"] / "OspreyFlow_Build/scripts/lane_stack_hosts.tsv", tree / "OspreyFlow_Build/scripts/")
    # the client names' hashed list: on the main checkout, gitignored; the merge tree is a git checkout without it
    hashes = w["repo"] / "OspreyFlow_Build/marketing_site/client_names.local.sha256"
    hashes.parent.mkdir(parents=True, exist_ok=True)
    hashes.write_text(hashlib.sha256(b"a listed name").hexdigest() + "\n")
    (tree / ".gitignore").write_text("OspreyFlow_Build/marketing_site/client_names.local.sha256\n")
    sh("git init -q -b main && git add -A && git commit -q -m tree", tree, w["env"])
    fake(bin_ / "make", "make", calls, 'case " $* " in *" $FAKE_MAKE_FAIL "*) exit 2;; esac\nexit 0')
    for major in ("22", "24"):
        nb = t / f"node{major}/bin"
        nb.mkdir(parents=True)
        (nb / "node").write_text(f"#!/bin/sh\necho v{major}.1.0\n")
        (nb / "node").chmod(0o755)
        fake(nb / "npm", f"npm{major}", calls, "exit 0")
    main_venv = w["repo"] / "OspreyFlow_Core/.venv/bin"
    fake(main_venv / "python", "MAIN-CHECKOUT-PYTHON", calls, "exit 0")
    return {**w, "tree": tree, "calls": calls, "bin": bin_, "main_venv": main_venv, "pythons": t / "pythons.txt",
            "node22": t / "node22/bin", "node24": t / "node24/bin"}


def run_gate(g, nodes=("node24", "node22"), fail="", venv_python="3.12.9", live="", queue="|", ssh_exit="",
             lease_fail=""):
    env = dict(g["env"])
    # the caller's shell as on this Mac: the main checkout's venv active and first on PATH
    env["VIRTUAL_ENV"] = str(g["main_venv"].parent)
    env["PATH"] = os.pathsep.join([str(g["main_venv"]), str(g["bin"]), *(str(g[n]) for n in nodes), "/usr/bin", "/bin"])
    env["OSPREY_LANE"] = "case"
    env["FAKE_MAKE_FAIL"] = fail
    env["FAKE_VENV_PYTHON"] = venv_python
    env["UV_PYTHON"] = "3.13"  # the caller's own choice, as on this Mac: never the gate's
    env.update(FAKE_LIVE=live, FAKE_QUEUE=queue, FAKE_SSH_EXIT=ssh_exit, FAKE_LEASE_FAIL=lease_fail)
    log = g["tmp"] / "gate.log"
    code = ("import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); import merge_slice as m; "
            "m.QUEUE_POLL_SECONDS = 0.05; sys.exit(m.full_gate(Path(sys.argv[2]), 'base', Path(sys.argv[3])))")
    p = subprocess.run([g["py"], "-c", code, str(g["lines"]), str(g["tree"]), str(log)], env=env,
                       capture_output=True, text=True, check=False)
    rows = [ln.split("\t") for ln in g["calls"].read_text().splitlines()] if g["calls"].exists() else []
    calls = [dict(zip(("name", "args", "cwd", "venv", "ports", "node", "python", "uv_python"), r)) for r in rows]
    return p.returncode, calls, (log.read_text() if log.exists() else "") + p.stderr


def test_the_full_gate_runs_make_ci_and_make_test_in_the_merge_tree(gate):
    rc, calls, out = run_gate(gate)
    assert rc == 0, out
    makes = [(c_["args"], c_["cwd"]) for c_ in calls if c_["name"] == "make"]
    build = str(gate["tree"] / "OspreyFlow_Build")
    assert makes == [("-k ci", build), ("test", build)]


@pytest.mark.parametrize("red", ["test", "ci"])
def test_the_full_gate_is_red_when_only_one_of_make_ci_and_make_test_is_red(gate, red):
    rc, calls, _out = run_gate(gate, fail=red)
    assert rc != 0
    assert [c_["args"] for c_ in calls if c_["name"] == "make"] == ["-k ci", "test"]  # both ran, both reported
    assert "MAIN-CHECKOUT-PYTHON" not in [c_["name"] for c_ in calls]


def test_the_full_gate_builds_its_environment_as_ci_does_never_the_main_checkouts(gate):
    rc, calls, out = run_gate(gate)
    assert rc == 0, out
    core = str(gate["tree"] / "OspreyFlow_Core")
    order = [(c_["name"], c_["args"].split(" ")[0], c_["cwd"]) for c_ in calls]
    assert order[:2] == [("uv", "sync", core), ("npm22", "ci", core)], order
    assert [c_["args"] for c_ in calls if c_["name"] == "uv"] == ["sync --frozen"]  # from the lock, no extras
    assert [c_["uv_python"] for c_ in calls if c_["name"] == "uv"] == ["3.12"]  # CI's Python, not the caller's
    for c_ in calls:
        assert c_["name"] != "MAIN-CHECKOUT-PYTHON", c_
        assert c_["venv"] == "", c_                      # the caller's VIRTUAL_ENV is not carried in
        assert c_["node"] == "v22.1.0", c_               # CI's major, though Node 24 is earlier on PATH
        assert c_["ports"] == "59991/13", c_             # closed ports, the merger's Playwright slot
        assert str(gate["main_venv"]) not in c_["python"], c_
    # live_select ran on the merge tree's own venv
    assert gate["pythons"].read_text().split() == [str(gate["tree"] / "OspreyFlow_Core/.venv/bin/python")]


def test_the_full_gate_refuses_a_node_other_than_cis(gate):
    rc, calls, out = run_gate(gate, nodes=("node24",))
    assert rc == 3 and "no Node 22" in out
    assert not [c_ for c_ in calls if c_["name"] == "make"]


def test_the_full_gate_refuses_a_tree_that_already_has_an_environment(gate):
    (gate["tree"] / "OspreyFlow_Core/.venv/bin").mkdir(parents=True)
    rc, calls, out = run_gate(gate)
    assert rc == 3 and "builds its own, fresh" in out
    assert not [c_ for c_ in calls if c_["name"] == "make"]


# ------------------------------------------------------------------ the verifier's verdict reaches the line
# run_seat.py launches the verifier with --json-schema and reads its verdict from the result's structured_output.
# Claude Code offers that answer through a StructuredOutput tool, and an agent definition's tools list is the
# whole of what its session is offered: without it there, the verifier's "pass" came back as prose only, was
# recorded as "no verdict returned", and stopped the dry run's slice (17 November 2026; shown live with an
# inline agent on Claude Code 2.1.326, both ways).


def test_the_verifier_is_offered_structured_output_for_its_verdict():
    agent = (SRC.parents[2] / ".claude/agents/slice-verifier.md").read_text()
    tools = next(ln for ln in agent.splitlines() if ln.startswith("tools:"))
    assert '"--json-schema"' in (SRC / "run_seat.py").read_text()  # the coupling this case guards
    assert "StructuredOutput" in [t.strip() for t in tools[len("tools:"):].split(",")], tools


def test_the_full_gate_refuses_a_venv_on_another_python_than_cis(gate):
    rc, calls, out = run_gate(gate, venv_python="3.13.4")
    assert rc == 3 and "not CI's Python 3.12" in out
    assert not [c_ for c_ in calls if c_["name"] == "make"]


# ------------------------------------------------------------------ the live step (live_step.yaml, the owner's)
# The dry run's documentation-only slice ran test_route_rights.py on the test server (17 November 2026), through
# live_select's floor alone: the gate now asks for the files the change itself reaches (--reached). The owner turned
# the step off on 18 November 2026; on, it waits for the server's run queue and refuses if it does not clear.

LIVE = "tests/services/api/test_route_rights.py tests/conformance/graph_port/test_suite.py"


def live_step(g, on, wait=0):
    f = g["repo"] / "OspreyFlow_Build/process/lanes/v062/live_step.yaml"
    f.write_text(f"live_step: {'true' if on else 'false'}\nqueue_wait_minutes: {wait}\n")


def lease_calls(calls):
    return [c_["args"].split(" ")[0] for c_ in calls if c_["name"] == "lease"]


def test_the_committed_live_step_is_off():
    import yaml
    data = yaml.safe_load((SRC.parents[1] / "process/lanes/v062/live_step.yaml").read_text())
    assert data["live_step"] is False


def test_a_change_that_reaches_no_live_file_takes_no_stack_and_reads_no_queue(gate):
    live_step(gate, on=True)
    rc, calls, out = run_gate(gate, live="")
    assert rc == 0, out
    asked = [c_["args"] for c_ in calls if c_["name"] == "python" and "live_select" in c_["args"]]
    assert asked == ["-m tools.live_select --base base --reached"], asked  # never the floor's route_rights alone
    assert not lease_calls(calls) and not [c_ for c_ in calls if c_["name"] == "ssh"]
    assert "takes no stack" in out


def test_the_live_step_off_runs_nothing_on_the_server_and_names_what_it_did_not_run(gate):
    live_step(gate, on=False)
    rc, calls, out = run_gate(gate, live=LIVE)
    assert rc == 0, out
    assert not lease_calls(calls) and not [c_ for c_ in calls if c_["name"] == "ssh"]
    assert "LIVE STEP OFF" in out and all(f in out for f in LIVE.split())
    note = json.loads((gate["tmp"] / "gate.live.json").read_text())
    assert note == {"live_step": "off", "not_run": LIVE.split()}


def test_the_live_step_on_waits_for_the_queue_then_runs_under_the_lease(gate):
    live_step(gate, on=True, wait=1)
    rc, calls, out = run_gate(gate, live=LIVE, queue="demo| |4242 merger|")
    assert rc == 0, out
    names = [c_["name"] for c_ in calls if c_["name"] in ("ssh", "lease")]
    assert names[:3] == ["ssh", "ssh", "ssh"] and "lease" not in names[:3], names  # two waits, then clear
    assert lease_calls(calls) == ["acquire", "up", "live", "down", "release"]
    assert out.count("Waiting for the server's run queue") == 2


@pytest.mark.parametrize(("queue", "ssh_exit", "said"), [
    ("demo|", "", "has 'demo' first"),
    ("|4242", "", "make is running there"),
    ("|", "255", "could not be read"),
])
def test_the_live_step_on_refuses_when_the_queue_does_not_clear(gate, queue, ssh_exit, said):
    live_step(gate, on=True, wait=0)
    rc, calls, out = run_gate(gate, live=LIVE, queue=queue, ssh_exit=ssh_exit)
    assert rc == 4 and said in out and "did not clear" in out, out
    assert not lease_calls(calls)


@pytest.mark.parametrize("body", ["", "live_step: maybe\n", "live_step: true\nqueue_wait_minutes: soon\n", None])
def test_a_missing_or_unclear_live_step_setting_refuses(gate, body):
    f = gate["repo"] / "OspreyFlow_Build/process/lanes/v062/live_step.yaml"
    if body is None:
        f.unlink()
    else:
        f.write_text(body)
    rc, calls, out = run_gate(gate, live=LIVE)
    assert rc == 3 and "live_step" in out, out
    assert not lease_calls(calls) and not [c_ for c_ in calls if c_["name"] == "ssh"]


def test_a_merge_with_the_live_step_off_records_the_live_files_it_did_not_run(world):
    w = world
    wt, tip = built(w)
    verified(w, wt, tip)
    note = {"live_step": "off", "not_run": ["tests/services/api/test_route_rights.py"]}
    p = merge(w, live_note=json.dumps(note))
    assert p.returncode == 0, p.stderr
    rec = json.loads((w["data"] / "records/S1/merged.json").read_text())
    assert rec["live_step"] == note


# ------------------------------------------------------------------ live tests owed (owed.py)
# The owner, 18 November 2026: with the live step off, each live test not run is owed; the board shows what is owed,
# and a release is refused until every owed live test has run.

OWED_TEST = "tests/services/api/test_route_rights.py"


def owe(w, slice_id, tests, at, merge="m" * 40):
    d = w["data"] / "records" / slice_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "merged.json").write_text(json.dumps({"slice": slice_id, "merge": merge, "at": at,
                                               "live_step": {"live_step": "off", "not_run": tests}}))


def owed_check(w):
    return sh([SYSPY, str(w["lines"] / "owed.py"), "check"], w["repo"], w["env"], check=False)


def test_a_live_test_not_run_is_owed_and_a_release_check_refuses_naming_it(world):
    w = world
    assert owed_check(w).returncode == 0  # nothing merged: nothing owed
    owe(w, "S1", [OWED_TEST], "2026-11-18T09:00:00Z")
    p = owed_check(w)
    assert p.returncode == 1 and OWED_TEST in p.stdout and "A release waits" in p.stderr


def test_the_board_shows_what_is_owed(world):
    w = world
    owe(w, "S1", [OWED_TEST], "2026-11-18T09:00:00Z")
    p = sh([w["py"], str(w["lines"] / "board.py")], w["repo"], w["env"], check=False)
    assert p.returncode == 0, p.stderr
    assert "live tests owed: 1" in p.stdout and OWED_TEST in p.stdout
    status = (w["repo"] / "Claude outputs/ospreyflow_build_plan_2026-11-17/dashboard/status.js").read_text()
    body = json.loads(status.split("window.OSPREY_STATUS = ", 1)[1].rstrip().rstrip(";"))
    assert [o["test"] for o in body["owed_live_tests"]] == [OWED_TEST]


def test_an_unreadable_merge_record_refuses_a_release_rather_than_say_nothing_is_owed(world):
    w = world
    d = w["data"] / "records/S1"
    d.mkdir(parents=True)
    (d / "merged.json").write_text("{not json")
    p = owed_check(w)
    assert p.returncode == 1 and "cannot be read" in p.stderr


def test_the_live_step_on_runs_what_is_owed_and_pays_it_only_when_green(gate):
    g = gate
    live_step(g, on=True)
    owe(g, "S0", ["tests/ingest/test_owed_one.py"], "2026-01-01T09:00:00Z")
    rc, calls, out = run_gate(g, live="", lease_fail="live")  # a documentation-only change, but something is owed
    assert rc != 0
    live = [c_["args"] for c_ in calls if c_["name"] == "lease" and c_["args"].startswith("live")]
    assert live == ["live merger --base base -- ../OspreyFlow_Build/tests/ingest/test_owed_one.py"], live
    assert owed_check(g).returncode == 1  # red: still owed
    g["calls"].unlink()
    shutil.rmtree(g["tree"] / "OspreyFlow_Core/.venv")  # the next merge's tree is a fresh one
    rc, calls, out = run_gate(g, live="")
    assert rc == 0, out
    assert owed_check(g).returncode == 0  # green: paid
    paid = json.loads((g["data"] / "live-paid.json").read_text())
    assert "tests/ingest/test_owed_one.py" in paid


def test_a_test_owed_again_after_it_was_paid_is_owed(world):
    w = world
    owe(w, "S1", [OWED_TEST], "2026-11-18T09:00:00Z")
    (w["data"] / "live-paid.json").write_text(json.dumps({OWED_TEST: {"at": "2026-11-18T10:00:00Z"}}))
    assert owed_check(w).returncode == 0
    owe(w, "S2", [OWED_TEST], "2026-11-18T11:00:00Z")
    p = owed_check(w)
    assert p.returncode == 1 and "slice S2" in p.stdout


# ------------------------------------------------------------------ the client names' hashed list (BL6)
# The owner, 18 November 2026: the merge gate reads the list from the main checkout and refuses the merge if it is
# missing; the list is never committed.

HASHES = "OspreyFlow_Build/marketing_site/client_names.local.sha256"


def test_the_gate_brings_the_hashed_list_from_the_main_checkout_and_never_commits_it(gate):
    rc, calls, out = run_gate(gate)
    assert rc == 0, out
    assert (gate["tree"] / HASHES).read_text() == (gate["repo"] / HASHES).read_text()
    status = sh(["git", "status", "--porcelain", "--untracked-files=all"], gate["tree"], gate["env"]).stdout
    assert "client_names" not in status and "marketing_site" not in status, status  # ignored: git never sees it


@pytest.mark.parametrize("state", ["absent", "empty"])
def test_the_gate_refuses_a_merge_when_the_hashed_list_is_missing(gate, state):
    f = gate["repo"] / HASHES
    f.unlink() if state == "absent" else f.write_text("")
    rc, calls, out = run_gate(gate)
    assert rc == 3 and "hashed list is missing from the main checkout" in out, out
    assert not [c_ for c_ in calls if c_["name"] in ("make", "uv")]


def test_the_gate_refuses_to_copy_the_list_where_git_would_take_it(gate):
    (gate["tree"] / ".gitignore").write_text("")
    rc, calls, out = run_gate(gate)
    assert rc == 3 and "not ignored by git" in out, out
    assert not (gate["tree"] / HASHES).exists()


def test_the_suite_runs_on_its_own_checkouts_venv_never_the_main_checkouts_when_it_has_one(world):
    """`make ci` runs this suite (slice-line-check), so the merge gate runs it in its CI-built tree."""
    w, t = world, world["tmp"]
    log = t / "python.log"

    def venv(root, name):
        b = root / "OspreyFlow_Core/.venv/bin"
        b.mkdir(parents=True, exist_ok=True)
        (b / "python").write_text(f'#!/bin/sh\necho {name} >> "{log}"\n')
        (b / "python").chmod(0o755)

    shutil.copytree(SRC / "tests", w["lines"] / "tests", ignore=shutil.ignore_patterns("__pycache__"))
    sh("git add -A && git commit -q -m suite", w["repo"], w["env"])
    tree = t / "mergetree"
    sh(["git", "worktree", "add", "-q", "--detach", str(tree), "HEAD"], w["repo"], w["env"])
    venv(w["repo"], "MAIN")
    venv(tree, "TREE")
    run = tree / "OspreyFlow_Build/scripts/slice_line/tests/run.sh"
    env = {k: v for k, v in w["env"].items() if k != "SLICE_LINE_PY"}
    sh(["bash", str(run)], tree, env)
    shutil.rmtree(tree / "OspreyFlow_Core/.venv")
    sh(["bash", str(run)], tree, env)
    assert log.read_text().split() == ["TREE", "MAIN"]
