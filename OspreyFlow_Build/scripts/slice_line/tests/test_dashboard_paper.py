"""The conductor's paper on the dashboard (DASHBOARD_LABELS_2026-11-23.md, items 1 to 14; the owner: "the dashboard is
not reflecting the true picture"). One cause under most of them: one entry per build, from one slice, read from records
that lag. Now each part has its own state in build_slices[<build>]["list"] (the owner's file 014), read in the paper's
order: a merge record (merged), a merge in progress (merging, with its step), a verifier's pass or the owner's acceptance
(verified), a running seat (building or verifying), a stop or a refusal with its cause in words; with what it waits for
(item 1). A build's entry is its most pressing part's, never just its last row's (item 9). A refusal that names no test
of the part's leaves it verified, to run its merge again (items 5, 10, 11). The server's word says its own words, its
main and a red that was the server's DuckDB extension (items 3, 4, 6); a retired part is gone (item 3); a build that
moved back says which parts were cut since it was done (item 7).
"""
from __future__ import annotations

import json
import subprocess
import sys

from test_build_counts import STATUS, merged, rows
from test_gates import TODAY, built, sh, verified, world  # noqa: F401  (world is a fixture)
from test_merge_progress import at_step, start
from test_resume import owner_line, resume, said_refused

V062 = "OspreyFlow_Build/process/lanes/v062"


def status(w):
    out = sh([w["py"], str(w["lines"] / "board.py")], w["repo"], w["env"], check=False)
    body = json.loads((w["repo"] / STATUS).read_text().split("window.OSPREY_STATUS = ", 1)[1].rstrip().rstrip(";"))
    return out.stdout, body


def part(body, sid, build="CO1"):
    return next(p for p in body["build_slices"][build]["list"] if p["id"] == sid)


def set_state(w, sid="S1", **kw):
    f = w["data"] / f"records/{sid}/state.json"
    st = json.loads(f.read_text())
    st.update(kw)
    f.write_text(json.dumps(st))


def ready(w):
    """S1 built, its checks green, its verifier's pass for its tip, phase verified."""
    wt, tip = built(w)
    verified(w, wt, tip)
    set_state(w, phase="verified", tip=tip)
    return wt, tip


# ------------------------------------------------------------------ item 9: a merge of one part, beside a merged one


def test_a_merge_running_shows_beside_a_merged_part_of_the_same_build(world):
    """DC1 at 11:45: DC1b merging at step 5 of 7, DC1c (a later row) merged; the dashboard showed DC1 done."""
    w = world
    ready(w)
    rows(w, ("S3", "CO1"))                                       # a later row of the same build, merged
    merged(w, "S3", 3)
    p = start(w, TEST_GATE_SLEEP=30)
    try:
        at_step(w, 5, p)
        _, body = status(w)
    finally:
        p.kill()
        p.wait()
    assert body["builds"]["CO1"].get("progress") and body["builds"]["CO1"]["state"] != "done", body["builds"]["CO1"]
    assert part(body, "S1")["state"] == "merging" and "step 5 of 7" in part(body, "S1")["said"], part(body, "S1")
    assert part(body, "S3")["state"] == "merged"


# ------------------------------------------------------------------ items 5, 10, 11: a refusal naming no test of the part's


def test_a_refusal_naming_no_test_of_the_parts_leaves_it_verified_to_run_its_merge_again(world):
    """SE9 (a full Docker disk) and PL12b (the line's own rerun in the wrong folder): 0 tests named, the part verified."""
    w = world
    ready(w)
    set_state(w, phase="refused", refused_for="gate", refused_tests=0, refused_at="2026-11-23T06:12:00Z",
              note="refused by the gate: 0 tests", last_refusal_cause="trivy-image-ingest: no space left on device",
              last_merge_refusal="2026-11-23T06:12:00Z")
    _, body = status(w)
    entry, mine = body["builds"]["CO1"], part(body, "S1")
    assert entry["state"] != "stopped" and "run its merge again" in entry["note"], entry
    assert "send-back" not in entry["note"] and "no space left on device" in entry["note"], entry
    assert mine["state"] == "verified" and mine["waiting_for"] == "a merge run again", mine


