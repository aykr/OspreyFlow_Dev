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


def counting(switch: str = SWITCH) -> bool:
    """The owner's switch: the exact word `on` in a regular file of his; anything else is off."""
    f = c.DATA / switch
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


def own_run(result: dict) -> dict:
    """The runner's own shape (the owner's file 011, 23 November 2026; run 97dc976c7be6d175): a slice's whole result at
    the top level, its place in a stack as `position` of `of` within `group` (the stack's run ids, in order), and
    `stack` the members as bare {slice, tip}, a slice run alone included. Stacked above others, the tree main must be
    is the tree of the run below it, fetched by its own id and checked to be that member; anything missing or not
    matching leaves base_tree None, and nothing counts."""
    stack = [x for x in result.get("stack") or [] if isinstance(x, dict)]
    pos, group = result.get("position"), result.get("group")
    i = pos - 1 if isinstance(pos, int) and pos >= 1 else 0
    if stack and (i >= len(stack) or (stack[i].get("slice"), stack[i].get("tip")) != (result["slice"], result["tip"])):
        i = None  # the stack does not place this run where its position says
    base_tree = None
    if i and isinstance(group, list) and len(group) > i and isinstance(group[i - 1], str):
        below = fetch(group[i - 1])
        if below and below.get("state") == "done" and (below.get("slice"), below.get("tip")) == \
                (stack[i - 1].get("slice"), stack[i - 1].get("tip")):
            base_tree = below.get("tree")
    k = i or 0
    return {**result, "index": i if i is not None else -1, "main": result.get("main") if i == 0 else None,
            "base_tree": base_tree,
            "below": [x.get("slice") for x in stack[:k]],
            "above": [(x.get("slice"), x.get("tip")) for x in stack[k + 1:]] if i is not None else []}


def element(result: dict | None, slice_id: str, tip: str) -> dict | None:
    """This slice's part of a result: the result itself for a single slice, or its element of a stack; None when the
    result is not for this slice at this tip."""
    if not isinstance(result, dict):
        return None
    if result.get("slice") == slice_id and result.get("tip") == tip and \
            any(k in result for k in ("tree", "position", "group")):  # the runner's own shape, a run with no tree too
        return own_run(result)
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


#: The early warning's log of each run it started or polled (early_warning.RUNS): where to ask, never the answer.
EW_RUNS = c.DATA / "early-warning" / "runs.jsonl"
#: How many older runs of the same slice and tip are asked about when the newest ended without a verdict.
OLDER_RUNS = 4
VERDICTS = ("pass", "fail")


def has_verdict(e: dict | None) -> bool:
    return bool(e) and e.get("state") == "done" and e.get("verdict") in VERDICTS


def older_runs(slice_id: str, tip: str, newest: str | None) -> list[str]:
    """The ids of the slice's earlier runs at this tip, newest first (EW_RUNS), the note's own left out. Only a shortcut:
    element() is what refuses a run of another slice or tip."""
    try:
        lines = EW_RUNS.read_text().splitlines()
    except OSError:
        return []
    ids: list[str] = []
    for ln in reversed(lines):
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        rid = r.get("id") if isinstance(r, dict) else None
        if r.get("slice") == slice_id and r.get("tip") == tip and isinstance(rid, str) and RUN_ID.match(rid) \
                and rid != newest and rid not in ids:
            ids.append(rid)
    return ids[:OLDER_RUNS]


def newer_runs(slice_id: str, tip: str, rid: str | None) -> list[str]:
    """The ids of the slice's runs at this tip that EW_RUNS records after `rid`'s own last line, newest first; [] when
    the log does not hold `rid` (nothing is known to be newer). Only a shortcut: element() refuses another slice or tip."""
    try:
        lines = EW_RUNS.read_text().splitlines()
    except OSError:
        return []
    rows = []
    for ln in lines:
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("slice") == slice_id and r.get("tip") == tip \
                and isinstance(r.get("id"), str) and RUN_ID.match(r["id"]):
            rows.append(r["id"])
    if not rid or rid not in rows:
        return []
    after = rows[len(rows) - rows[::-1].index(rid):]
    ids: list[str] = []
    for x in reversed(after):
        if x != rid and x not in ids:
            ids.append(x)
    return ids[:OLDER_RUNS]


