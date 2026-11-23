"""A part that carries its own scan row, byte for byte what main already holds, is not refused at the merge's first
check (the owner's file 015, 23 November 2026).

AD1b's merge was refused twice at the first check (14:58 and 15:01 UTC): "the branch touches protected paths:
OspreyFlow_Build/process/lanes/v062/scan_rows/AD1b.tsv". Its brief told its builder to write its row in its own file
(round 1, 803e75c); the conductor then put other rows in that file on main (04f86c7, AD1a's three), the branch took
main's file when it merged main in (ea1dc1e), the verifier found the builder's row lost, and the builder wrote it
again (round 2, 997ee14). The conductor then put the same row on main (8f8e1d4). The check measured what the branch
changed since it left main, not what the merge would change: nothing, for that file.

The way out is narrow: only the part's own scan_rows/<its id>.tsv, and only when that file in the merge result is
byte for byte main's. Nothing reaches main that the conductor or the owner did not put there. Another part's row, a
row one byte from main's, a row main has not got and every other protected path are refused as before. A builder
never sets its own row (the row decides which tests cover the part). The tests replay AD1b's history with its real
row files (fixtures/scan_rows_AD1b_*.tsv, as git holds them at those commits).
"""
from __future__ import annotations

import json
from pathlib import Path

from test_gates import built, main_sha, merge, sh, verified, world  # noqa: F401  (world is a fixture)
from test_scan_rows import HEADER, MAP, V062, on_main, set_state

FIX = Path(__file__).resolve().parent / "fixtures"
ROW_MAIN = (FIX / "scan_rows_AD1b_8f8e1d4.tsv").read_text()        # the builder's row, and main's since 8f8e1d4
ROW_AD1A = (FIX / "scan_rows_AD1b_04f86c7.tsv").read_text()        # the conductor's first file: AD1a's three rows
TEST = "tests/services/api/test_stale_engine_keys_are_named.py"
PREFIXES = ("OspreyFlow_Build/spec/06_DECISIONS.md", "OspreyFlow_Build/spec/10_ADMINISTRATION_GUIDE.md",
            "OspreyFlow_Core/docs/administration-guide.md", "OspreyFlow_Build/tests/services/api/test_model_key_paths.py")
PURE = "def test_the_routes_that_leave_a_token_are_named():\n    assert True\n"
OWN = f"{V062}/scan_rows/S1.tsv"
REAL_WHY = "the branch touches protected paths: OspreyFlow_Build/process/lanes/v062/scan_rows/AD1b.tsv"


def ad1b(w, row_on_main=ROW_MAIN, extra=None):
    """S1 replays AD1b: its own row in round 1, main's other rows taken in, its row again in round 2, main's copy."""
    on_main(w, {MAP: HEADER, **{p: "named by the row\n" for p in PREFIXES}}, "docs: the files the row names")
    wt, _ = built(w, extra={f"OspreyFlow_Build/{TEST}": PURE, OWN: ROW_MAIN})          # 803e75c: round 1
    on_main(w, {OWN: ROW_AD1A}, "docs(slice-line): scan rows for S1 (04f86c7)")
    m = sh(["git", "merge", "-q", "--no-edit", "main"], wt, w["env"], check=False)    # ea1dc1e: main's file taken
    if m.returncode != 0:
        sh(["git", "checkout", "--theirs", "--", OWN], wt, w["env"])
        sh(["git", "add", "--", OWN], wt, w["env"])
        sh(["git", "commit", "-q", "--no-edit"], wt, w["env"])
    (wt / OWN).write_text(ROW_MAIN)                                                    # 997ee14: round 2, again
    for path, text in (extra or {}).items():
        (wt / path).parent.mkdir(parents=True, exist_ok=True)
        (wt / path).write_text(text)
    sh("git add -A . && git commit -qm 'fix: S1 round 2, its row again'", wt, w["env"])
    tip = sh("git rev-parse HEAD", wt).stdout.strip()
    verified(w, wt, tip)
    set_state(w, phase="verified", tip=tip)
    if row_on_main is not None:
        on_main(w, {OWN: row_on_main}, "docs(slice-line): S1's own scan row on main (8f8e1d4)")
    return wt, tip


def test_ad1b_s_own_row_byte_for_byte_main_s_is_let_through_and_applied(world):
    """AD1b at its verified tip, main at 8f8e1d4: refused today at the first check; merged with its tip unchanged."""
    w = world
    wt, tip = ad1b(w)
    p = merge(w)
    assert REAL_WHY.replace("AD1b", "S1") not in p.stderr, p.stderr                     # the real refusal, gone
    assert p.returncode == 0, p.stdout + p.stderr
    done = json.loads((w["data"] / "records/S1/merged.json").read_text())
    assert done["tip"] == tip and sh(["git", "rev-parse", "main^2"], w["repo"], w["env"]).stdout.strip() == tip
    assert done["scan_rows"] == [ROW_MAIN.rstrip("\n")], done                           # main's row, applied as ever
    assert (w["repo"] / MAP).read_text() == HEADER + ROW_MAIN and not (w["repo"] / OWN).exists()
    assert "byte for byte main's" in p.stdout + p.stderr                               # said, not silent


def test_a_row_one_byte_from_main_s_is_refused(world):
    w = world
    ad1b(w, row_on_main=ROW_MAIN.replace("walks no folder", "walks no folders", 1))
    before = main_sha(w)
    p = merge(w)
    assert p.returncode == 1 and REAL_WHY.replace("AD1b", "S1") in p.stderr, p.stderr
    assert main_sha(w) == before


def test_a_row_main_has_not_got_is_refused(world):
    w = world
    ad1b(w, row_on_main=None)
    on_main(w, {OWN: None}, "docs: the conductor's row taken away")
    p = merge(w)
    assert p.returncode == 1 and REAL_WHY.replace("AD1b", "S1") in p.stderr, p.stderr


def test_another_part_s_row_is_refused_even_byte_for_byte_main_s(world):
    w = world
    other = f"{V062}/scan_rows/S2.tsv"
    on_main(w, {other: ROW_MAIN}, "docs: S2's row")
    ad1b(w, extra={other: ROW_MAIN.replace("walks no folder", "walks a folder", 1)})
    on_main(w, {other: ROW_MAIN.replace("walks no folder", "walks a folder", 1)}, "docs: S2's row, as the branch has it")
    p = merge(w)
    assert p.returncode == 1 and "protected paths" in p.stderr and other in p.stderr, p.stderr
    refusal = next(ln for ln in p.stderr.splitlines() if ln.startswith("Refused: "))
    assert OWN not in refusal, refusal                                                 # its own row is not the cause


def test_a_second_protected_path_riding_along_is_refused(world):
    w = world
    dial = f"{V062}/dial.yaml"
    ad1b(w, extra={dial: "changed\n"})
    before = main_sha(w)
    p = merge(w)
    assert p.returncode == 1 and "protected paths" in p.stderr and dial in p.stderr, p.stderr
    assert main_sha(w) == before