def test_a_refusal_naming_the_parts_tests_is_still_a_stop(world):
    w = world
    ready(w)
    set_state(w, phase="refused", refused_for="gate", refused_tests=3, refused_at="2026-11-23T06:12:00Z",
              note="refused by the gate: 3 tests")
    _, body = status(w)
    assert body["builds"]["CO1"]["state"] == "stopped" and "send-back" in body["builds"]["CO1"]["note"]
    assert part(body, "S1")["state"] == "stopped" and part(body, "S1")["waiting_for"] == "you"


# ------------------------------------------------------------------ item 12: accepted narrower is verified


def test_a_part_accepted_narrower_is_verified_not_checks_green(world):
    """IS2a at 11:22: accepted narrower on the standing line; the dashboard said 'checks green; verifier pending'."""
    w = world
    wt, tip = built(w)
    rec = w["data"] / "records/S1"
    (rec / f"accepted-{tip}.json").write_text(json.dumps({"slice": "S1", "commit": tip, "by": "standing",
                                                           "findings": [{"kind": "test_gap", "what": "a gap"}]}))
    _, body = status(w)
    assert "accepted narrower on the standing line" in body["builds"]["CO1"]["note"], body["builds"]["CO1"]
    assert "verifier pending" not in body["builds"]["CO1"]["note"]
    assert part(body, "S1")["state"] == "verified", part(body, "S1")


# ------------------------------------------------------------------ items 2 and 13: a running seat


def test_a_running_verifier_is_shown_at_work_not_waiting(world):
    w = world
    wt, tip = built(w)
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        (w["data"] / "records/S1/running-verifier.json").write_text(json.dumps(
            {"slice": "S1", "seat": "verifier", "account": "default", "pid": proc.pid, "at": "2026-11-23T11:36:00Z"}))
        _, body = status(w)
    finally:
        proc.kill()
        proc.wait()
    assert "its verifier is running (since 2026-11-23T11:36:00Z)" in body["builds"]["CO1"]["note"], body["builds"]["CO1"]
    assert part(body, "S1")["state"] == "verifying" and part(body, "S1")["waiting_for"] == "", part(body, "S1")
    _, body = status(w)                                             # the seat ended: queued for a seat again
    assert part(body, "S1")["waiting_for"] == "a seat" and "running" not in body["builds"]["CO1"]["note"]


# ------------------------------------------------------------------ items 3, 4, 6: the server's own words


def note(w, tip, headline, *lines):
    d = w["repo"] / V062 / "early_warning"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"S1-{tip[:8]}.md").write_text(f"# Early warning: S1 at {tip[:8]}: {headline}\n\n" + "".join(f"{x}\n" for x in lines)
                                        + "- Run id: `0123456789abcdef`\n")


def test_a_green_on_a_main_that_has_moved_says_so(world):
    """SE8d: an old green, many main commits back, shown 'next to merge'."""
    w = world
    wt, tip = ready(w)
    old = "1" * 40                                                   # a main long gone
    note(w, tip, "GREEN", f"- Main: `{old}`")
    _, body = status(w)
    srv = part(body, "S1")["server"]
    assert srv["state"] == "green" and srv["on_main"] is False and "main has moved: not counted" in srv["said"], srv
    note(w, tip, "GREEN", f"- Main: `{sh('git rev-parse main', w['repo']).stdout.strip()}`")
    _, body = status(w)
    assert part(body, "S1")["server"]["on_main"] is True and "moved" not in part(body, "S1")["server"]["said"]