def newer_green(slice_id: str, tip: str, rid: str | None) -> tuple[str, dict] | None:
    """RM1a, 26 November 2026: a newer run of this slice at this tip supersedes an older red when the newest of them
    with a verdict passed. A newer red never yields to an older green, and a run with no verdict decides nothing."""
    for newer in newer_runs(slice_id, tip, rid):
        o = element(fetch(newer), slice_id, tip)
        if has_verdict(o):
            return (newer, o) if o.get("verdict") == "pass" else None
    return None


def server_result(slice_id: str, tip: str) -> tuple[str | None, dict | None]:
    """(run id, this slice's element) as fetched; (rid, None) when the note names a run that cannot be fetched or is
    not for this slice at this tip. When the note's run finished with no verdict (an error: SE6c, 23 November 2026,
    run f8394584d97477d3, "nothing was run", sent again after its stack's own run), the newest earlier run of the slice
    at this tip that has one is read instead, and the element says which run had none: an error never hides a verdict,
    and the older run must still be the same candidate as the Mac's (same_candidate). A red the note names is
    superseded by a newer green the log records for the same slice at the same tip (newer_green): that run is read, and
    the element names the red it superseded."""
    rid = run_id(slice_id, tip)
    e = element(fetch(rid), slice_id, tip)
    if is_red(e):  # a newer green of the same slice at the same tip supersedes it (RM1a; newer_green)
        g = newer_green(slice_id, tip, rid)
        return (g[0], {**g[1], "superseded_red": rid}) if g else (rid, e)
    if not e or e.get("state") != "done" or has_verdict(e):
        return rid, e
    for older in older_runs(slice_id, tip, rid):
        o = element(fetch(older), slice_id, tip)
        if has_verdict(o):
            return older, {**o, "newer_without_verdict": {"id": rid, "verdict": e.get("verdict"), "words": e.get("words")}}
    return rid, e


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
    if done.get("tip") == tip and done.get("result") in ("green", "unplaced"):  # unplaced: the whole gate settles it
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


#: Item 4 (the owner's approval, 23 November 2026): the records folder, and what in it no records commit may change
#: under a server result (the same rule land() lands a merge by): the scan rows and the owner's own files.
RECORDS_REL = f"{c.V062_REL}/"
SCAN_ROWS_REL = f"{c.V062_REL}/scan_rows"
OWNER_FILES = (f"{c.V062_REL}/dial.yaml", f"{c.V062_REL}/accounts.yaml", f"{c.V062_REL}/live_step.yaml",
               f"{c.V062_REL}/resume.tsv", f"{c.V062_REL}/standing.tsv")
#: The targets of today's full gate that read the records folder, which the Mac always runs when a server result stands
#: across records commits (the owner's approved list, items 1 to 3; item 4, live-collect, is run beside make test's
#: files, item 5: every test whose scan_map.tsv row covers the folder, and test_live_select.py besides).
RECORDS_TARGETS = ("slice-line-check", "citation-check", "client-name-check")
RECORDS_TESTS = ("tests/test_live_select.py",)
LINE_MAP_REL = "OspreyFlow_Build/scripts/slice_line/scan_map.tsv"


def git_ok(args: list[str]) -> tuple[bool, str]:
    p = subprocess.run(["git", *args], cwd=c.REPO, capture_output=True, text=True)
    return p.returncode == 0, p.stdout.strip()


def records_moved(e: dict, base: str, tip: str, tree: str) -> tuple[list[str], str | None]:
    """(the files the records commits changed, None) when main has moved since the server's run only by records
    commits (item 4): each a Slice-Records commit with one parent, together changing only records-folder files that are
    not scan rows, the owner's files or a file the slice changed; and the Mac's candidate tree differs from the server's
    (the server's main with the slice merged, made again here and checked against the tree the server gives) in
    exactly those files, each as main has it. Otherwise ([], why)."""
    smain, stree = str(e.get("main") or ""), str(e.get("tree") or "")
    words = f"main has moved since the server's run (it ran on {smain[:10]}, main is {base[:10]})"
    if not smain or not stree or not git_ok(["merge-base", "--is-ancestor", smain, base])[0]:
        return [], f"{words}, and not forward"
    _, commits = git_ok(["rev-list", "--reverse", f"{smain}..{base}"])
    for sha in commits.split():
        _, parents = git_ok(["rev-list", "--parents", "-n", "1", sha])
        _, trailers = git_ok(["log", "-1", "--format=%(trailers:only,unfold)", sha])
        if len(parents.split()) != 2 or "Slice-Records: yes" not in trailers:
            return [], f"{words} by {sha[:10]}, which is not a records commit"
    _, diff = git_ok(["diff", "--name-only", "--no-renames", smain, base])
    paths = sorted(diff.split())
    _, own = git_ok(["diff", "--name-only", "--no-renames", f"{smain}...{tip}"])
    bad = [f for f in paths if not f.startswith(RECORDS_REL) or f.startswith(SCAN_ROWS_REL + "/") or f in OWNER_FILES
           or f in own.split()]
    if bad:
        return [], f"{words}, in a path the server's run tested or the merge reads ({', '.join(bad[:5])})"
    ok, made = git_ok(["merge-tree", "--write-tree", "--no-messages", smain, tip])
    if not ok or made.split("\n", 1)[0] != stree:
        return [], f"{words}, and the server's candidate tree {stree[:10]} cannot be made again here"
    _, differ = git_ok(["diff", "--name-only", "--no-renames", stree, tree])
    same = all(git_ok(["rev-parse", f"{tree}:{f}"]) == git_ok(["rev-parse", f"{base}:{f}"]) for f in paths)
    if sorted(differ.split()) != paths or not same:
        return [], (f"{words}, and the Mac's candidate tree differs from the server's in more than the records "
                    f"commits' files ({', '.join(sorted(differ.split())[:5])})")
    return paths, None


