"""The runner as sshd's forced command runs it (the owner's ruling 4 and points 1, 4 to 6), against a local fake server
folder. What cannot be shown on the Mac (systemd-run's caps, sshd's `restrict`) is in OUT/SERVER_HAND_CHECKS.md."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

from conftest import DEMO, out, runner, sh

sys.path.insert(0, str(DEMO))
import protocol  # noqa: E402

GOOD_ID = "0123456789abcdef"
REFUSED = [
    ("run extra", "shape"), ("result %s word" % GOOD_ID, "shape"), ("run; ls", "shape"), ("result $(id)", "shape"),
    ("result ../x", "shape"), ("result", "shape"), ("result 0123456789ABCDEF", "shape"), ("result 0123456789abcde", "shape"),
    ("result 0123456789abcdef0", "shape"), ("", "empty"), (None, "empty"), ("run\n", "newline"),
    ("result %s\nrun" % GOOD_ID, "newline"), ("run`id`", "shape"), ("`run`", "shape"), ("run | sh", "shape"),
    ("run & ls", "shape"), ("run && ls", "shape"), ("'run'", "shape"), ('"run"', "shape"), (" run", "shape"),
    ("run ", "shape"), ("RUN", "shape"), ("internal-sftp", "shape"), ("sftp", "shape"),
    ("scp -t /tmp", "shape"), ("scp -f /etc/passwd", "shape"), ("result\t%s" % GOOD_ID, "shape"),
]


def bundle_of(w, *refs, base=None):
    f = w["tmp"] / "b.bundle"
    f.unlink(missing_ok=True)
    sh(["git", "bundle", "create", "-q", str(f), *refs, *([f"^{base}"] if base else [])], w["repo"], w["env"])
    return f.read_bytes()


def answer(p):
    return json.loads(p.stdout.decode().strip().splitlines()[-1])


@pytest.mark.parametrize("command,reason", REFUSED)
def test_every_other_command_is_refused_logged_by_class_and_length_and_nothing_runs(world, command, reason):
    w = world
    p = runner(w, command, stdin=b"not a bundle")
    assert p.returncode == 3 and answer(p) == {"state": "refused", "reason": reason}
    log = (w["remote"] / "data/refusals.log").read_text().splitlines()
    assert len(log) == 1
    at, word, cls, length = log[0].split("\t")
    assert (word, cls, length) == ("refused", reason, "length=%d" % len(command or ""))
    if command and len(command) > 3:
        assert command not in log[0]  # never the received text
    assert not (w["remote"] / "data/source.git").exists() and not (w["remote"] / "data/jobs").exists()


def test_the_two_shapes_are_matched_whole_by_one_pattern_the_mac_script_also_uses():
    assert protocol.parse_command("run") == ("run", "")
    assert protocol.parse_command("result " + GOOD_ID) == ("result", GOOD_ID)
    early = (DEMO.parent / "early_warning.py").read_text()
    assert "proto.ID_PATTERN" in early and "[0-9a-f]{16}" not in early  # the pattern is written once, in protocol.py


def test_the_runner_never_passes_the_command_to_a_shell():
    text = (DEMO / "runner.py").read_text()
    assert "shell=True" not in text and "os.system" not in text and "os.popen" not in text
    assert text.count('os.environ.get("SSH_ORIGINAL_COMMAND")') == 1  # read once


def test_an_unknown_job_is_unknown(world):
    p = runner(world, "result " + GOOD_ID)
    assert p.returncode == 3 and answer(p)["state"] == "unknown"


def test_a_bundle_with_another_head_is_refused_naming_what_it_carries(world):
    w = world
    sh(["git", "branch", "other"], w["repo"], w["env"])
    p = runner(w, "run", bundle_of(w, "refs/heads/main", "refs/heads/lane/slice-S1", "refs/heads/other"))
    a = answer(p)
    assert p.returncode == 3 and a["reason"] == "bundle-heads" and "refs/heads/other" in a["heads"]
    assert list((w["remote"] / "data/jobs").iterdir()) == []


def test_a_bundle_without_main_is_refused(world):
    w = world
    p = runner(w, "run", bundle_of(w, "refs/heads/lane/slice-S1"))
    assert answer(p)["reason"] == "bundle-heads"


def test_an_incremental_bundle_the_server_cannot_resolve_is_refused_naming_the_commits(world):
    w = world
    base = out(["git", "rev-parse", "main~1"], w["repo"])
    p = runner(w, "run", bundle_of(w, "refs/heads/main", "refs/heads/lane/slice-S1", base=base))
    a = answer(p)
    assert p.returncode == 3 and a["reason"] == "bundle-prerequisites" and base in a["missing"]


def test_an_empty_or_unreadable_bundle_is_refused(world):
    assert answer(runner(world, "run", b""))["reason"] == "bundle-empty"
    assert answer(runner(world, "run", b"# v2 git bundle\nnonsense\n"))["reason"] == "bundle-unreadable"


def test_a_bundle_over_the_size_limit_is_refused(world, monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "stdin", type("S", (), {"buffer": __import__("io").BytesIO(b"x" * 2048)})())
    sys.path.insert(0, str(DEMO))
    import runner as r
    monkeypatch.setattr(r.p, "MAX_BUNDLE_BYTES", 1024)
    assert r.receive(tmp_path / "b") == -1


def test_a_planted_mount_outside_the_work_folder_is_refused(world, tmp_path):
    """Point 6: the runner writes into, mounts and binds nothing outside its work folder. A jobs folder that leads to
    a demo data folder (a planted link) is refused before anything is read or written."""
    w = world
    demo_data = tmp_path / "demo-volume"
    demo_data.mkdir()
    (w["remote"] / "data/jobs").symlink_to(demo_data)
    p = runner(w, "run", bundle_of(w, "refs/heads/main", "refs/heads/lane/slice-S1"),
               )
    assert p.returncode == 3 and answer(p)["reason"] == "outside-work" and list(demo_data.iterdir()) == []


def test_without_systemd_run_nothing_runs_uncapped(world):
    w = world
    p = runner(w, "run", bundle_of(w, "refs/heads/main", "refs/heads/lane/slice-S1"),
               harness={"launch": "capped"}, env={"PATH": "/usr/bin:/bin"})  # the real launch, no systemd-run
    assert p.returncode == 3 and answer(p)["reason"] == "no-cap"
    assert list((w["remote"] / "data/jobs").iterdir()) == []


def test_under_the_free_space_floor_nothing_is_received(world):
    w = world
    p = runner(w, "run", bundle_of(w, "refs/heads/main", "refs/heads/lane/slice-S1"),
               harness={"min_free": 1 << 62})  # more than any disk has free, whatever this Mac has today
    assert p.returncode == 3 and answer(p)["reason"] == "disk-floor"
    assert answer(p)["words"] == "under %d GB free" % ((1 << 62) // 1024 ** 3)
    assert list((w["remote"] / "data/jobs").iterdir()) == []


def started(w, harness=None, **gate):
    w["gate"].write_text(json.dumps(gate or {"exit": 0}))
    p = runner(w, "run", bundle_of(w, "refs/heads/main", "refs/heads/lane/slice-S1"), harness=harness)
    a = answer(p)
    assert p.returncode == 0 and a["state"] == "started", a
    return a["id"]


def wait(w, jid, seconds=20):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        a = answer(runner(w, "result " + jid))
        if a["state"] != "running":
            return a
        time.sleep(0.2)
    return a


def test_run_returns_at_once_and_result_says_running_then_done(world):
    w = world
    jid = started(w, harness={"slow_clean": 2}, exit=0, sleep=3)  # a slow clean-up: "done" only once it is over
    assert len(jid) == protocol.ID_LENGTH
    assert answer(runner(w, "result " + jid))["state"] == "running"
    others = [started(w, harness={"slow_clean": 2}, exit=0, sleep=3) for _ in range(protocol.MAX_JOBS - 1)]
    busy = runner(w, "run", bundle_of(w, "refs/heads/main", "refs/heads/lane/slice-S1"),
                  )  # 009: up to MAX_JOBS at once, and no more
    assert answer(busy) == {"state": "refused", "reason": "busy", "running": sorted([jid, *others]), "free": 0}
    a = wait(w, jid)
    assert a["state"] == "done" and a["verdict"] == "pass" and a["runner_version"] == protocol.RUNNER_VERSION
    want = out(["git", "merge-tree", "--write-tree", "main", w["tip"]], w["repo"]).splitlines()[0]
    assert a["tree"] == want and a["tip"] == w["tip"]
    job = w["remote"] / "data/jobs" / jid
    assert not (job / "tree").exists() and not (job / "bundle").exists()  # its own work removed after the run


def test_the_source_copy_has_no_remote_and_no_credential(world):
    w = world
    wait(w, started(w))
    cfg = out(["git", "config", "--list", "--local"], w["remote"] / "data/source.git")
    assert "remote." not in cfg and "credential" not in cfg and "url." not in cfg
    assert out(["git", "remote"], w["remote"] / "data/source.git") == ""


def test_the_slices_waiting_scan_rows_are_applied_in_the_merge_commit(world):
    w = world
    rows = w["repo"] / "OspreyFlow_Build/process/lanes/v062/scan_rows/S1.tsv"
    rows.parent.mkdir(parents=True)
    rows.write_text("tests/test_new.py\t-\twalks nothing\n")
    sh("git add -A && git commit -qm 'records: S1 scan rows'", w["repo"], w["env"])
    a = wait(w, started(w))
    assert a["scan_rows"] == ["tests/test_new.py\t-\twalks nothing"]
    assert a["tree"] != out(["git", "merge-tree", "--write-tree", "main", w["tip"]], w["repo"]).splitlines()[0]


def test_a_slice_that_does_not_merge_is_a_conflict(world):
    w = world
    sh(["git", "switch", "-q", "lane/slice-S1"], w["repo"], w["env"])
    (w["repo"] / "shared.txt").write_text("the slice's line\n")
    sh("git commit -qam 'feat: S1 changes shared'", w["repo"], w["env"])
    sh(["git", "switch", "-q", "main"], w["repo"], w["env"])
    (w["repo"] / "shared.txt").write_text("main's other line\n")
    sh("git commit -qam 'docs: main changes shared'", w["repo"], w["env"])
    a = wait(w, started(w))
    assert a["verdict"] == "conflict" and a["conflicts"] == ["shared.txt"]
