"""WS4a round 2: the canvas marks' unit tests, red for each fault planted in `src/canvas/canvasMarks.ts` itself
(CLAUDE.md rule 15), then green with the file written back byte for byte.

    python3 OspreyFlow_Build/process/lanes/v062/away/WS4a_records/plant_canvas_marks.py   (from the repository root)
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

CORE = Path.cwd() / "OspreyFlow_Core"
MARKS = CORE / "apps/workspace/src/canvas/canvasMarks.ts"
PLANTS = {
    "the teardown leaves the state mark on": ('    markState(element, null);\n  };', '  };'),
    "nothing listens for a finished frame": ('  sigma.on("afterRender", drawn);\n', ""),
    "the teardown leaves its listener on": (
        '  return () => {\n    sigma.removeListener("afterRender", drawn);\n', "  return () => {\n"),
    "drawn is said without waiting for a frame": (
        '  markState(element, "mounted");\n', '  markState(element, "drawn");\n'),
}  # fmt: skip


def run(label: str) -> None:
    done = subprocess.run(["npm", "exec", "--workspace", "apps/workspace", "--", "vitest", "run",
                           "src/canvas/canvasMarks.test.ts"], cwd=CORE, capture_output=True, text=True)  # fmt: skip
    out = re.sub(r"\x1b\[[0-9;]*m", "", done.stdout + done.stderr)
    kept = [line.strip() for line in out.splitlines()
            if line.strip().startswith(("FAIL ", "×", "Tests "))]  # fmt: skip
    print(f"--- {label}: vitest exit {done.returncode}")
    print("\n".join(dict.fromkeys(line[:200] for line in kept)))


def main() -> None:
    good = MARKS.read_bytes()
    text = good.decode("utf-8")
    run("as it is")
    try:
        for label, (old, new) in PLANTS.items():
            assert text.count(old) == 1, (label, old)
            MARKS.write_bytes(text.replace(old, new).encode("utf-8"))
            run(f"planted: {label}")
    finally:
        MARKS.write_bytes(good)
    assert MARKS.read_bytes() == good, "NOT restored"
    print(f"restored: canvasMarks.ts {hashlib.sha256(good).hexdigest()[:8]}")


if __name__ == "__main__":
    main()
