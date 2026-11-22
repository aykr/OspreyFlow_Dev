"""Records and resume actions while a merge runs (LINE_FIXES_5_BRIEF.md, 2).

A merge takes 25 to 35 minutes, and the conductor's records waited for it. The merge builds its trees from a fixed
commit of main (the base) and, before this, refused to land if main had moved at all. Now: (a) `merge_slice.py records`
commits while a merge runs, and the merge lands its tested result on the moved main only when every commit that moved
it is a records commit changing only files in the records folder that the merge neither tested through the slice nor
reads (its scan rows, the owner's files), made again there by git merge-tree and checked to differ from the tested
tree in exactly those files; it records the base it tested. Anything else moving main is refused as before, and no
records commit is ever lost. (b) add-round, clear-stop, send-back and accept go on for a slice other than the one being
merged; on the merging slice they wait.

The gate here is the suite's stand-in (test_gates.STAND_IN_GATE); TEST_GATE_DURING is run while it runs.
"""
from __future__ import annotations

import json
import time

import pytest

from test_gates import built, main_sha, merge, sh, started, verified, world  # noqa: F401  (world is a fixture)

V062 = "OspreyFlow_Build/process/lanes/v062"
from test_gates import TODAY  # noqa: E402  (the run's one date: 9)


def during(w, cmd):
    w["env"]["TEST_GATE_DURING"] = cmd
    w["env"]["TEST_GATE_DURING_CWD"] = str(w["repo"])


def records_cmd(w, rel, text, out="during.out"):
    return (f"printf '%s\\n' '{text}' > '{rel}' && '{w['py']}' '{w['lines'] / 'merge_slice.py'}' records -m "
            f"'docs(process): {text}' '{rel}' > '{w['tmp'] / out}' 2>&1")


def merged_json(w):
    f = w["data"] / "records/S1/merged.json"
    return json.loads(f.read_text()) if f.exists() else None


def test_a_records_commit_while_a_merge_runs_is_landed_and_the_merge_result_contains_it(world):
    w = world
    wt, tip = built(w)
    verified(w, wt, tip)
    base = main_sha(w)
    during(w, records_cmd(w, f"{V062}/notes.md", "a conductor note"))
    p = merge(w)
    assert p.returncode == 0, p.stdout + p.stderr
    said = (w["tmp"] / "during.out").read_text()
    assert said.startswith("Committed"), said  # not refused: a merge was running
    rec_sha = said.split()[1]
    done = merged_json(w)
    head = main_sha(w)
    assert done["merge"] == head and done["base"] == base and done["landed_on"] == rec_sha, done
    assert done["records_under_gate"] == [rec_sha] and done["tested_merge"] != head, done
    assert sh(["git", "merge-base", "--is-ancestor", rec_sha, head], w["repo"], check=False).returncode == 0  # kept
    assert sh(["git", "show", f"{head}:{V062}/notes.md"], w["repo"]).stdout.strip() == "a conductor note"
    assert sh(["git", "show", f"{head}:feature.txt"], w["repo"]).stdout.strip() == "done"
    # the landed tree is the tested tree with the records commit's file and nothing else
    assert sh(["git", "diff", "--name-only", done["tested_merge"], head], w["repo"]).stdout.split() == [f"{V062}/notes.md"]
    msg = sh(["git", "log", "-1", "--format=%B", head], w["repo"]).stdout
    assert "Slice-Merge: S1" in msg and f"Slice-Tested: {done['tested_merge']}" in msg, msg
    assert sh(["git", "rev-parse", "HEAD^1", "HEAD^2"], w["repo"]).stdout.split() == [rec_sha, tip]
    assert sh("git ls-remote origin refs/heads/main", w["repo"]).stdout.split()[0] == head  # pushed, records and all
    assert not (w["data"] / "merge.running.json").exists()


def test_a_merge_with_nothing_moving_main_lands_its_tested_commit_as_before(world):
    w = world
    wt, tip = built(w)
    verified(w, wt, tip)
    p = merge(w)
    assert p.returncode == 0, p.stdout + p.stderr
    done = merged_json(w)
    assert done["merge"] == main_sha(w) and "tested_merge" not in done and "records_under_gate" not in done, done


