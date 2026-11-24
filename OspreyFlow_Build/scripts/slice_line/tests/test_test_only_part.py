"""A test-only part merges through the line (the owner, 24 November 2026, "cut my paperwork", item 2, with his answers).

A part that adds tests and no code cannot show its acceptance red before it: the code it tests is already on main, so
the merge's red-before step refused it ("it was never red"). Now the conductor writes a planted fault for it as a record
(plants/<ID>.patch, committed on main), whose hash is frozen with the acceptance when the part starts; a change to it is
a refreeze. At the merge the line applies it to the base with the acceptance files: the acceptance must be green
without it (the part adds no code), and red with it, on an assertion (a fault that breaks an import or a collection
makes any test red and proves nothing). The fault changes product files only, never a test or an acceptance file, and
it never reaches the merge result.
"""
from __future__ import annotations

import json

from test_gates import TODAY, built, main_sha, merge, sh, started, verified, world  # noqa: F401
from test_resume import V062, changes, owner_line, resume, said_refused, set_state, state

PRODUCT = "OspreyFlow_Build/tool_limit/limit.py"
ACCEPT = ("python3 -c \"import sys; sys.path.insert(0, 'OspreyFlow_Build/tool_limit'); import limit; "
          "assert limit.LIMIT == 10, 'the limit is ten'\"")
PLANTS = f"{V062}/plants"


def patch(path, old, new):
    return (f"--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n-{old}\n+{new}\n")


FAIR = patch(PRODUCT, "LIMIT = 10", "LIMIT = 11")


def on_main(w, files, msg="docs: records"):
    for path, text in files.items():
        f = w["repo"] / path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
    sh(["git", "add", "-A", "--", *files], w["repo"], w["env"])
    sh(["git", "commit", "-qm", msg], w["repo"], w["env"])


def a_test_only_part(w, plant=FAIR, accept=ACCEPT):
    """S1 adds a test of code main already has (limit.py), verified; the conductor's planted fault on main first."""
    on_main(w, {PRODUCT: "LIMIT = 10\n"}, "feat: the limit (on main before S1)")
    if plant is not None:
        on_main(w, {f"{PLANTS}/S1.patch": plant}, "docs(slice-line): S1's planted fault")
    wt, tip = built(w, accept=accept, feature=False)
    verified(w, wt, tip)
    set_state(w, phase="verified", tip=tip)
    return wt, tip


def test_a_test_only_part_with_a_fair_planted_fault_merges(world):
    w = world
    wt, tip = a_test_only_part(w)
    frozen = json.loads((w["data"] / "records/S1/frozen.json").read_text())
    assert frozen.get("plant"), frozen                                          # frozen with the acceptance
    p = merge(w)
    assert p.returncode == 0, p.stdout + p.stderr
    assert (w["data"] / "records/S1/merged.json").exists()
    assert (w["repo"] / PRODUCT).read_text() == "LIMIT = 10\n"                  # the fault never reaches main


def test_without_a_planted_fault_a_test_only_part_is_never_red(world):
    w = world
    a_test_only_part(w, plant=None)
    p = merge(w)
    assert p.returncode == 1 and "it was never red" in p.stderr, p.stderr


def test_a_planted_fault_that_touches_a_test_or_acceptance_file_is_refused(world):
    """Refused when the part starts (the dry run), before anything is frozen: a fault in a test file main already has."""
    w = world
    t = "OspreyFlow_Build/tool_limit/test_limit.py"
    on_main(w, {PRODUCT: "LIMIT = 10\n", t: "x\n", f"{PLANTS}/S1.patch": FAIR + patch(t, "x", "y")}, "docs: S1's fault")
    p, wt = started(w)
    out = p.stdout + p.stderr
    assert p.returncode != 0 and "not product code alone" in out and t in out, out
    assert not (w["data"] / "records/S1/frozen.json").exists()


def test_a_planted_fault_in_a_tests_folder_is_refused(world):
    """Refused when the part starts (the dry run): a fault in a helper of a tests folder main already has."""
    w = world
    t = "OspreyFlow_Build/tests/helpers_x.py"
    on_main(w, {PRODUCT: "LIMIT = 10\n", t: "a\n", f"{PLANTS}/S1.patch": patch(t, "a", "b")}, "docs: S1's fault")
    p, wt = started(w)
    out = p.stdout + p.stderr
    assert p.returncode != 0 and "not product code alone" in out and t in out, out
    assert not (w["data"] / "records/S1/frozen.json").exists()


