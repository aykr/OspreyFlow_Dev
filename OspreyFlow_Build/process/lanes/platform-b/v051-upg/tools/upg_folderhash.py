"""UPG: every file under a deployment's folder, hashed with its mode, compared before and after a
step. Never prints a file's content, so deployment.env is safe to include.

    python upg_folderhash.py snap <folder> <out.json> [--skip <relative dir>]...
    python upg_folderhash.py diff <before.json> <after.json>   # exit 1 if anything differs
"""

from __future__ import annotations

import hashlib
import json
import stat
import sys
from pathlib import Path


def snap(folder: Path, skip: list[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for path in sorted(folder.rglob("*")):
        rel = path.relative_to(folder).as_posix()
        if any(rel == s or rel.startswith(s + "/") for s in skip) or not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        found[rel] = f"{digest} {oct(stat.S_IMODE(path.stat().st_mode))}"
    return found


def main(argv: list[str]) -> int:
    if argv[0] == "snap":
        skip = [argv[i + 1] for i, a in enumerate(argv) if a == "--skip"]
        Path(argv[2]).write_text(json.dumps(snap(Path(argv[1]), skip), indent=1))
        return 0
    before = json.loads(Path(argv[1]).read_text())
    after = json.loads(Path(argv[2]).read_text())
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])
    print(f"upg-folderhash: {len(before)} files before, {len(after)} after")
    print(f"upg-folderhash: added {added or 'none'}")
    print(f"upg-folderhash: removed {removed or 'none'}")
    print(f"upg-folderhash: changed (content or mode) {changed or 'none'}")
    return 1 if added or removed or changed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
