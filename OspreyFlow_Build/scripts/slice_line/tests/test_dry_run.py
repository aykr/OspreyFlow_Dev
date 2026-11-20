"""A slice whose frozen commands do not run is not started (the owner's ruling 4(b), 18 November 2026).

slice_start.py proves the commands on main in a scratch worktree first: the checks, with the slice's own new files
stood in, exit 0 and reach the last step of their `&&` chain; the acceptance is red for a reason that is no malformed
command's. The two real malformed commands of 18 November are each refused at start: BL6's `make -C` to a folder that
is not there (after a `cd`), and AD2's Playwright run in a linked worktree with no port slot.
"""
from __future__ import annotations

import json

import pytest

from test_gates import sh, started, world  # noqa: F401  (world is a fixture)

V062 = "OspreyFlow_Build/process/lanes/v062"
#: OspreyFlow_Core/apps/lanePorts.ts's refusal, as `npm run test:keyboard` prints it in a linked worktree with no slot
PLAYWRIGHT = r'''#!/bin/sh
# a stand-in for `npm run test:keyboard`: lanePorts.ts's slotOf() in a linked worktree
if [ -z "$OSPREY_PORTS_SLOT" ] && [ "$(git rev-parse --git-dir)" != "$(git rev-parse --git-common-dir)" ]; then
  echo "Error: this checkout is a linked worktree and OSPREY_PORTS_SLOT is not set, so its Playwright ports would be the main checkout's"
  exit 1
fi
echo "47 passed"
'''


def row(w, acceptance="sh accept.sh", checks="true", files="accept.sh", extra=None):
    """S1's row on main with these commands, and any files main holds for them."""
    r = w["repo"]
    for rel, text in (extra or {}).items():
        (r / rel).parent.mkdir(parents=True, exist_ok=True)
        (r / rel).write_text(text)
        if rel.endswith(".sh"):
            (r / rel).chmod(0o755)
    tsv = r / V062 / "slices.tsv"
    tsv.write_text(tsv.read_text().replace("S1\tCO1\tA test slice\t-\t1\t-\tnone\taccept.sh\tsh accept.sh\ttrue",
                                           f"S1\tCO1\tA test slice\t-\t1\t-\tnone\t{files}\t{acceptance}\t{checks}"))
    sh("git add -A . ':!OspreyFlow_Core/osprey.yaml' && git commit -qm 'docs: S1' --trailer 'Slice-Records: yes'", r, w["env"])


def not_started(w, p):
    assert p.returncode != 0, p.stdout + p.stderr
    assert "Traceback" not in p.stderr, p.stderr
    assert not (w["data"] / "records/S1/frozen.json").exists()
    assert not (w["tmp"] / "wt/slice-S1").exists()
    return p.stdout + p.stderr


def test_slice_start_refuses_bl6s_make_path_after_a_cd(world):
    w = world
    row(w, checks="cd OspreyFlow_Core && make -C OspreyFlow_Build all", extra={"OspreyFlow_Build/Makefile": "all:\n\t@true\n"})
    said = not_started(w, started(w)[0])
    assert "make names a folder that does not exist" in said and "on main" in said, said


def test_the_dry_run_refuses_ad2s_playwright_with_no_port_slot(world):
    """AD2's commands as of 18 November, proved with no slot: refused, by signature. (slice_start.py now gives every
    slice a slot of its own, so the same command starts: test_settings.py.)"""
    w = world
    row(w, checks="cd OspreyFlow_Core && sh ../tools/keyboard.sh", extra={"tools/keyboard.sh": PLAYWRIGHT})
    code = (f"import sys, json; sys.path.insert(0, {str(w['lines'])!r}); import common as c, dry_run; "
            "print(json.dumps(dry_run.prove(c.slice_row('S1'), slot=None)))")
    p = sh([w["py"], "-c", code], w["repo"], w["env"])
    said = " ".join(json.loads(p.stdout.splitlines()[-1]))
    assert "OSPREY_PORTS_SLOT is not set" in said and "Playwright in a linked worktree with no port slot" in said, said


def test_slice_start_says_which_step_of_the_chain_it_did_not_reach(world):
    w = world
    row(w, checks="true && false && echo the-last-step")
    said = not_started(w, started(w)[0])
    assert "step 2 of 3" in said and "never reached the last (echo the-last-step)" in said, said


def test_slice_start_refuses_an_acceptance_that_is_never_red(world):
    w = world
    row(w, acceptance="true")
    said = not_started(w, started(w)[0])
    assert "never red" in said, said


def test_slice_start_refuses_an_acceptance_red_only_for_a_malformed_command(world):
    w = world
    row(w, acceptance="make -C nowhere all")
    said = not_started(w, started(w)[0])
    assert "acceptance command is red on main for a malformed command" in said, said


def test_slice_start_stands_in_the_slices_own_new_test_file_and_runs_every_step(world):
    w = world
    py = f"{w['py']} -m pytest -q -p no:cacheprovider"
    row(w, files="tests/test_new.py", acceptance=f"{py} tests/test_new.py",
        checks=f"{py} tests/test_new.py && echo reached-the-end")
    p, wt = started(w)
    assert p.returncode == 0, p.stdout + p.stderr
    assert json.loads((w["data"] / "records/S1/frozen.json").read_text())["checks"].endswith("reached-the-end")
    assert not (wt / "tests/test_new.py").exists()  # the stand-in was main's scratch copy's, never the slice's
