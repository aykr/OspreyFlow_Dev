#!/usr/bin/env python3
"""A slice's frozen commands, proved on main in a scratch worktree before they are trusted (README, "A slice's life").

Used by slice_start.py (a slice whose commands do not run is not started) and by resume.py's correct-command (a
corrected command is proved here first). On main:

- the checks command, without the slice's own new files, must exit 0 and reach the last step of its `&&` chain:
  each acceptance file the slice adds (absent on main) stands as a placeholder test that passes, so the command
  keeps its shape and runs every step; every `&&` is marked, so a red run says which step it did not reach (18
  November 2026: a dry run stopped at vitest and never reached Playwright, and the slice stopped there six times);
- the acceptance command must be red, for a reason that matches no malformed-command signature (with the slice's
  acceptance files from its branch, when it has any yet).

The signatures are the conductor's own malformed commands, as the line has met them; a genuine failing assertion
matches none.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402
import merge_slice as ms  # noqa: E402
import stop_check  # noqa: E402

#: The conductor's own malformed commands, as the line has met them (18 November 2026: BL6's `make -C` path after a
#: `cd`; AD2's Playwright with no port slot). Add one only for a failure that can never be a test's own.
MALFORMED = (
    (re.compile(r"make(?:\[\d+\])?: \*\*\* [^\n]*: No such file or directory"), "make names a folder that does not exist"),
    (re.compile(r"OSPREY_PORTS_SLOT is not set"), "Playwright in a linked worktree with no port slot"),
)
#: What a genuine test failure prints: an output with any of these is never taken as only a malformed command.
GENUINE = re.compile(r"^(FAILED|ERROR) |AssertionError|\b\d+ failed\b|^E\s|^\s*(✗|×|✘) ", re.M)
TIMEOUT_S = 1800

PLACEHOLDERS = (
    (re.compile(r"\.py$"), "def test_placeholder_for_the_slices_own_file():\n    pass\n"),
    (re.compile(r"\.spec\.[cm]?[jt]sx?$"), "import { test } from '@playwright/test';\n\ntest('placeholder', () => {});\n"),
    (re.compile(r"\.test\.[cm]?[jt]sx?$"), "import { test } from 'vitest';\n\ntest('placeholder', () => {});\n"),
)


def malformed(output: str) -> str | None:
    """Which malformed-command signature this output matches, or None."""
    for pat, what in MALFORMED:
        if pat.search(output):
            return what
    return None


def genuine(output: str) -> bool:
    return bool(GENUINE.search(output))


def and_positions(cmd: str) -> list[int]:
    """Where each `&&` outside quotes is."""
    out, quote, i = [], "", 0
    while i < len(cmd):
        ch = cmd[i]
        if quote:
            if ch == "\\" and quote == '"':
                i += 2
                continue
            if ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch == "\\":
            i += 2
            continue
        elif cmd.startswith("&&", i):
            out.append(i)
            i += 2
            continue
        i += 1
    return out


def steps(cmd: str) -> list[str]:
    return [cmd[a:b] for a, b in step_spans(cmd)]


def step_spans(cmd: str) -> list[tuple[int, int]]:
    """Where each step of the command's `&&` chain is, its surrounding blanks left out."""
    cuts = [0, *[p + 2 for p in and_positions(cmd)]]
    ends = [*and_positions(cmd), len(cmd)]
    out = []
    for a, b in zip(cuts, ends):
        while a < b and cmd[a].isspace():
            a += 1
        while b > a and cmd[b - 1].isspace():
            b -= 1
        out.append((a, b))
    return out


#: A failing test as pytest's summary names it (`FAILED <node id> - <why>`, `ERROR <node id>`), its id as pytest gives it.
FAILING_ID = re.compile(r"^(?:FAILED|ERROR) (\S+)", re.M)


def failing_ids(output: str) -> list[str]:
    """The failing tests' ids in an output, each once, in order."""
    return list(dict.fromkeys(FAILING_ID.findall(output or "")))


