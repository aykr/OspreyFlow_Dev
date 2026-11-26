"""WS4a round 2: the version check as a gate calls it (`node scripts/same_drawing_versions_check.mjs`, no argument, on
the checkout's own two files), red for planted faults and green with both files written back byte for byte (rule 15).
The window naming `sigma` twice is also given to round 1's script (read from commit aa6bda4), which passed it.

    python3 OspreyFlow_Build/process/lanes/v062/away/WS4a_records/plant_i20_round2.py   (from the repository root)
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path.cwd()
CORE = ROOT / "OspreyFlow_Core"
LOCK = CORE / "package-lock.json"
WINDOW = CORE / "apps/pages/VERSION_WINDOW.yaml"
OLD = ROOT / "OspreyFlow_Build/dist/ws4a-round1-check.mjs"


def entry(pages: str) -> str:
    return f"  - package: sigma\n    apps/workspace: 3.0.3\n    apps/pages: {pages}\n    opened: 2026-11-26\n"


def check(label: str, script: Path | None = None) -> None:
    command = ["node", str(script), str(CORE)] if script else ["node", "scripts/same_drawing_versions_check.mjs"]
    done = subprocess.run(command, cwd=CORE, capture_output=True, text=True)
    print(f"--- {label}: exit {done.returncode}\n{done.stdout.rstrip()}")


def main() -> None:
    lock, window = LOCK.read_bytes(), WINDOW.read_bytes()
    gg2a = subprocess.run(["git", "show", "37492cc:OspreyFlow_Core/package-lock.json"], cwd=ROOT,
                          capture_output=True, check=True).stdout  # fmt: skip
    OLD.parent.mkdir(exist_ok=True)
    OLD.write_bytes(subprocess.run(["git", "show", "aa6bda4:OspreyFlow_Core/scripts/same_drawing_versions_check.mjs"],
                                   cwd=ROOT, capture_output=True, check=True).stdout)  # fmt: skip
    check("the checkout as it is")
    try:
        nested = json.loads(lock)
        nested["packages"]["node_modules/@sigma/node-border/node_modules/sigma"] = {"version": "3.1.0"}
        nested["packages"]["node_modules/@sigma/node-border"]["dependencies"] = {"sigma": "3.1.0"}
        LOCK.write_text(json.dumps(nested, indent=2) + "\n", encoding="utf-8")
        check("planted: Sigma 3.1.0 nested under @sigma/node-border")
        LOCK.write_bytes(gg2a)
        head = window.decode("utf-8").removesuffix("windows: []\n")
        WINDOW.write_text(head + "windows:\n" + entry("4.0.5") + entry("4.0.6"), encoding="utf-8")
        check("planted: GG2a's lockfile, sigma listed twice, the wrong entry first; round 1's script", OLD)
        check("the same files; this round's script")
    finally:
        LOCK.write_bytes(lock)
        WINDOW.write_bytes(window)
        OLD.unlink()
    assert (LOCK.read_bytes(), WINDOW.read_bytes()) == (lock, window), "NOT restored"
    print(f"restored: package-lock.json {hashlib.sha256(lock).hexdigest()[:8]}, "
          f"VERSION_WINDOW.yaml {hashlib.sha256(window).hexdigest()[:8]}")
    check("the checkout as it is, restored")


if __name__ == "__main__":
    main()