def records_tests(tree: Path) -> list[str]:
    """The test files (relative to OspreyFlow_Build) of item 5: every scan_map.tsv row of the candidate tree whose
    prefixes cover the records folder, and RECORDS_TESTS."""
    import scan_select
    try:
        table = scan_select.load((tree / LINE_MAP_REL).read_text())
    except (OSError, ValueError):
        table = scan_select.entries()
    rows = {t for t, prefixes, _ in table if any(RECORDS_REL.startswith(p) or p.startswith(RECORDS_REL)
                                                 for p in prefixes)}
    return sorted(rows | set(RECORDS_TESTS))


def same_candidate(e: dict | None, base: str, tip: str, tree: str) -> str | None:
    """Why the server's run is not for the Mac's own candidate (None when it is): the same main tip (for a slice stacked
    on others, main exactly the tree the server ran it on), the same slice tip and the same candidate tree hash; or main
    moved since only by records commits, the trees differing in exactly their files (item 4, records_moved)."""
    if not e:
        return "no result from the server for this slice at this tip"
    if e.get("state") == "done" and e.get("verdict") not in VERDICTS:  # an error: nothing was run, no candidate
        return (f"the server's run {e.get('id')} ended without a verdict ({e.get('verdict')}: "
                f"{str(e.get('words') or 'no words')[:160]})")
    if e.get("index"):  # stacked: main must be exactly the tree the server ran it on (those below landed as tested)
        if c.git(["rev-parse", base + "^{tree}"], c.REPO) != e.get("base_tree"):
            return (f"stacked on {', '.join(e.get('below') or [])}: main is not the tree the server ran it on (one "
                    "below has not landed as tested); it goes to the server again")
    elif e.get("main") != base:
        if e.get("tip") != tip:
            return "the server's run is for another tip of the slice"
        return records_moved(e, base, tip, tree)[1]
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


def remainder(e: dict, tree: Path, mk: Path, records: list[str] | tuple = ()) -> dict:
    """What the Mac still runs of today's full gate when the server's green counts, and what is taken from the server:
    each `ci` prerequisite the server does not name as run and passed (core-check by Core's own `check` targets, each
    named), and `make test` whole unless the server names it passed, then only the test files it did not run (written
    as a second makefile, `mk`, for make test's own pytest command). Anything the server names but the Mac cannot place
    runs on the Mac whole: never weaker than today on a path the server did not prove."""
    passed = {t for t in e.get("passed_targets") or [] if isinstance(t, str)}
    if records:  # item 4: main moved by records commits since the server's run; what reads them runs on the Mac
        passed -= set(RECORDS_TARGETS)
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
        if records:
            files = sorted(set(files) | {f"../OspreyFlow_Build/{t}" for t in records_tests(tree)})
            targets.append(["make", "live-collect"])
            mac.append("live-collect (the records folder moved)")
        if files:
            mk.write_text("server-test-files:\n\t$(IN_CORE) $(PYTEST) $(SERVER_TEST_FILES)\n")
            targets.append(["make", "-f", "Makefile", "-f", str(mk), "server-test-files",
                            "SERVER_TEST_FILES=" + " ".join(files)])
            mac.append("test files the server did not run: " + ", ".join(f[len("../"):] for f in files))
    else:
        targets.append(["make", "test"])
        mac.append("test")
    return {"targets": targets, "taken": taken, "mac": mac, "records": list(records)}


