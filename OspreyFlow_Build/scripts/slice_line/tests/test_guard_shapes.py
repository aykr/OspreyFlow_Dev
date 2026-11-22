"""The slice guard and some shell shapes (LINE_FIXES_5_BRIEF.md, 8.3).

On 21 November the conductor's commands were refused for their shape, not their effect: a copy into
process/lanes/v062/ followed, in the same `&&` chain, by a run of a line script (read as a write to the line's scripts
or to product code), and a write whose target was a shell variable set earlier in the command (read as a write
outside the conductor's folder). The guard now reads each part of a chain: a part that only runs one of the line's
scripts whole writes nothing itself, and a simple variable set earlier in the command is put in where it is used; a
write into a variable it cannot resolve is refused, naming the shape. Each shape is tested both ways: allowed where it
writes the records, refused where it writes the line, product code or the owner's files.
"""
from __future__ import annotations

import pytest

from test_gates import bash, refused, world  # noqa: F401  (world is a fixture)

V = "OspreyFlow_Build/process/lanes/v062"
LINE = "OspreyFlow_Build/scripts/slice_line"
RECORDS = f"python3 {LINE}/merge_slice.py records -m 'docs(process): S9' {V}/slices/S9.md"


def allowed(p):
    return p.returncode == 0


@pytest.mark.parametrize("cmd", [
    f"cp /tmp/S9.md {V}/slices/S9.md && {RECORDS}",
    f"cp /tmp/S9.md {V}/slices/S9.md && python3 {LINE}/resume.py S9 add-round",
    f"D={V}; cp /tmp/S9.md \"$D/slices/S9.md\" && {RECORDS}",
    f"D={V}/slices\necho note > \"$D/S9.md\"",
    f"export D={V}; printf '%s\\n' x > ${{D}}/notes.md",
], ids=["copy-then-records", "copy-then-resume", "variable-then-records", "variable-on-its-own-line",
        "exported-braced-variable"])
def test_the_conductors_records_writes_are_allowed_in_these_shapes(world, cmd):
    p = bash(world, cmd, seat="conductor")
    assert allowed(p), (cmd, p.stderr)


@pytest.mark.parametrize("cmd,said", [
    (f"cp /tmp/x {LINE}/board.py && {RECORDS}", "part of the slice line itself"),
    (f"cp /tmp/x OspreyFlow_Core/apps/x.ts && {RECORDS}", "writes no product code"),
    (f"{RECORDS} && cp /tmp/x {LINE}/board.py", "part of the slice line itself"),
    (f"D={LINE}; echo x > \"$D/board.py\"", "part of the slice line itself"),
    ("D=OspreyFlow_Core; cp /tmp/x \"$D/apps/x.ts\"", "writes no product code"),
    (f"D={V}; echo x > \"$D/dial.yaml\"", "owner's"),
    ("echo x > \"$SOMEWHERE/notes.md\"", "cannot resolve ($SOMEWHERE)"),
    (f"D=\"$(pwd)\"; echo x > \"$D/{V}/notes.md\"", "cannot resolve ($D)"),
    (f"{RECORDS} > {LINE}/out.txt", "part of the slice line itself"),
], ids=["line-before-records", "product-before-records", "line-after-records", "variable-into-the-line",
        "variable-into-product-code", "variable-into-the-owners-file", "unset-variable", "computed-variable",
        "records-redirected-into-the-line"])
def test_the_same_shapes_writing_elsewhere_are_refused(world, cmd, said):
    p = bash(world, cmd, seat="conductor")
    assert refused(p) and said in p.stderr, (cmd, p.returncode, p.stderr)


def test_a_builder_still_never_runs_a_line_script_in_a_chain(world):
    p = bash(world, f"cp /tmp/x {V}/slices/S9.md && {RECORDS}", seat="builder", wt=world["repo"])
    assert refused(p) and "run by the conductor" in p.stderr, p.stderr
