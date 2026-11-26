"""WS4a round 1 (the owner's answer to question 4): the release-local diff's own cases, red then green in a scratch
copy of the tree with `WS4a_diffs/I20_RELEASE_LOCAL.diff` applied (CLAUDE.md rule 15). Nothing in the checkout is
edited: the scratch copy is made under `OspreyFlow_Build/dist/` (ignored by git) and removed at the end.

    python3 OspreyFlow_Build/process/lanes/v062/away/WS4a_records/plant_release_window.py   (from the repository root)

The copy is `git archive HEAD`: main with this slice merged, which is what main is when the owner applies the diff
(today's main has no `scripts/same_drawing_versions_check.mjs` to ask). The Python is the checkout's own
`OspreyFlow_Core/.venv`.

Round 2 adds two things. The diff only adds, so `git apply --numstat` must count no removed line in either file (round
1's diff also rewrote a line of `test_release_owed.py` it had no business with). And the runs are made again in a copy
holding the state GG2a's merge leaves main in (its lockfile, read from its branch at `37492cc`, and the `sigma` window
entry), since the diff's cases are to hold whether or not the checkout's own window is open.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path.cwd()
SCRATCH = ROOT / "OspreyFlow_Build/dist/ws4a-release-plant"
DIFF = "OspreyFlow_Build/process/lanes/v062/away/WS4a_diffs/I20_RELEASE_LOCAL.diff"
PYTHON = str(ROOT / "OspreyFlow_Core/.venv/bin/python")
CALL = """    refusal = window_refusal()
    if refusal:
        print(f"release_local: refusing — the version window is open:\\n{refusal}", file=sys.stderr)
        return 1
"""
ANSWER = """    return None if p.returncode == 0 else (p.stdout + p.stderr).strip()


def owed_refusal"""
ALWAYS = """    return "planted: refused whatever the window holds"


def owed_refusal"""


def run(label: str) -> None:
    env = {**os.environ, "ARCADEDB_HTTP_PORT": "9", "POSTGRES_PORT": "9", "PYTHONDONTWRITEBYTECODE": "1"}
    done = subprocess.run(
        [PYTHON, "-m", "pytest", "-c", "../OspreyFlow_Build/pytest.ini", "--rootdir", "../OspreyFlow_Build",
         "-p", "no:cacheprovider", "-q", "../OspreyFlow_Build/tests/test_release_owed.py"],
        cwd=SCRATCH / "OspreyFlow_Core", env=env, capture_output=True, text=True,
    )  # fmt: skip
    kept = [line for line in done.stdout.splitlines()
            if line.startswith(("E   ", "FAILED")) or " passed" in line or " failed" in line]  # fmt: skip
    print(f"--- {label}: pytest exit {done.returncode}")
    print("\n".join(line[:200] for line in kept))


GG2A = "37492cc"
ENTRY = """windows:
  - package: sigma
    apps/workspace: 3.0.3
    apps/pages: 4.0.6
    opened: 2026-11-26
"""


def open_the_window() -> None:
    """The scratch copy put in the state GG2a's merge leaves main in."""
    lock = subprocess.run(["git", "show", f"{GG2A}:OspreyFlow_Core/package-lock.json"], cwd=ROOT,
                          capture_output=True, check=True).stdout  # fmt: skip
    (SCRATCH / "OspreyFlow_Core/package-lock.json").write_bytes(lock)
    window = SCRATCH / "OspreyFlow_Core/apps/pages/VERSION_WINDOW.yaml"
    text = window.read_text(encoding="utf-8")
    assert text.endswith("windows: []\n"), "the window file does not end as it is written"
    window.write_text(text.removesuffix("windows: []\n") + ENTRY, encoding="utf-8")


def main() -> None:
    counted = subprocess.run(["git", "apply", "--numstat", DIFF], cwd=ROOT, capture_output=True, text=True, check=True)
    print("--- lines added, removed, by the diff:")
    print(counted.stdout.rstrip())
    shutil.rmtree(SCRATCH, ignore_errors=True)
    SCRATCH.mkdir(parents=True)
    try:
        archive = subprocess.run(["git", "archive", "HEAD", "OspreyFlow_Core", "OspreyFlow_Build"], cwd=ROOT,
                                 capture_output=True, check=True)  # fmt: skip
        subprocess.run(["tar", "-x", "-C", str(SCRATCH)], input=archive.stdout, check=True)
        subprocess.run(["git", "apply", f"--directory={SCRATCH.relative_to(ROOT)}", DIFF], cwd=ROOT, check=True)
        tool = SCRATCH / "OspreyFlow_Build/tools/release_local.py"
        applied = tool.read_text(encoding="utf-8")
        assert applied.count(CALL) == 1 and applied.count(ANSWER) == 1, "the diff did not apply as expected"
        run("the diff applied")
        tool.write_text(applied.replace(CALL, ""), encoding="utf-8")
        run("planted: window_refusal()'s call removed from main()")
        tool.write_text(applied.replace(ANSWER, ALWAYS), encoding="utf-8")
        run("planted: window_refusal() refuses whatever the window holds")
        tool.write_text(applied, encoding="utf-8")
        run("restored")
        open_the_window()
        run("the diff applied, the checkout's own window open as GG2a leaves it")
        tool.write_text(applied.replace(CALL, ""), encoding="utf-8")
        run("window open, planted: window_refusal()'s call removed from main()")
    finally:
        shutil.rmtree(SCRATCH, ignore_errors=True)


if __name__ == "__main__":
    main()
