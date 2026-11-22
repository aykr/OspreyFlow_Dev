"""The Mac side, early_warning.py, run as the conductor runs it, against the real runner behind a fake ssh (point 9)."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time

from conftest import early, gate, note, out, setting, sh, ssh_calls

HASHES = "OspreyFlow_Build/marketing_site/client_names.local.sha256"


def records_snapshot(w):
    root = w["data"] / "records"
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns) for p in sorted(root.rglob("*")) if p.is_file()}


def set_state(w, **kw):
    p = w["data"] / "records/S1/state.json"
    st = json.loads(p.read_text())
    st.update(kw)
    p.write_text(json.dumps(st))


# ------------------------------------------------------------------ refusals before anything is sent

def test_an_unverified_slice_is_refused_and_nothing_is_sent(world):
    w = world
    set_state(w, phase="building")
    p = early(w, "S1")
    assert p.returncode == 2 and b"not at verified" in p.stderr
    assert ssh_calls(w) == [] and not note(w).exists()


def test_a_verified_record_for_another_tip_is_refused(world):
    w = world
    set_state(w, tip="0" * 40)
    p = early(w, "S1")
    assert p.returncode == 2 and b"not its branch's tip" in p.stderr and ssh_calls(w) == []


def test_a_missing_setting_file_is_refused_in_words(world):
    w = world
    w["setting"].unlink()
    p = early(w, "S1")
    assert p.returncode == 2 and b"No setting file" in p.stderr and b"never runs without one" in p.stderr
    assert ssh_calls(w) == [] and not note(w).exists()


# ------------------------------------------------------------------ what is sent

def test_the_bundle_carries_main_and_the_slice_tip_and_nothing_else(world):
    w = world
    repo = w["repo"]
    (repo / HASHES).parent.mkdir(parents=True, exist_ok=True)
    (repo / HASHES).write_text("planted-client-hash-list\n")  # gitignored, as on the Mac
    (repo / "untracked.txt").write_text("planted-untracked-file\n")
    (repo / "shared.txt").write_text("planted-uncommitted-change\n")
    p = early(w, "S1")
    assert p.returncode == 0, p.stdout + p.stderr
    sent = w["tmp"] / "sent-0.bundle"
    heads = dict(reversed(ln.split(" ", 1)) for ln in out(["git", "bundle", "list-heads", str(sent)], repo).splitlines())
    assert heads == {"refs/heads/main": out(["git", "rev-parse", "main"], repo), "refs/heads/lane/slice-S1": w["tip"]}
    fresh = w["tmp"] / "fresh"
    sh(["git", "init", "-q", "--bare", str(fresh)], w["tmp"])
    sh(["git", "fetch", "-q", str(sent), "refs/heads/*:refs/heads/*"], fresh)
    got = set(out(["git", "rev-list", "--objects", "--all"], fresh).split("\n"))
    want = set(out(["git", "rev-list", "--objects", "main", w["tip"]], repo).split("\n"))
    assert got == want  # main's history and the slice's commits, every object, and not one more
    blobs = [ln.split()[0] for ln in got if ln]
    contents = sh(["git", "cat-file", "--batch"], fresh, input="\n".join(blobs).encode()).stdout
    for planted in (b"planted-client-hash-list", b"planted-untracked-file", b"planted-uncommitted-change"):
        assert planted not in contents


def test_no_code_path_reads_or_sends_the_hashed_client_name_list(world):
    """The owner's ruling 2: the list never leaves the Mac. No file of the early warning names it or the merge's
    copier, and the bundle test above shows a planted list is not sent."""
    names = ("client_names.local", "CLIENT_HASHES", "bring_client_hashes", "client_hashes.py")
    for f in [w for w in (world["lines"] / "demo_server").iterdir() if w.is_file()] + [world["lines"] / "early_warning.py"]:
        text = f.read_text()
        assert not any(n in text for n in names), f.name


def test_a_second_run_sends_only_what_is_new_and_a_full_bundle_when_the_server_has_lost_it(world):
    w = world
    assert early(w, "S1").returncode == 0
    held = json.loads((w["data"] / "early-warning/held.json").read_text())["main"]
    assert held == out(["git", "rev-parse", "main"], w["repo"])
    assert early(w, "S1").returncode == 0
    second = w["tmp"] / "sent-1.bundle"
    v = sh(["git", "bundle", "verify", str(second)], w["repo"])
    assert b"requires" in v.stdout + v.stderr and b"requires 0" not in v.stdout + v.stderr  # built on what it holds
    heads = out(["git", "bundle", "list-heads", str(second)], w["repo"])
    assert "refs/heads/main" in heads and "refs/heads/lane/slice-S1" in heads
    sh(["rm", "-rf", str(w["remote"] / "data/source.git")], w["tmp"])  # the server lost its copy
    p = early(w, "S1")
    assert p.returncode == 0, p.stdout + p.stderr
    third, fourth = w["tmp"] / "sent-2.bundle", w["tmp"] / "sent-3.bundle"
    assert third.exists() and fourth.exists()  # refused for its prerequisites, then sent in full
    empty = w["tmp"] / "empty.git"
    sh(["git", "init", "-q", "--bare", str(empty)], w["tmp"])
    assert sh(["git", "bundle", "verify", str(third)], empty, check=False).returncode != 0  # incremental
    assert sh(["git", "bundle", "verify", str(fourth)], empty, check=False).returncode == 0  # full: needs nothing


# ------------------------------------------------------------------ the note and the records

def test_the_note_is_written_in_the_lanes_folder_and_nothing_under_records_changes(world):
    w = world
    before = records_snapshot(w)
    p = early(w, "S1")
    assert p.returncode == 0, p.stdout + p.stderr
    assert records_snapshot(w) == before
    text = note(w).read_text()
    assert note(w).parent == w["repo"] / "OspreyFlow_Build/process/lanes/v062/early_warning"
    for line in ("advice only; the Mac's merge run is the gate", "GREEN", w["tip"], "Runner version: ew-2",
                 "Time taken:", "Candidate tree hash: `", "never costs a builder a round",
                 "The client-name check: not run (no client-name list on this machine)"):
        assert line in text, line


def test_the_tree_hash_is_the_merge_of_main_and_the_tip(world):
    w = world
    assert early(w, "S1").returncode == 0
    want = out(["git", "merge-tree", "--write-tree", "main", w["tip"]], w["repo"]).splitlines()[0]
    assert f"Candidate tree hash: `{want}`" in note(w).read_text()


def test_red_names_the_failing_and_exits_red(world):
    w = world
    gate(w, exit=2, targets=["design-check"], tests=["../OspreyFlow_Build/tests/test_x.py::test_y"])
    p = early(w, "S1")
    text = note(w).read_text()
    assert p.returncode == 1 and "RED" in text and "GREEN" not in text
    assert "make target `design-check`" in text and "test `../OspreyFlow_Build/tests/test_x.py::test_y`" in text
    assert "rerun the named failing check on the Mac before sending the slice back" in text


def test_the_note_names_each_failing_test_under_its_target(world):
    w = world
    gate(w, exit=2, targets=["slice-line-check", "lanes-check", "test"],
         tests=["tests/test_a.py::test_one", "../OspreyFlow_Build/tests/test_b.py::test_two"],
         by_target={"slice-line-check": ["tests/test_a.py::test_one"],
                    "test": ["../OspreyFlow_Build/tests/test_b.py::test_two"]})
    p = early(w, "S1")
    text = note(w).read_text()
    assert p.returncode == 1
    lines = text.splitlines()
    at = lines.index("- make target `slice-line-check`")
    assert lines[at + 1] == "  - test `tests/test_a.py::test_one`"
    assert "- make target `lanes-check`: no failing test named in its output" in lines
    at = lines.index("- make target `test`")
    assert lines[at + 1] == "  - test `../OspreyFlow_Build/tests/test_b.py::test_two`"
    assert text.count("test_two") == 1  # named once, under its target


def test_the_note_says_in_one_line_what_happened_to_duckdbs_spatial_extension(world):
    """006: installed, with what; or the stage it stopped at, and why."""
    w = world
    gate(w, exit=2, targets=["test"], duckdb_spatial={"status": "failed", "stage": "fetch", "version": "1.5.6",
         "reason": "HTTPError: HTTP Error 403: Forbidden"})
    p = early(w, "S1")
    # once (22 November, a loaded full run) no note was written: should it happen again, say what the script said
    assert note(w).exists(), (p.returncode, p.stdout.decode()[-1500:], p.stderr.decode()[-3000:])
    assert "- DuckDB's spatial extension: failed at the fetch: HTTPError: HTTP Error 403: Forbidden" in \
        note(w).read_text().splitlines()
    gate(w, exit=0, duckdb_spatial={"status": "installed", "version": "1.5.6", "platform": "linux_amd64",
         "sha256": "ab" * 32})
    note(w).unlink()
    early(w, "S1")
    assert "- DuckDB's spatial extension: installed (DuckDB 1.5.6, linux_amd64, sha256 abababababababab…)" in \
        note(w).read_text().splitlines()


def test_a_run_still_going_at_the_deadline_is_no_result(world):
    w = world
    gate(w, exit=0, sleep=30)
    setting(w, max_wait_minutes=0)
    p = early(w, "S1")
    text = note(w).read_text()
    assert p.returncode == 4 and "NO RESULT" in text and "still running" in text and "GREEN" not in text
    jid = next(ln for ln in text.splitlines() if ln.startswith("- Run id:")).split("`")[1]
    assert f"--result {jid}" in text


def test_a_refusal_by_the_runner_is_refused_not_green(world):
    w = world
    for n in "abc":  # every job slot taken by a job of the runner's still running: busy (009: three at once)
        jobs = w["remote"] / ("data/jobs/" + n * 16)
        jobs.mkdir(parents=True)
        (jobs / "job.json").write_text("{}")
        (jobs / "job.pid").write_text(str(os.getpid()))
    p = early(w, "S1")
    text = note(w).read_text()
    assert p.returncode == 3 and "REFUSED" in text and "busy" in text and "GREEN" not in text


def test_an_unreachable_server_is_no_result_never_green_and_never_names_the_host(world):
    w = world
    s = setting(w, host="early-box.example.invalid", user="osprey-early")
    p = early(w, "S1", env={"FAKE_SSH": "down"})
    text = note(w).read_text()
    assert p.returncode == 4 and "NO RESULT" in text and "ssh exit 255" in text and "GREEN" not in text
    for secret in (s["host"], s["key_file"], "early-box"):
        assert secret not in text and secret.encode() not in p.stdout + p.stderr


def test_a_host_shaped_string_in_the_setting_never_reaches_the_note(world):
    w = world
    address = ".".join(["10", "11", "12", "13"])  # built here, so this file passes its own scan
    s = setting(w, host=address)
    gate(w, exit=1, tests=["tests/test_ssh.py::test_reaches_" + address])  # even if the runner said it
    p = early(w, "S1")
    text = note(w).read_text()
    assert p.returncode == 1 and s["host"] not in text and "<setting>" in text
