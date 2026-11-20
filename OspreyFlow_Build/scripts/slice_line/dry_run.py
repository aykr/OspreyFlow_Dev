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
    cuts = [0, *[p + 2 for p in and_positions(cmd)]]
    ends = [*and_positions(cmd), len(cmd)]
    return [cmd[a:b].strip() for a, b in zip(cuts, ends)]


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
    d = Path(tempfile.mkdtemp(prefix="slice-dryrun-"))
    shutil.rmtree(d)
    c.git(["worktree", "add", "--detach", str(d), ref], c.REPO)
    return d


def drop_tree(d: Path) -> None:
    c.git(["worktree", "remove", "--force", str(d)], c.REPO, check=False)
    shutil.rmtree(d, ignore_errors=True)


def acceptance_files(spec: dict) -> list[str]:
    return [f.strip() for f in (spec.get("acceptance_files") or "").split(",") if f.strip()]


def prove(spec: dict, slot: int | str | None = None, tip: str | None = None, log: Path | None = None) -> list[str]:
    """Why the slice's commands are not proved on main (empty when they are). `spec` holds acceptance_files,
    acceptance and checks; `slot` is the slice's Playwright slot; `tip`, the slice's branch tip, gives its acceptance
    files to the acceptance run. The runs get the environment the merge script's runs get (merge_slice.slice_env:
    built as CI builds it, its venv outside the scratch tree, closed ports, the slot)."""
    problems: list[str] = []
    tree = scratch_tree("main")
    venv = Path(tempfile.mkdtemp(prefix="slice-dryrun-venv-"))
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
        if spec.get("checks"):
            stand_in = []
            for f in new:
                body = next((b for pat, b in PLACEHOLDERS if pat.search(f)), None)
                if body is not None:
                    (tree / f).parent.mkdir(parents=True, exist_ok=True)
                    (tree / f).write_text(body)
                    stand_in.append(f)
            code, out, reached = run_marked(spec["checks"], tree, env, log)
            parts = steps(spec["checks"])
            if code != 0:
                where = (f"it stopped at step {reached + 1} of {len(parts)} ({parts[min(reached, len(parts) - 1)][:120]})"
                         + (f" and never reached the last ({parts[-1][:120]})" if reached + 1 < len(parts) else ""))
                problems.append(f"the checks are red on main (exit {code}): {where}"
                                + (f"; malformed: {malformed(out)}" if malformed(out) else "") + "\n" + tail(out))
            for f in stand_in:
                (tree / f).unlink(missing_ok=True)
        if spec.get("acceptance"):
            for f in files:
                if tip:
                    blob = subprocess.run(["git", "show", f"{tip}:{f}"], cwd=c.REPO, capture_output=True)
                    if blob.returncode == 0:
                        (tree / f).parent.mkdir(parents=True, exist_ok=True)
                        (tree / f).write_bytes(blob.stdout)
            code, out, _ = run_marked(spec["acceptance"], tree, env, log)
            if code == 0:
                problems.append("the acceptance command passes on main: it was never red")
            elif malformed(out):
                problems.append(f"the acceptance command is red on main for a malformed command ({malformed(out)}), "
                                "not for the slice's missing work:\n" + tail(out))
    finally:
        shutil.rmtree(venv, ignore_errors=True)
        drop_tree(tree)
    return problems
