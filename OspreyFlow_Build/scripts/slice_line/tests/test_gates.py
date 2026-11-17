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
                                             "FULL_GATE = lambda t, b, l: int(os.environ.get('TEST_GATE', '0'))"))
    v062 = repo / "OspreyFlow_Build/process/lanes/v062"
    v062.mkdir(parents=True)
    real = SRC.parents[1] / "process/lanes/v062"
    shutil.copy(real / "dial.yaml", v062 / "dial.yaml")
    shutil.copy(real / "accounts.yaml", v062 / "accounts.yaml")
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
                 w["data"] / "records/S1/verify-abc.json", w["data"] / "bin/guard.py",
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


def merge(w, gate="0"):
    env = {**w["env"], "TEST_GATE": gate}
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
                                  "OspreyFlow_Build/process/lanes/v062/dial.yaml"])
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
printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "@NAME@" "$*" "$PWD" "${VIRTUAL_ENV:-}" \
  "${ARCADEDB_HTTP_PORT:-}/${OSPREY_PORTS_SLOT:-}" "$(node --version 2>/dev/null)" "$(command -v python)" >> "@LOG@"
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
        'jobs:\n  a:\n    steps:\n      - uses: actions/setup-node@v4\n        with: { node-version: "22" }\n'
        '  b:\n    steps:\n      - uses: actions/setup-node@v4\n        with:\n          node-version: "22"\n')
    (tree / "OspreyFlow_Core").mkdir()
    (tree / "OspreyFlow_Build/scripts").mkdir(parents=True)
    (tree / "OspreyFlow_Build/scripts/lane_ports.tsv").write_text("# lane\tslot\nmerger\t13\ncase\t5\n")
    bin_ = t / "fakebin"
    venv_py = 'mkdir -p .venv/bin && cp "$0.python" .venv/bin/python' 
    fake(bin_ / "uv", "uv", calls, f'[ "$1" = sync ] && {venv_py}\nexit 0')
    fake(bin_ / "uv.python", "python", calls, 'echo "$0" >> "' + str(t / "pythons.txt") + '"\nexit 0')
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


def run_gate(g, nodes=("node24", "node22"), fail=""):
    env = dict(g["env"])
    # the caller's shell as on this Mac: the main checkout's venv active and first on PATH
    env["VIRTUAL_ENV"] = str(g["main_venv"].parent)
    env["PATH"] = os.pathsep.join([str(g["main_venv"]), str(g["bin"]), *(str(g[n]) for n in nodes), "/usr/bin", "/bin"])
    env["OSPREY_LANE"] = "case"
    env["FAKE_MAKE_FAIL"] = fail
    log = g["tmp"] / "gate.log"
    code = ("import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); import merge_slice as m; "
            "sys.exit(m.full_gate(Path(sys.argv[2]), 'base', Path(sys.argv[3])))")
    p = subprocess.run([g["py"], "-c", code, str(g["lines"]), str(g["tree"]), str(log)], env=env,
                       capture_output=True, text=True, check=False)
    rows = [ln.split("\t") for ln in g["calls"].read_text().splitlines()] if g["calls"].exists() else []
    calls = [dict(zip(("name", "args", "cwd", "venv", "ports", "node", "python"), r)) for r in rows]
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