def id_path(test_id: str) -> str:
    """The file of a test id (`../OspreyFlow_Build/tests/test_x.py::test_y` -> `OspreyFlow_Build/tests/test_x.py`)."""
    p = test_id.split("::", 1)[0]
    while p.startswith(("./", "../")):
        p = p[2:] if p.startswith("./") else p[3:]
    return p


def stand_in(tree: Path, files: list[str]) -> list[str]:
    """Each of the slice's own new test files absent from `tree`, stood in by a placeholder that passes; the ones written."""
    out = []
    for f in files:
        if (tree / f).exists():
            continue
        body = next((b for pat, b in PLACEHOLDERS if pat.search(f)), None)
        if body is not None:
            (tree / f).parent.mkdir(parents=True, exist_ok=True)
            (tree / f).write_text(body)
            out.append(f)
    return out


def builder_shaped(tree: Path) -> list[str]:
    """`tree` given what the line puts in every builder worktree beside the branch: main's RULINGS.md copy (the copy
    every seat reads, in the tree's own git folder) and the client names' hashed list where git ignores it. What was
    put there, in words."""
    import slice_start  # here, not at the top: slice_start.py imports this module
    copy = c.deliver_rulings(tree)
    return [f"the rulings copy ({c.RULINGS_COPY_REL})" if copy else "no rulings copy (main has no RULINGS.md)",
            slice_start.bring_client_hashes(tree)]


def checks_in_tree(spec: dict, tree: Path, slot: int | str | None, log: Path | None) -> list[str]:
    """The checks column run in `tree` as it stands, in the environment the builder's Stop hook gives it
    (stop_check.seat_env), each of the slice's own new test files stood in: why it is not green (empty when it is).
    A red run names the step it stopped at and the failing tests."""
    if not spec.get("checks"):
        return []
    written = stand_in(tree, acceptance_files(spec))
    try:
        code, out, reached = run_marked(spec["checks"], tree, stop_check.seat_env(str(tree), slot), log)
    finally:
        for f in written:
            (tree / f).unlink(missing_ok=True)
    if code == 0:
        return []
    parts = steps(spec["checks"])
    failing = failing_ids(out)
    return [f"the checks are red in the slice's own worktree (exit {code}): step {reached + 1} of {len(parts)} "
            f"cannot pass there: {parts[min(reached, len(parts) - 1)][:300]}"
            + (f" and the chain never reached the last ({parts[-1][:120]})" if reached + 1 < len(parts) else "")
            + (f"; failing: {', '.join(failing[:10])}" if failing else "")
            + (f"; malformed: {malformed(out)}" if malformed(out) else "") + "\n" + tail(out)]


def instrument(cmd: str, marks: Path) -> str:
    """The command with a mark written after each step of its `&&` chain (to a file, so no redirection hides it)."""
    out, last = [], 0
    for n, p in enumerate(and_positions(cmd), start=1):
        out.append(cmd[last:p] + f'&& {{ echo {n} >> "{marks}"; }} &&')
        last = p + 2
    out.append(cmd[last:])
    return "".join(out)


def run_marked(cmd: str, tree: Path, env: dict, log: Path | None = None) -> tuple[int, str, int]:
    """(exit, output, steps reached) of the command run in `tree`."""
    fd, name = tempfile.mkstemp(prefix="slice-marks-")
    os.close(fd)
    marks = Path(name)
    try:
        try:
            p = subprocess.run(instrument(cmd, marks), shell=True, cwd=str(tree), env=env, capture_output=True,
                               text=True, timeout=TIMEOUT_S)
            code, out = p.returncode, (p.stdout or "") + "\n" + (p.stderr or "")
        except subprocess.TimeoutExpired:
            code, out = 124, f"timed out after {TIMEOUT_S} s"
        reached = len([ln for ln in marks.read_text().splitlines() if ln.strip()])
    finally:
        marks.unlink(missing_ok=True)
    if log:
        with log.open("a") as fh:
            fh.write(f"\n$ {cmd}   (in {tree}; exit {code})\n{out}\n")
    return code, out, reached


def tail(out: str, n: int = 12) -> str:
    return "\n".join([ln for ln in out.splitlines() if ln.strip()][-n:])