# ------------------------------------------------------------------ 017, item 1: the build account's container checks

#: The owner's own switch for them, apart from server_counts (off as built), and his file naming the backup repository
#: (one line: its URL or path). The Mac reads the build account's results only from that repository, fetched into a
#: cache of the line's own (never the main checkout, never over SSH into the build account: the owner, 24 November).
BUILD_SWITCH = "build_counts"
BUILD_BACKUP = "build_backup"
BUILD_CACHE = "build-backup.git"
BUILD_BRANCH = "build-results"
BUILD_RUNNER = "bc-1"
#: The only targets a build-account result may stand for (build_server/runner.py's TARGETS): a name outside them in
#: its passed_targets is never taken, whatever the result says.
BUILD_TARGETS = ("opentofu-check", "chart-check", "cp-policy-check", "trivy", "trivy-image-ingest", "trivy-image-api",
                 "trivy-image-workspace", "trivy-image-harness", "trivy-image-ner", "trivy-image-worker",
                 "trivy-image-report-sync", "trivy-image-superset", "trivy-image-laurium", "harness-a11y")


def build_backup() -> str | None:
    """The backup repository the owner's file names; None when it is absent, a link, or not one line."""
    f = c.DATA / BUILD_BACKUP
    try:
        if f.is_symlink() or not f.is_file():
            return None
        lines = [x.strip() for x in f.read_text().splitlines() if x.strip()]
    except OSError:
        return None
    return lines[0] if len(lines) == 1 and not lines[0].startswith("-") else None


def build_git(args: list[str], timeout: int = FETCH_SECONDS) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(["git", "--git-dir", str(c.DATA / BUILD_CACHE), *args], capture_output=True, text=True,
                              timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None


def build_result(slice_id: str, tip: str) -> tuple[dict | None, str | None]:
    """(the build account's result for this slice at this tip, why not) as the backup repository holds it now:
    fetched into the cache, read from refs/heads/build-results, and checked to be the runner's own shape for exactly
    this slice and tip."""
    url = build_backup()
    if not url:
        return None, f"no backup repository named (the owner's file {BUILD_BACKUP})"
    cache = c.DATA / BUILD_CACHE
    if not cache.is_dir():
        p = subprocess.run(["git", "init", "-q", "--bare", str(cache)], capture_output=True, text=True)
        if p.returncode != 0:
            return None, "the backup's cache could not be made"
    p = build_git(["fetch", "-q", "--no-tags", "--", url, f"+refs/heads/{BUILD_BRANCH}:refs/heads/{BUILD_BRANCH}"])
    if not p or p.returncode != 0:
        return None, "the backup repository could not be fetched"
    p = build_git(["show", f"refs/heads/{BUILD_BRANCH}:results/{slice_id}/{tip}.json"], 30)
    if not p or p.returncode != 0:
        return None, "the build account has no result for this slice at this tip"
    try:
        b = json.loads(p.stdout)
    except ValueError:
        return None, "the build account's result is not JSON"
    if not isinstance(b, dict) or b.get("runner") != BUILD_RUNNER or not RUN_ID.match(str(b.get("id"))) or \
            (b.get("slice"), b.get("tip")) != (slice_id, tip):
        return None, "the build account's result is not its runner's own for this slice at this tip"
    return b, None


def build_part(slice_id: str, tip: str, base: str, tree: str) -> dict:
    """What the build account's container checks take from the Mac at this merge: counted only with the owner's switch
    on, for the same candidate as the Mac's own (the same main tip, or main moved by records commits only; the same
    slice tip; the same candidate tree), a finished pass, and then only BUILD_TARGETS it names as run and passed."""
    if not counting(BUILD_SWITCH):
        return {"counted": False, "why": f"the owner's switch ({BUILD_SWITCH}) is off"}
    b, why = build_result(slice_id, tip)
    rid = (b or {}).get("id")
    if not why:
        why = same_candidate(b, base, tip, tree)
    if not why and (b.get("state") != "done" or b.get("verdict") != "pass"):
        why = f"the build account's run is not a finished pass ({b.get('state')}, {b.get('verdict')})"
    taken = [t for t in (b or {}).get("passed_targets") or [] if t in BUILD_TARGETS] if not why else []
    if not why and not taken:
        why = "the build account's result names no container check it ran and passed"
    out = {"counted": not why, "run_id": rid, "taken": taken}
    return {**out, "why": why} if why else out


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