@pytest.mark.parametrize("how", ["outside-the-records", "a-file-the-slice-changed", "the-merges-scan-rows",
                                 "not-a-records-commit"])
def test_a_moved_main_that_touches_a_tested_path_is_refused_and_nothing_is_lost(world, how):
    w = world
    # no scan of the real map runs on this throwaway tree (its walkers' tests are not here): the map's header alone
    (w["lines"] / "scan_map.tsv").write_text("# test\tprefixes\twhy\n")
    sh("git add -A . ':!OspreyFlow_Core/osprey.yaml' && git commit -qm 'test: no scans' --trailer 'Slice-Records: yes'",
       w["repo"], w["env"])
    brief = w["repo"] / V062 / "slices/S1.md"
    brief.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"line {n}\n" for n in range(1, 9)]
    brief.write_text("".join(lines))
    sh("git add -A . ':!OspreyFlow_Core/osprey.yaml' && git commit -qm 'docs: S1 brief' --trailer 'Slice-Records: yes'",
       w["repo"], w["env"])
    # the slice changes the brief's last line; a records commit changing its first merges cleanly with it
    wt, tip = built(w, extra={f"{V062}/slices/S1.md": "".join(lines[:-1]) + "the slice's own last line\n"})
    verified(w, wt, tip)
    rel, trailer = {"outside-the-records": ("README.md", True),
                    "a-file-the-slice-changed": (f"{V062}/slices/S1.md", True),
                    "the-merges-scan-rows": (f"{V062}/scan_rows/S9.tsv", True),
                    "not-a-records-commit": (f"{V062}/notes.md", False)}[how]
    t = "--trailer 'Slice-Records: yes'" if trailer else ""
    if how == "a-file-the-slice-changed":
        write = f"sed -i.bak '1s/.*/moved/' '{rel}' && rm -f '{rel}.bak'"
    else:
        write = f"mkdir -p \"$(dirname '{rel}')\" && echo moved > '{rel}'"
    during(w, f"{write} && git add '{rel}' && git commit -qm 'moved' {t}")
    p = merge(w)
    assert p.returncode == 1 and "main moved while the merge was being tested" in p.stderr, p.stdout + p.stderr
    moved = main_sha(w)
    assert sh(["git", "show", f"{moved}:{rel}"], w["repo"]).stdout.splitlines()[0] == "moved"  # main kept the commit
    assert sh(["git", "log", "-1", "--format=%s", moved], w["repo"]).stdout.strip() == "moved"  # nothing landed on it
    assert merged_json(w) is None


def second_slice_at_its_limit(w):
    tsv = w["repo"] / V062 / "slices.tsv"
    tsv.write_text(tsv.read_text() + "S3\tCO1\tAnother\t-\t2\t-\tnone\taccept3.sh\tsh accept3.sh\ttrue\n")
    sh("git add -A . ':!OspreyFlow_Core/osprey.yaml' && git commit -qm 'docs: S3' --trailer 'Slice-Records: yes'",
       w["repo"], w["env"])
    p, wt3 = started(w, "S3")
    assert p.returncode == 0, p.stdout + p.stderr
    f = w["data"] / "records/S3/state.json"
    st = json.loads(f.read_text())
    f.write_text(json.dumps({**st, "phase": "stopped", "round": st["rounds_limit"], "note": "findings: your word?"}))
    return st