def test_a_planted_fault_that_breaks_the_import_is_not_an_assertion_red(world):
    w = world
    a_test_only_part(w, plant=patch(PRODUCT, "LIMIT = 10", "LIMIT = = 10"))
    p = merge(w)
    assert p.returncode == 1 and "not on an assertion" in p.stderr and "SyntaxError" in p.stderr, p.stderr


def test_an_acceptance_red_without_the_fault_is_not_a_test_only_part(world):
    w = world
    a_test_only_part(w, accept=ACCEPT.replace("== 10", "== 12"))
    p = merge(w)
    assert p.returncode == 1 and "must be green on the base without its planted fault" in p.stderr, p.stderr


def test_a_planted_fault_that_does_not_apply_is_refused(world):
    """Refused when the part starts (the dry run), before anything is frozen; never as late as the merge."""
    w = world
    on_main(w, {PRODUCT: "LIMIT = 10\n", f"{PLANTS}/S1.patch": patch(PRODUCT, "LIMIT = 99", "LIMIT = 11")}, "docs: S1's fault")
    p, wt = started(w)
    out = p.stdout + p.stderr
    assert p.returncode != 0 and "planted fault" in out and 'patch failed' in out, out
    assert not (w["data"] / "records/S1/frozen.json").exists()


def test_a_planted_fault_changed_after_the_start_is_refused_until_refrozen(world):
    w = world
    a_test_only_part(w)
    on_main(w, {f"{PLANTS}/S1.patch": patch(PRODUCT, "LIMIT = 10", "LIMIT = 12")}, "docs: S1's planted fault, again")
    p = merge(w)
    assert p.returncode == 1 and "not the one frozen" in p.stderr, p.stderr
    owner_line(w, f"S1\trefreeze\t{TODAY}")
    r = resume(w, "S1", "refreeze")
    assert r.returncode == 0 and "planted fault refrozen" in r.stdout, r.stdout + r.stderr
    assert [x[2] for x in changes(w)] == ["refreeze"]
    set_state(w, phase="verified")
    p = merge(w)
    assert p.returncode == 0, p.stdout + p.stderr


def test_a_refreeze_with_nothing_changed_is_still_refused(world):
    w = world
    a_test_only_part(w)
    owner_line(w, f"S1\trefreeze\t{TODAY}")
    r = resume(w, "S1", "refreeze")
    assert said_refused(r, "nothing changed"), r.stdout + r.stderr                # as it always was


def test_an_unfair_planted_fault_is_refused_at_the_start(world):
    w = world
    on_main(w, {PRODUCT: "LIMIT = 10\n", f"{PLANTS}/S1.patch": patch("accept.sh", "x", "y")}, "docs: S1's fault")
    p, wt = started(w)
    assert p.returncode != 0 and "planted fault" in p.stdout + p.stderr, p.stdout + p.stderr
    assert not (w["data"] / "records/S1/frozen.json").exists()


def test_a_planted_fault_the_acceptance_does_not_see_is_never_red(world):
    """A fault in a line the test never reads leaves it green: refused, as any acceptance that was never red."""
    w = world
    on_main(w, {PRODUCT: "LIMIT = 10\n# the limit\n"}, "feat: the limit (on main before S1)")
    on_main(w, {f"{PLANTS}/S1.patch": f"--- a/{PRODUCT}\n+++ b/{PRODUCT}\n@@ -1,2 +1,2 @@\n LIMIT = 10\n-# the limit\n+# a limit\n"},
            "docs(slice-line): S1's planted fault")
    wt, tip = built(w, accept=ACCEPT, feature=False)
    verified(w, wt, tip)
    set_state(w, phase="verified", tip=tip)
    p = merge(w)
    assert p.returncode == 1 and "passes with the planted fault applied" in p.stderr, p.stderr


def test_a_part_frozen_before_planted_faults_existed_merges_as_before(world):
    """frozen.json with no "plant" key (every part started before today): no fault on main matches it."""
    w = world
    wt, tip = built(w)
    verified(w, wt, tip)
    set_state(w, phase="verified", tip=tip)
    f = w["data"] / "records/S1/frozen.json"
    fz = json.loads(f.read_text())
    fz.pop("plant", None)
    f.write_text(json.dumps(fz))
    p = merge(w)
    assert p.returncode == 0, p.stdout + p.stderr