def test_a_run_with_no_verdict_says_what_was_tried_and_its_words(world):
    """PL12b: tried at 07:12, no verdict (the shield); the dashboard said 'not yet sent to the server'."""
    w = world
    wt, tip = ready(w)
    note(w, tip, "REFUSED", "- Result: REFUSED (the shield does not hold: port 34041)", "- Written: 2026-11-23T07:12:00Z")
    _, body = status(w)
    srv = part(body, "S1")["server"]
    assert srv["state"] == "no verdict" and srv["words"] == "the shield does not hold: port 34041", srv
    assert srv["said"] == "server no verdict (the shield does not hold: port 34041, 2026-11-23T07:12:00Z)", srv


def test_a_red_from_the_servers_duckdb_extension_is_no_verdict_not_red(world):
    """DC1b and AD1a: about 25 tests red because the extension did not install (a download failure, a truncated file)."""
    w = world
    wt, tip = ready(w)
    note(w, tip, "RED", "- DuckDB's spatial extension: not installed (the download stopped at 4 MB of 31)", "",
         "## Failing", "", "- make target `test`", "  - test `tests/test_x.py::test_spatial`")
    _, body = status(w)
    srv = part(body, "S1")["server"]
    assert srv["state"] == "no verdict" and "DuckDB extension failed" in srv["words"] and "test" not in srv, srv
    note(w, tip, "RED", "- DuckDB's spatial extension: installed (DuckDB 1.5.6)", "",
         "## Failing", "", "- make target `test`", "  - test `tests/test_x.py::test_spatial`")
    _, body = status(w)
    assert part(body, "S1")["server"]["state"] == "red"                # a real red stays red


# ------------------------------------------------------------------ item 3: retire, on the owner's line


def test_a_part_retired_on_the_owners_line_is_neither_shown_nor_counted(world):
    w = world
    rows(w, ("S3", "CO1"))
    ready(w)
    _, body = status(w)
    assert body["build_slices"]["CO1"]["cut"] == 2
    p = resume(w, "S3", "retire")
    assert said_refused(p, "no line"), p.stdout + p.stderr           # the owner's word, and only it
    owner_line(w, f"S3\tretire\t{TODAY}")
    p = resume(w, "S3", "retire")
    assert p.returncode == 0 and "retired on the owner's line" in p.stdout, p.stdout + p.stderr
    _, body = status(w)
    assert [x["id"] for x in body["build_slices"]["CO1"]["list"]] == ["S1"] and body["build_slices"]["CO1"]["cut"] == 1
    log = (w["data"] / "owner-changes.tsv").read_text()
    assert f"resume.tsv {TODAY} retire:" in log, log


def test_a_merged_part_is_never_retired(world):
    w = world
    rows(w, ("S3", "CO1"))
    merged(w, "S3", 3)
    owner_line(w, f"S3\tretire\t{TODAY}")
    assert said_refused(resume(w, "S3", "retire"), "has merged")
    assert not (w["data"] / "records/S3/retired.json").exists()


# ------------------------------------------------------------------ item 7: why a build's count fell


def test_a_build_that_moved_back_says_which_parts_were_cut_since_it_was_done(world):
    """SE6 (SE6c cut) and PL7 (PL7a2b, PL7c cut): 35 of 61 builds became 33, and the owner saw only the number fall."""
    w = world
    rows(w, ("S3", "CO1"))
    merged(w, "S1", 1)
    merged(w, "S3", 3)
    _, body = status(w)
    assert body["build_slices"]["CO1"]["said"] == "2 of 2" and "moved_back" not in body["build_slices"]["CO1"]
    rows(w, ("S4", "CO1"))                                          # a new part cut under a done build
    out, body = status(w)
    assert body["build_slices"]["CO1"]["moved_back"] == ["S4"], body["build_slices"]["CO1"]
    assert "CO1 moved back: S4 cut since it was done" in out, out
    merged(w, "S4", 4)
    out, body = status(w)
    assert "moved_back" not in body["build_slices"]["CO1"] and "moved back" not in out
