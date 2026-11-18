#!/usr/bin/env python3
"""The live tests owed (process/lanes/v062/slice-line/README.md, "The live step"): computed, never kept by hand.

While the owner's live_step.yaml has the merge script's live step off, a slice whose change reaches live test files
merges on the offline gates, and its merge record (`records/<ID>/merged.json`, `live_step.not_run`) names each live
file not run. Each is owed until a live run that passed has run it since (`live-paid.json`, written by the merge
script's live step when it is on: it runs every owed file beside the ones its change reaches). A release is refused
while anything is owed.

    owed.py           list what is owed
    owed.py check     exit 1, naming each owed file, while anything is owed or the records cannot be read;
                      the release paths call this (OspreyFlow_Build/tools/release_local.py,
                      OspreyFlow_Build/scripts/publish_user_repo_update.sh)

The standard library only, so the system's python3 runs it.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

DATA = Path(os.environ.get("OSPREY_SLICE_HOME") or Path.home() / ".ospreyflow" / "slice-line")
PAID = "live-paid.json"


class Unreadable(Exception):
    pass


def _json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        raise Unreadable(f"{path} cannot be read ({e})")
    if not isinstance(data, dict):
        raise Unreadable(f"{path} is not a JSON object")
    return data


def outstanding(data: Path = DATA) -> tuple[dict[str, dict], list[str]]:
    """Each owed file -> the latest merge that left it unrun ({slice, merge, at}), and the records that could not be
    read (a reader that cannot tell must not say nothing is owed)."""
    owing: dict[str, dict] = {}
    problems: list[str] = []
    for f in sorted((data / "records").glob("*/merged.json")):
        try:
            rec = _json(f)
            live = rec.get("live_step") or {}
            if not isinstance(live, dict) or not isinstance(live.get("not_run", []), list):
                raise Unreadable(f"{f}: live_step is not a record of files not run")
            for t in live.get("not_run", []):
                was = owing.get(t)
                if was is None or str(rec.get("at", "")) > was["at"]:
                    owing[t] = {"slice": rec.get("slice", f.parent.name), "merge": rec.get("merge", ""),
                                "at": str(rec.get("at", ""))}
        except Unreadable as e:
            problems.append(str(e))
    paid: dict = {}
    if (data / PAID).exists():
        try:
            paid = _json(data / PAID)
        except Unreadable as e:
            problems.append(str(e))
    return {t: o for t, o in owing.items() if not (isinstance(paid.get(t), dict) and str(paid[t].get("at", "")) > o["at"])}, problems


def record_paid(tests: list[str], merge: str, log: str, data: Path = DATA) -> None:
    """A live run that passed ran these files: each is paid as of now."""
    path = data / PAID
    paid = _json(path) if path.exists() else {}
    at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for t in tests:
        paid[t] = {"at": at, "merge": merge, "log": log}
    tmp = path.with_name(f".{PAID}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(paid, indent=1, sort_keys=True) + "\n")
    os.replace(tmp, path)


def main(argv: list[str]) -> int:
    owed, problems = outstanding()
    for p in problems:
        print(f"owed.py: {p}", file=sys.stderr)
    for t, o in sorted(owed.items()):
        print(f"owed: {t}   (slice {o['slice']}, merge {o['merge'][:10]}, {o['at']})")
    if argv[1:2] == ["check"]:
        if problems:
            print("Refused: the slice line's records cannot be read, so what live tests are owed is not known.",
                  file=sys.stderr)
            return 1
        if owed:
            print(f"Refused: {len(owed)} live test files are owed (merged while the live step was off) and have not "
                  "run since. A release waits until every one has run green: turn the live step on "
                  "(OspreyFlow_Build/process/lanes/v062/live_step.yaml) and the next merge runs them.", file=sys.stderr)
            return 1
        print("No live test is owed.")
    elif not owed:
        print("No live test is owed.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
