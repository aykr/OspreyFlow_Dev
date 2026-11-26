"""WS4a round 1 (the owner's answer to question 4): the release-local diff's own cases, red then green in a scratch
copy of the tree with `WS4a_diffs/I20_RELEASE_LOCAL.diff` applied (CLAUDE.md rule 15). Nothing in the checkout is
edited: the scratch copy is made under `OspreyFlow_Build/dist/` (ignored by git) and removed at the end.

    python3 OspreyFlow_Build/process/lanes/v062/away/WS4a_records/plant_release_window.py   (from the repository root)

The copy is `git archive HEAD`: main with this slice merged, which is what main is when the owner applies the diff
(today's main has no `scripts/same_drawing_versions_check.mjs` to ask). The Python is the checkout's own
`OspreyFlow_Core/.venv`.
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


def main() -> None:
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
    finally:
        shutil.rmtree(SCRATCH, ignore_errors=True)


if __name__ == "__main__":
    main()
