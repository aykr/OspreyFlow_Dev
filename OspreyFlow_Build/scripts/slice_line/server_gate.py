"""The demo server's result, read for merging (the owner's word of 22 November 2026, his file 004 to the fifth line-fix
session): the Mac's side. The server's side (the runner, early_warning.py and its notes) is the demo-server session's.

A result counts only as the runner gave it, fetched by its run id (`early_warning.py fetch <id>`, the runner's own
JSON), never as a note says it: the note in the lanes folder is read for the run id alone, and a note edited by hand
changes nothing a script trusts. Every use is behind the owner's switch, `~/.ospreyflow/slice-line/server_counts`:
the exact word `on` (a regular file, not a link) is on; absent, empty or anything else is off, as built. Off, the line
does exactly what it did before, and only records what the server would have changed (the shadow, item 4).

Item 1, before the slot: a verified slice the server shows red is not given the merge slot until its named tests have
been rerun on the Mac (`merge_slice.py server-rerun <ID>`): green there, it queues as before; red there, it goes back
to its builder as a gate refusal. A slice with no server result queues as before.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import common as c

HERE = Path(__file__).resolve().parent
SWITCH = "server_counts"
#: The runner's job id: 16 lower-case hexadecimal characters (the demo-server session's one pattern).
RUN_ID = re.compile(r"\A[0-9a-f]{16}\Z")
NOTES_REL = f"{c.V062_REL}/early_warning"
NOTE_RUN_ID = re.compile(r"^- Run id: `([0-9a-f]{16})`\s*$", re.M)
FETCH_SECONDS = 300


def counting() -> bool:
    """The owner's switch: the exact word `on` in a regular file of his; anything else is off."""
    f = c.DATA / SWITCH
    try:
        if f.is_symlink() or not f.is_file():
            return False
        return f.read_text() in ("on", "on\n")
    except OSError:
        return False


def note_of(slice_id: str, tip: str) -> Path:
    return c.REPO / NOTES_REL / f"{slice_id}-{tip[:8]}.md"


def run_id(slice_id: str, tip: str) -> str | None:
    """The run id the slice's note names for this tip; a pointer only (what it points to is checked when fetched)."""
    try:
        m = NOTE_RUN_ID.search(note_of(slice_id, tip).read_text())
    except OSError:
        return None
    return m.group(1) if m else None


def fetch(rid: str | None) -> dict | None:
    """The runner's own result for this run id, through early_warning.py; None when it cannot be fetched."""
    if not rid or not RUN_ID.match(rid):
        return None
    tool = HERE / "early_warning.py"
    if not tool.is_file():
        return None
    try:
        p = subprocess.run([sys.executable, str(tool), "fetch", rid], capture_output=True, text=True,
                           timeout=FETCH_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if p.returncode != 0:
        return None
    for ln in reversed(p.stdout.splitlines()):
        try:
            data = json.loads(ln)
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("state") and data.get("id") == rid:
            return data
    return None


def element(result: dict | None, slice_id: str, tip: str) -> dict | None:
    """This slice's part of a result: the result itself for a single slice, or its element of a stack; None when the
    result is not for this slice at this tip."""
    if not isinstance(result, dict):
        return None
    if isinstance(result.get("stack"), list):
        for e in result["stack"]:
            if isinstance(e, dict) and e.get("slice") == slice_id and e.get("tip") == tip:
                return {**e, "id": result.get("id"), "state": result.get("state")}
        return None
    return result if result.get("slice") == slice_id and result.get("tip") == tip else None


def failing_names(e: dict) -> tuple[list[str], list[str]]:
    """(the failing tests, the failing targets with no test named under them) of a red result."""
    f = e.get("failing") or {}
    tests = [t for t in f.get("tests") or [] if isinstance(t, str) and t]
    by_target = f.get("by_target") or {}
    bare = [t for t in f.get("targets") or [] if isinstance(t, str) and t and not by_target.get(t)]
    return tests, bare


def server_result(slice_id: str, tip: str) -> tuple[str | None, dict | None]:
    """(run id, this slice's element) as fetched; (rid, None) when the note names a run that cannot be fetched or is
    not for this slice at this tip."""
    rid = run_id(slice_id, tip)
    return rid, element(fetch(rid), slice_id, tip)


def is_red(e: dict | None) -> bool:
    return bool(e) and e.get("state") == "done" and e.get("verdict") == "fail"


def rerun_record(slice_id: str, rid: str) -> Path:
    return c.rec_dir(slice_id) / f"server-rerun-{rid}.json"


def slot_hold(slice_id: str, tip: str) -> str | None:
    """Why the slice is not given the merge slot (item 1), or None. Only with the switch on; only for a red result the
    runner gave for this slice at this tip; until a rerun on the Mac of its named tests is recorded green."""
    if not counting():
        return None
    rid, e = server_result(slice_id, tip)
    if not is_red(e):
        return None
    done = c.read_json(rerun_record(slice_id, rid)) or {}
    if done.get("tip") == tip and done.get("result") == "green":
        return None
    tests, bare = failing_names(e)
    if not tests and not bare:  # nothing named to rerun: the whole gate at the merge settles it, as before
        return None
    named = ", ".join((tests + bare)[:6])
    return (f"the demo server's run {rid} was red for {slice_id} at {tip[:10]} ({named}): it is not given the merge "
            f"slot until those are rerun on the Mac: merge_slice.py server-rerun {slice_id}. Green there, it queues as "
            "before; red there, it goes back to its builder.")
