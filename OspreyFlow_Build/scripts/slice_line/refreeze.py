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
    c.refreeze(sys.argv[1], "owner")
    print(f"{sys.argv[1]}: acceptance and checks refrozen from main's backlog file.")