def scratch_tree(ref: str = "main") -> Path:
    d = c.gate_dir("slice-dryrun-")  # 65: the line's own tmp, never the system's
    shutil.rmtree(d)
    c.git(["worktree", "add", "--detach", str(d), ref], c.REPO)
    return d


def drop_tree(d: Path) -> None:
    c.git(["worktree", "remove", "--force", str(d)], c.REPO, check=False)
    shutil.rmtree(d, ignore_errors=True)


def acceptance_files(spec: dict) -> list[str]:
    return [f.strip() for f in (spec.get("acceptance_files") or "").split(",") if f.strip()]


def prove(spec: dict, slot: int | str | None = None, tip: str | None = None, log: Path | None = None,
          checks: bool = True) -> list[str]:
    """Why the slice's commands are not proved on main (empty when they are). `spec` holds acceptance_files,
    acceptance and checks; `slot` is the slice's Playwright slot; `tip`, the slice's branch tip, gives its acceptance
    files to the acceptance run. The runs get the environment the merge script's runs get (merge_slice.slice_env:
    built as CI builds it, its venv outside the scratch tree, closed ports, the slot). `checks=False` leaves the checks
    to slice_start.py, which runs them in the slice's own worktree (checks_in_tree)."""
    problems: list[str] = []
    with c.heartbeat(f"dry run of {spec.get('id') or 'a slice'}'s commands on main"):  # the owner, 25 November 2026
        return _prove(spec, slot, tip, log, checks, problems)


def _prove(spec: dict, slot, tip, log, checks: bool, problems: list[str]) -> list[str]:
    tree = scratch_tree("main")
    venv = c.gate_dir("slice-dryrun-venv-")
    if log is None:
        fd, name = tempfile.mkstemp(prefix="slice-dryrun-", suffix=".log")
        os.close(fd)
        log = Path(name)
    try:
        try:
            env = ms.slice_env(tree, log, slot, venv)
        except ms.GateEnvError as e:
            return [f"the environment for the commands could not be built on main: {e}"]
        files = acceptance_files(spec)
        new = [f for f in files if not (tree / f).exists()]
        if spec.get("checks") and checks:
            stood = stand_in(tree, new)
            code, out, reached = run_marked(spec["checks"], tree, env, log)
            parts = steps(spec["checks"])
            if code != 0:
                where = (f"it stopped at step {reached + 1} of {len(parts)} ({parts[min(reached, len(parts) - 1)][:120]})"
                         + (f" and never reached the last ({parts[-1][:120]})" if reached + 1 < len(parts) else ""))
                problems.append(f"the checks are red on main (exit {code}): {where}"
                                + (f"; malformed: {malformed(out)}" if malformed(out) else "") + "\n" + tail(out))
            for f in stood:
                (tree / f).unlink(missing_ok=True)
        if spec.get("acceptance"):
            for f in files:
                if tip:
                    blob = subprocess.run(["git", "show", f"{tip}:{f}"], cwd=c.REPO, capture_output=True)
                    if blob.returncode == 0:
                        (tree / f).parent.mkdir(parents=True, exist_ok=True)
                        (tree / f).write_bytes(blob.stdout)
            plant = c.plant_text(spec.get("id") or "") if spec.get("id") else ""
            if plant:  # a test-only part (item 2): its planted fault, applied to main, must be fair and apply
                why = ms.plant_unfair(plant, files) or ms.apply_plant(tree, plant)
                if why:
                    problems.append(f"the planted fault ({c.PLANTS_REL}/{spec['id']}.patch) does not stand: {why}")
            code, out, _ = run_marked(spec["acceptance"], tree, env, log)
            if code == 0:
                problems.append("the acceptance command passes on main" + (" with its planted fault" if plant else "")
                                + ": it was never red")
            elif plant and tip and ms.not_assertion_red(out):
                problems.append(f"the acceptance is red with its planted fault, but not on an assertion "
                                f"({ms.not_assertion_red(out)})")
            elif malformed(out):
                problems.append(f"the acceptance command is red on main for a malformed command ({malformed(out)}), "
                                "not for the slice's missing work:\n" + tail(out))
    finally:
        shutil.rmtree(venv, ignore_errors=True)
        drop_tree(tree)
    return problems
