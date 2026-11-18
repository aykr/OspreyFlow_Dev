#!/usr/bin/env python3
"""The owner's word on a started slice's acceptance or checks (README.md, "Frozen commands").

    refreeze.py <slice>     run by the owner only (the guard refuses it from any agent)

Takes the slice's acceptance files, acceptance and checks commands from main's backlog file into its frozen
record, keeping the previous ones in the record's history.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: refreeze.py <slice>")
    sid = sys.argv[1]
    f = c.rec_dir(sid) / "frozen.json"
    frozen = c.read_json(f) or {}
    if not frozen:
        raise SystemExit(f"{sid} has not started.")
    row = c.slice_row(sid)
    frozen.setdefault("history", []).append({k: frozen.get(k) for k in (*c.FROZEN_KEYS, "frozen_at")})
    frozen.update({k: row[k] for k in c.FROZEN_KEYS})
    frozen["frozen_at"] = c.now()
    frozen["refrozen_by"] = "owner"
    c.write_json(f, frozen)
    print(f"{sid}: acceptance and checks refrozen from main's backlog file.")
