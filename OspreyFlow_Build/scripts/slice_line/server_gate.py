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
FETCH_SECONDS = 120


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
    if isinstance(result.get("stack"), list):  # item 3: main+A, main+A+B, ... run at once, in this order
        stack = [e for e in result["stack"] if isinstance(e, dict)]
        for i, e in enumerate(stack):
            if e.get("slice") == slice_id and e.get("tip") == tip:
                return {**e, "id": result.get("id"), "state": result.get("state"), "index": i,
                        "main": result.get("main") if i == 0 else None,
                        "base_tree": stack[i - 1].get("tree") if i else None,
                        "below": [x.get("slice") for x in stack[:i]],
                        "above": [(x.get("slice"), x.get("tip")) for x in stack[i + 1:]]}
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


# ------------------------------------------------------------------ item 2: the server's green counts


def prerequisites(makefile: Path, target: str) -> list[str]:
    """The prerequisites of `target:` in a Makefile, as written on its rule line (continuations joined); [] if none."""
    try:
        text = makefile.read_text().replace("\\\n", " ")
    except OSError:
        return []
    m = re.search(rf"^{re.escape(target)}:([^=\n]*)$", text, re.M)
    return m.group(1).split() if m else []


#: A test file the server may name as not run, as make test's own pytest is given one (from OspreyFlow_Core).
TEST_FILE = re.compile(r"\A(?:\.\./)?(OspreyFlow_Build/tests/[A-Za-z0-9_./-]+\.py)\Z")


def same_candidate(e: dict | None, base: str, tip: str, tree: str) -> str | None:
    """Why the server's run is not for the Mac's own candidate (None when it is): the same main tip (for a slice stacked
    on others, main exactly the tree the server ran it on), the same slice tip and the same candidate tree hash."""
    if not e:
        return "no result from the server for this slice at this tip"
    if e.get("index"):  # stacked: main must be exactly the tree the server ran it on (those below landed as tested)
        if c.git(["rev-parse", base + "^{tree}"], c.REPO) != e.get("base_tree"):
            return (f"stacked on {', '.join(e.get('below') or [])}: main is not the tree the server ran it on (one "
                    "below has not landed as tested); it goes to the server again")
    elif e.get("main") != base:
        return f"main has moved since the server's run (it ran on {str(e.get('main'))[:10]}, main is {base[:10]})"
    if e.get("tip") != tip:
        return "the server's run is for another tip of the slice"
    if e.get("tree") != tree:
        return f"the server's candidate tree {str(e.get('tree'))[:10]} is not the Mac's {tree[:10]}"
    return None


def matches(e: dict | None, base: str, tip: str, tree: str) -> str | None:
    """Why the server's green does not stand for this merge (None when it does): the runner's finished pass, for the same
    main tip, the same slice tip and the same candidate tree hash as the Mac's own merge result."""
    why = same_candidate(e, base, tip, tree)
    if why:
        return why
    if e.get("state") != "done" or e.get("verdict") != "pass":
        return f"the server's run is not a finished pass ({e.get('state')}, {e.get('verdict')})"
    if not isinstance(e.get("passed_targets"), list):
        return "the server's result names no target it ran and passed"
    return None


