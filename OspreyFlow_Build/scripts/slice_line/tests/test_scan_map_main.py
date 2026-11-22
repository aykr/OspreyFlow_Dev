"""The owner's file 007 (22 November 2026): the installed copy of scan_map.tsv goes stale when a merge adds a row (195
rows installed against 196 on main after PL4d3e), and a builder was then failed for a row that exists. The Stop hook's
scan-map check reads main's rows beside the installed copy: a row on main counts at once, with nothing installed
changed. (The scans a stop selects are unchanged; the merge reads main's map itself.)
"""
from __future__ import annotations

from test_gates import sh, stop_gate, world  # noqa: F401  (world is a fixture)
from test_stop_lint import WALKER, branch, record, tools

LINE_MAP = "OspreyFlow_Build/scripts/slice_line/scan_map.tsv"


def test_a_row_a_merge_added_on_main_counts_before_the_owner_reinstalls(world):
    w = world
    tools(w)                                                    # the installed copy: no row for the walker
    installed = (w["data"] / "bin/scan_map.tsv").read_bytes()
    m = w["repo"] / LINE_MAP
    m.write_text(m.read_text() + "tests/test_walker.py\t-\twalks its own folder of pages only\n")
    sh(["git", "commit", "-qam", "merge: a slice's scan row"], w["repo"], w["env"])
    wt = branch(w, {"OspreyFlow_Build/tests/test_walker.py": WALKER})
    assert stop_gate(w, wt) is None and record(w, wt)["green"]
    assert (w["data"] / "bin/scan_map.tsv").read_bytes() == installed        # nothing installed changed


def test_without_the_row_anywhere_it_is_still_red(world):
    w = world
    tools(w)
    wt = branch(w, {"OspreyFlow_Build/tests/test_walker.py": WALKER})
    out = stop_gate(w, wt)
    assert out and "RED: scan map" in out["reason"], out
