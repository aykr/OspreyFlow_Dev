"""WS4a round 2: I20's acceptance tests in the state GG2a's merge leaves main in (the owner's answer to question 1:
that merge writes the `sigma` entry). GG2a's own lockfile, read from its branch at `37492cc`, and the window entry
are planted at the real call site, this checkout's `OspreyFlow_Core/package-lock.json` and
`apps/pages/VERSION_WINDOW.yaml`; the tests run; both files are written back byte for byte and their SHA-256 checked.

    python3 OspreyFlow_Build/process/lanes/v062/away/WS4a_records/plant_gg2a_state.py   (from the repository root)

The Python is the checkout's own `OspreyFlow_Core/.venv`. No other branch is merged: one file of it is read.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

ROOT = Path.cwd()
CORE = ROOT / "OspreyFlow_Core"
LOCK = CORE / "package-lock.json"
WINDOW = CORE / "apps/pages/VERSION_WINDOW.yaml"
GG2A = "37492cc"
ENTRY = """windows:
  - package: sigma
    apps/workspace: 3.0.3
    apps/pages: 4.0.6
    opened: 2026-11-26
"""


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(label: str) -> None:
    env = {**os.environ, "ARCADEDB_HTTP_PORT": "9", "POSTGRES_PORT": "9", "PYTHONDONTWRITEBYTECODE": "1"}
    done = subprocess.run(
        [str(CORE / ".venv/bin/python"), "-m", "pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-p",
         "no:cacheprovider", "-q", "-rf", "../OspreyFlow_Build/tests/glass_trees/test_same_drawing_versions.py"],
        cwd=CORE, env=env, capture_output=True, text=True,
    )  # fmt: skip
    kept = [line for line in done.stdout.splitlines()
            if line.startswith("FAILED") or " passed" in line or " failed" in line]  # fmt: skip
    print(f"--- {label}: pytest exit {done.returncode}")
    print("\n".join(line[:220] for line in kept))


def main() -> None:
    lock, window = LOCK.read_bytes(), WINDOW.read_bytes()
    before = (sha(LOCK), sha(WINDOW))
    planted = subprocess.run(["git", "show", f"{GG2A}:OspreyFlow_Core/package-lock.json"], cwd=ROOT,
                             capture_output=True, check=True).stdout  # fmt: skip
    run("this checkout as it is (window shut)")
    try:
        LOCK.write_bytes(planted)
        kept = window.decode("utf-8")
        assert kept.endswith("windows: []\n"), "the window file does not end as it is written"
        WINDOW.write_bytes((kept.removesuffix("windows: []\n") + ENTRY).encode("utf-8"))
        run(f"planted: GG2a's lockfile at {GG2A} and its `sigma` window entry")
    finally:
        LOCK.write_bytes(lock)
        WINDOW.write_bytes(window)
    assert (sha(LOCK), sha(WINDOW)) == before, "NOT restored"
    print(f"restored: package-lock.json {before[0][:8]}, VERSION_WINDOW.yaml {before[1][:8]}")


if __name__ == "__main__":
    main()