def test_a_resume_action_on_another_slice_goes_on_and_one_on_the_merging_slice_waits(world):
    w = world
    second_slice_at_its_limit(w)
    wt, tip = built(w)
    verified(w, wt, tip)
    base = main_sha(w)
    origin = sh("git ls-remote origin refs/heads/main", w["repo"]).stdout.split()[0]
    (w["repo"] / V062 / "resume.tsv").write_text(f"S3\tadd-round\t{TODAY}\nS1\tadd-round\t{TODAY}\n"
                                                 f"S3\trefreeze\t{TODAY}\n")
    tsv = w["repo"] / V062 / "slices.tsv"
    row = tsv.read_text().replace("\tsh accept3.sh\ttrue\n", "\tsh accept3.sh\ttrue && true\n")
    (w["tmp"] / "slices-refrozen.tsv").write_text(row)  # the owner's new row for S3, put in place while the merge runs
    r = f"'{w['py']}' '{w['lines'] / 'resume.py'}'"
    during(w, f"{r} S3 add-round > '{w['tmp']}/s3.out' 2>&1; {r} S1 add-round > '{w['tmp']}/s1.out' 2>&1; "
              f"cp '{w['tmp']}/slices-refrozen.tsv' '{tsv}'; {r} S3 refreeze > '{w['tmp']}/s3-refreeze.out' 2>&1; "
              f"git ls-remote origin refs/heads/main > '{w['tmp']}/origin-during.out'; "
              f"{r} S3 self-clear > '{w['tmp']}/s3-self-clear.out' 2>&1; "
              f"{r} S3 undo-seat-failure > '{w['tmp']}/s3-undo.out' 2>&1; "
              f"{r} S3 move-seat builder x > '{w['tmp']}/s3-move.out' 2>&1")
    p = merge(w)
    assert p.returncode == 0, p.stdout + p.stderr
    s3 = (w["tmp"] / "s3.out").read_text()
    assert "S3: one more round" in s3, s3
    st3 = json.loads((w["data"] / "records/S3/state.json").read_text())
    assert st3["phase"] == "building" and st3["round"] == st3["rounds_limit"], st3
    s1 = (w["tmp"] / "s1.out").read_text()
    assert s1.startswith("Refused: another merge is running (S1)") and "add-round on S1 waits" in s1, s1
    # the owner's refreeze line goes on: its commit lands beneath the merge and is pushed with it
    refreeze = (w["tmp"] / "s3-refreeze.out").read_text()
    assert refreeze.startswith("S3: refrozen from main"), refreeze
    done = merged_json(w)
    head = main_sha(w)
    assert done["base"] == base and len(done["records_under_gate"]) == 1, done
    assert refreeze.split("(")[1].split(")")[0] == done["records_under_gate"][0][:10], (refreeze, done)
    assert "sh accept3.sh\ttrue && true" in sh(["git", "show", f"{head}:{V062}/slices.tsv"], w["repo"]).stdout
    assert json.loads((w["data"] / "records/S3/frozen.json").read_text())["checks"] == "true && true"
    assert (w["tmp"] / "origin-during.out").read_text().split()[0] == origin  # not pushed while the merge ran
    assert sh("git ls-remote origin refs/heads/main", w["repo"]).stdout.split()[0] == head
    # self-clear and undo-seat-failure go past the lock (and are refused for their own reasons); move-seat waits
    for out in ("s3-self-clear.out", "s3-undo.out"):
        said = (w["tmp"] / out).read_text()
        assert "another merge is running" not in said and said.startswith("Refused: "), said
    move = (w["tmp"] / "s3-move.out").read_text()
    assert move.startswith("Refused: another merge is running (S1): move-seat waits"), move
    log = (w["data"] / "owner-changes.tsv").read_text()
    assert "S3\tadd-round" in log and "S3\trefreeze" in log and "S1\tadd-round" not in log, log


def test_a_refreeze_with_no_merge_running_still_pushes_at_once(world):
    w = world
    second_slice_at_its_limit(w)
    (w["repo"] / V062 / "resume.tsv").write_text(f"S3\trefreeze\t{TODAY}\n")
    tsv = w["repo"] / V062 / "slices.tsv"
    tsv.write_text(tsv.read_text().replace("\tsh accept3.sh\ttrue\n", "\tsh accept3.sh\ttrue && true\n"))
    p = sh([w["py"], str(w["lines"] / "resume.py"), "S3", "refreeze"], w["repo"], w["env"], check=False)
    assert p.returncode == 0 and "S3: refrozen from main" in p.stdout, p.stdout + p.stderr
    assert sh("git ls-remote origin refs/heads/main", w["repo"]).stdout.split()[0] == main_sha(w)


def test_records_alone_still_pushes_and_takes_the_merge_lock(world):
    w = world
    (w["repo"] / V062 / "notes.md").write_text("x\n")
    p = sh([w["py"], str(w["lines"] / "merge_slice.py"), "records", "-m", "docs: notes", f"{V062}/notes.md"],
           w["repo"], w["env"], check=False)
    assert p.returncode == 0, p.stdout + p.stderr
    assert sh("git ls-remote origin refs/heads/main", w["repo"]).stdout.split()[0] == main_sha(w)
