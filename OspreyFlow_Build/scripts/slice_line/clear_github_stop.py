#!/usr/bin/env python3
"""Clear the GitHub stop (LINE_FIXES_4_BRIEF.md, 1c; the owner's ruling of 20 November 2026). The owner's, and refused
to every agent by the guard (OWNER_SCRIPTS), as clear_account.py is.

    clear_github_stop.py

The stop (`github.stopped.json` in the data folder) is written by `merge_slice.py watch-github` when one test of ours
failed in a run on main and in the rerun of the same commit; while it is there, every merge is refused, naming the
test, the job and the commit. Once the owner has dealt with it (a fix merged, or judged not ours), this removes it and
appends one line for audit to `github-stop-clears.tsv`, beside owner-changes.tsv: the time, the stop's key (the commit
and both runs), the test, the job and the commit. watch-github reads that file, so the same pair of runs never writes
the stop again; a new failure on a later run can. Refused, changing nothing, when there is no stop.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402

HEADER = "at\tkey\ttest\tjob\tcommit\truns\n"


def clear() -> str:
    if not c.GITHUB_STOP.exists():
        raise SystemExit("Refused: there is no GitHub stop (github.stopped.json): nothing to clear.")
    stop = c.read_json(c.GITHUB_STOP) or {}
    runs = ", ".join(f"{r.get('run')}/{r.get('attempt')}" for r in stop.get("runs", []))
    row = [c.now(), str(stop.get("key") or "unreadable"), str(stop.get("test", "")), str(stop.get("job", "")),
           str(stop.get("commit", "")), runs]
    c.GITHUB_CLEARS.parent.mkdir(parents=True, exist_ok=True)
    if not c.GITHUB_CLEARS.exists():
        c.GITHUB_CLEARS.write_text(HEADER)
    with c.GITHUB_CLEARS.open("a") as fh:
        fh.write("\t".join(v.replace("\t", " ").replace("\n", " ") for v in row) + "\n")
    c.GITHUB_STOP.unlink()
    return (f"The GitHub stop is cleared ({stop.get('test') or 'a stop that could not be read'}, commit "
            f"{str(stop.get('commit', ''))[:10]}); logged in {c.GITHUB_CLEARS.name}. Merges may go on.")


def main() -> int:
    if len(sys.argv) > 1:
        print("Refused: clear_github_stop.py takes no arguments.", file=sys.stderr)
        return 1
    try:
        said = clear()
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 1
    print(said)
    subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "board.py"), "--quiet"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