def remainder(e: dict, tree: Path, mk: Path) -> dict:
    """What the Mac still runs of today's full gate when the server's green counts, and what is taken from the server:
    each `ci` prerequisite the server does not name as run and passed (core-check by Core's own `check` targets, each
    named), and `make test` whole unless the server names it passed, then only the test files it did not run (written
    as a second makefile, `mk`, for make test's own pytest command). Anything the server names but the Mac cannot place
    runs on the Mac whole: never weaker than today on a path the server did not prove."""
    passed = {t for t in e.get("passed_targets") or [] if isinstance(t, str)}
    ci = prerequisites(tree / "OspreyFlow_Build/Makefile", "ci")
    core = prerequisites(tree / "OspreyFlow_Core/Makefile", "check")
    targets, taken, mac = [], [], []
    ci_left = [t for t in ci if t != "core-check" and t not in passed]
    taken += [t for t in ci if t != "core-check" and t in passed]
    if "core-check" in ci:
        core_left = [t for t in core if t not in passed] if core else ["check"]
        taken += [f"core:{t}" for t in core if t in passed]
        if core_left:
            targets.append(["make", "-k", "-C", "../OspreyFlow_Core", *core_left])
            mac += [f"core:{t}" for t in core_left]
    if ci_left:
        targets.insert(0, ["make", "-k", *ci_left])
        mac = ci_left + mac
    nr = e.get("not_run") or {}
    names = [x.get("name") if isinstance(x, dict) else x for x in (nr.get("test_files") or [])]
    names += [x for x in (nr.get("docker_skipped") or [])]
    files = [TEST_FILE.match(str(n)) for n in names]
    if "test" in passed and all(files):
        taken.append("test")
        files = sorted({"../" + m.group(1) for m in files})
        if files:
            mk.write_text("server-test-files:\n\t$(IN_CORE) $(PYTEST) $(SERVER_TEST_FILES)\n")
            targets.append(["make", "-f", "Makefile", "-f", str(mk), "server-test-files",
                            "SERVER_TEST_FILES=" + " ".join(files)])
            mac.append("test files the server did not run: " + ", ".join(f[len("../"):] for f in files))
    else:
        targets.append(["make", "test"])
        mac.append("test")
    return {"targets": targets, "taken": taken, "mac": mac}


# ------------------------------------------------------------------ item 3: the stack


def stack_refused(slice_id: str, tip: str) -> list[str]:
    """A slice refused at merge: every slice the server ran stacked on it is not counted, and is marked to go to the
    server again (records/<ID>/server-again.json, for that run id). The slices so marked."""
    rid, e = server_result(slice_id, tip)
    marked = []
    for sid, stip in (e or {}).get("above") or []:
        if not sid or not (c.DATA / "records" / sid).is_dir():
            continue
        c.write_json(c.rec_dir(sid) / "server-again.json",
                     {"slice": sid, "tip": stip, "run_id": rid, "because": f"{slice_id}, below it in the server's stack, "
                      "was refused at merge", "at": c.now()})
        marked.append(sid)
    return marked


# ------------------------------------------------------------------ item 4: the shadow

SHADOW_LOG = "server-shadow.tsv"
SHADOW_HEAD = "at\tslice\ttip\trun_id\tserver\tmac\tresult\twhy\n"


def shadow(slice_id: str, tip: str, server: dict, code: int, network: bool, failing: list[str]) -> dict:
    """The server's result beside the Mac's whole gate for the same candidate (item 4: on from the first day, whatever
    the switch): agree, differ, or no comparison and why. Written to records/<ID>/server-shadow-<run id>.json and one
    line of server-shadow.tsv in the data folder. Never changes the merge."""
    rid = server.get("run_id")
    srv = {"pass": "green", "fail": "red"}.get(server.get("server_verdict") or "")
    mac = "green" if code == 0 else "red"
    if server.get("counted"):
        result, why = "counted", "the switch is on and the server's green counted: the Mac ran the remainder only"
    elif not rid:
        result, why = "no comparison", "no server result named for this slice at this tip"
    elif not server.get("same"):
        result, why = "no comparison", server.get("same_why") or "not the same candidate"
    elif network:
        result, why = "no comparison", "the Mac's gate could not reach a registry or a download (network)"
    elif srv is None:
        result, why = "no comparison", f"the server's run has no verdict ({server.get('server_verdict')})"
    else:
        result = "agree" if srv == mac else "differ"
        why = "" if result == "agree" else (f"the server said {srv}, the Mac's whole gate {mac}"
                                            + (f" ({', '.join(failing[:5])})" if failing else ""))
    row = {"at": c.now(), "slice": slice_id, "tip": tip, "run_id": rid, "server": srv, "mac": mac,
           "result": result, "why": why, "mac_failing": failing[:20]}
    if rid:
        c.write_json(c.rec_dir(slice_id) / f"server-shadow-{rid}.json", row)
    f = c.DATA / SHADOW_LOG
    try:
        if not f.exists():
            f.write_text(SHADOW_HEAD)
        with f.open("a") as fh:
            fh.write("\t".join(str(row[k] or "") for k in ("at", "slice", "tip", "run_id", "server", "mac", "result",
                                                            "why")) + "\n")
    except OSError:
        pass
    return row


