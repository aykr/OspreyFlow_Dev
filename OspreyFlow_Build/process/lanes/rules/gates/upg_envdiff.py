"""UPG: deployment.env compared key by key, never printing a value. Each key's value is hashed
(SHA-256, first 12 hex) so the record shows which keys were added, removed or changed, and that
every other one is byte for byte as before, without carrying a secret.

    python upg_envdiff.py snap <deployment.env> <out.json>
    python upg_envdiff.py diff <before.json> <after.json>   # exit 1 if a key held before changed
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
from pathlib import Path


def snap(env: Path) -> dict[str, object]:
    pairs: dict[str, str] = {}
    for line in env.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and not line.startswith("#"):
            pairs[key] = hashlib.sha256(value.encode()).hexdigest()[:12] + (
                "" if value else " (empty)"
            )
    return {
        "mode": oct(stat.S_IMODE(os.stat(env).st_mode)),
        "file_sha": hashlib.sha256(env.read_bytes()).hexdigest()[:12],
        "keys": pairs,
    }


def main(argv: list[str]) -> int:
    if argv[0] == "snap":
        Path(argv[2]).write_text(json.dumps(snap(Path(argv[1])), indent=1))
        return 0
    before = json.loads(Path(argv[1]).read_text())
    after = json.loads(Path(argv[2]).read_text())
    b, a = before["keys"], after["keys"]
    added = sorted(set(a) - set(b))
    removed = sorted(set(b) - set(a))
    changed = sorted(k for k in set(a) & set(b) if a[k] != b[k])
    print(
        f"upg-envdiff: mode {before['mode']} -> {after['mode']}; "
        f"file {'unchanged' if before['file_sha'] == after['file_sha'] else 'changed'}"
    )
    print(f"upg-envdiff: added {added or 'none'}")
    print(f"upg-envdiff: removed {removed or 'none'}")
    print(f"upg-envdiff: changed {changed or 'none'}")
    print(
        f"upg-envdiff: {len(set(a) & set(b)) - len(changed)} keys held before are byte for byte the same"
    )
    return 1 if changed or removed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
