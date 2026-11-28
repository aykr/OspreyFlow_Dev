"""WS4a round 3: the red cases for the comparison's references, red for each fault planted in
`keyboard/canvasCompare.ts` itself (CLAUDE.md rule 15), then green with the file written back byte for byte. The
committed references and their record are never written: the cases plant theirs in scratch copies.

    python3 OspreyFlow_Build/process/lanes/v062/away/WS4a_records/plant_references.py   (from the repository root)
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

CORE = Path.cwd() / "OspreyFlow_Core"
COMPARE = CORE / "apps/workspace/keyboard/canvasCompare.ts"
HASH = "    else if (record.scenes?.[scene] !== sha256(readFileSync(file))) {\n"
PLANTS = {
    "the hash comparison is turned off (the verifier's)": (HASH, "    else if (false) {\n"),
    "a picture the record has no entry for is let through": (
        HASH, "    else if (record.scenes?.[scene] && record.scenes[scene] !== sha256(readFileSync(file))) {\n"),
    "a missing picture is not reported": (
        "if (!existsSync(file)) problems.push(`no reference for the scene ${scene}`);\n",
        "if (!existsSync(file)) continue;\n"),
    "a record with no reason is taken": ("  if (!record.reason?.trim()) problems.push(", "  if (false) problems.push("),
    "a missing record is no problem": (
        'problems: ["no canvas-compare/', 'problems: [], unsaid: ["no canvas-compare/'),
    "a recorded scene that is gone is let through": (
        "    if (!scenes.includes(scene)) problems.push(", "    if (false) problems.push("),
}  # fmt: skip


def run(label: str) -> None:
    done = subprocess.run(["npm", "exec", "--workspace", "apps/workspace", "--", "vitest", "run",
                           "keyboard/canvasCompare.test.ts"], cwd=CORE, capture_output=True, text=True)  # fmt: skip
    out = re.sub(r"\x1b\[[0-9;]*m", "", done.stdout + done.stderr)
    kept = [line.strip() for line in out.splitlines()
            if line.strip().startswith(("FAIL ", "×", "Tests "))]  # fmt: skip
    print(f"--- {label}: vitest exit {done.returncode}")
    print("\n".join(dict.fromkeys(line[:200] for line in kept)))


def main() -> None:
    good = COMPARE.read_bytes()
    text = good.decode("utf-8")
    run("as it is")
    try:
        for label, (old, new) in PLANTS.items():
            assert text.count(old) == 1, (label, old)
            COMPARE.write_bytes(text.replace(old, new).encode("utf-8"))
            run(f"planted: {label}")
    finally:
        COMPARE.write_bytes(good)
    assert COMPARE.read_bytes() == good, "NOT restored"
    print(f"restored: canvasCompare.ts {hashlib.sha256(good).hexdigest()[:8]}")
    run("restored")


if __name__ == "__main__":
    main()