def shadow_tally() -> dict:
    """How many merges the server agreed and differed on (server-shadow.tsv), for the board and the owner's switch."""
    out = {"agree": 0, "differ": 0, "no comparison": 0, "counted": 0}
    try:
        lines = (c.DATA / SHADOW_LOG).read_text().splitlines()[1:]
    except OSError:
        return out
    for ln in lines:
        parts = ln.split("\t")
        if len(parts) >= 7 and parts[6] in out:
            out[parts[6]] += 1
    return out


# ------------------------------------------------------------------ item 6: measure and report

GATE_STEP = "today's full gate"


def report() -> dict:
    """What the server saved, from the records (read only): for merges whose gate counted the server's green, the
    Mac-only remainder's seconds and the whole merge's seconds; the same for merges that ran the whole gate; how many
    refusals the server caught before the slot (a server red, rerun on the Mac and red there too) and how many were an
    environment difference (green on the Mac); and the shadow's tally."""
    counted, whole = [], []
    caught = differences = 0
    for d in sorted((c.DATA / "records").glob("*")) if (c.DATA / "records").is_dir() else []:
        merged = c.read_json(d / "merged.json") or {}
        run = merged.get("gate_run") or ""
        prog = c.read_json(d / f"merge-progress-{run[len('merge-'):-len('.log')]}.json") if run.endswith(".log") else None
        if merged and prog:
            gate = next((x["seconds"] for x in prog.get("done") or [] if x.get("name") == GATE_STEP), None)
            total = sum(x.get("seconds") or 0 for x in prog.get("done") or [])
            row = {"slice": d.name, "merge": merged.get("merge"), "gate_s": gate, "merge_s": total}
            (counted if (merged.get("server") or {}).get("counted") else whole).append(row)
        for f in d.glob("server-rerun-*.json"):
            r = c.read_json(f) or {}
            caught += r.get("result") == "red"
            differences += r.get("result") == "green"

    def mean(rows, k):
        xs = [r[k] for r in rows if isinstance(r.get(k), (int, float))]
        return round(sum(xs) / len(xs)) if xs else None
    return {"counted": {"merges": len(counted), "remainder_s": mean(counted, "gate_s"), "merge_s": mean(counted, "merge_s"),
                        "each": counted},
            "whole": {"merges": len(whole), "gate_s": mean(whole, "gate_s"), "merge_s": mean(whole, "merge_s")},
            "caught_before_the_slot": caught, "environment_differences": differences, "shadow": shadow_tally()}


def report_words(r: dict) -> str:
    def m(s):
        return "none yet" if s is None else f"{s // 60} min {s % 60} s"
    return "\n".join([
        f"merges with the server's green counted: {r['counted']['merges']}; the Mac-only remainder took "
        f"{m(r['counted']['remainder_s'])} on average, the whole merge {m(r['counted']['merge_s'])}",
        f"merges that ran the whole gate: {r['whole']['merges']}; the gate took {m(r['whole']['gate_s'])} on average, "
        f"the whole merge {m(r['whole']['merge_s'])}",
        f"refusals the server caught before the slot (red there, rerun red on the Mac): {r['caught_before_the_slot']}; "
        f"a server red that was green on the Mac (an environment difference): {r['environment_differences']}",
        f"shadow: {r['shadow']['agree']} agree, {r['shadow']['differ']} differ, {r['shadow']['no comparison']} no "
        f"comparison, {r['shadow']['counted']} counted"])
