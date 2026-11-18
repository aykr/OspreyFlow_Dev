#!/usr/bin/env python3
"""The slice line's guard: every refusing hook (process/lanes/v062/slice-line/README.md, "Gates").

It runs only from the fixed place outside every worktree (~/.ospreyflow/slice-line/bin/guard.py, put
there by install.sh), so a builder's own copy of this file is never the one that runs. Standard library
only, and Python 3.9 compatible: the hook runs it with /usr/bin/python3.

    guard.py pre            PreToolUse, every tool: refuses with exit 2 and the reason on stderr
    guard.py session-start  SessionStart: a seat's proof that the guard is loaded (run_seat.py waits for it)
    guard.py stop           Stop and SubagentStop: a credential or the owner's address in the final message

A refusal is never a reminder: the tool call does not run, and the agent is told why.
A guard that fails internally refuses (fails closed) rather than letting the call through.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional

BIN = Path.home() / ".ospreyflow" / "slice-line"
# The data folder (records, session markers, the owner's address hashes). The launcher may point a dry
# run at a scratch folder; an agent cannot change the environment its own hooks inherit.
DATA = Path(os.environ.get("OSPREY_SLICE_HOME") or str(BIN))

# Paths are repository-relative (from the root of whichever checkout the path is in).
PROTECTED = ("OspreyFlow_Core/Makefile", ".github/workflows/ci.yml")
OWNER_ONLY = ("OspreyFlow_Build/process/lanes/v062/dial.yaml", "OspreyFlow_Build/process/lanes/v062/accounts.yaml",
              "OspreyFlow_Build/process/lanes/v062/live_step.yaml", "OspreyFlow_Build/process/lanes/v062/resume.tsv")
LINE_PREFIXES = (".claude/", "OspreyFlow_Build/scripts/slice_line/")
NEVER_STAGED = ("OspreyFlow_Core/osprey.yaml", "OspreyFlow_Core/data/")
RECORDS_ROOT = "OspreyFlow_Build/process/lanes/v062/"
DASHBOARD = "ospreyflow_build_plan_2026-11-17/dashboard"

TEMP_ROOTS = ("/tmp/", "/private/tmp/", "/private/var/folders/", "/var/folders/")

SECRET_PATTERNS = (
    (r"sk-ant-[A-Za-z0-9_\-]{20,}", "an Anthropic key"),
    (r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b", "an AWS access key"),
    (r"\bgh[pousr]_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{40,}", "a GitHub token"),
    (r"\bAIza[0-9A-Za-z_\-]{35}\b", "a Google (Gemini) key"),
    (r"\bxox[abposr]-[A-Za-z0-9\-]{10,}", "a Slack token"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "a private key"),
    (r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}", "a signed token (JWT)"),
    (r"\b[ps]k1_[0-9a-f]{40,}\b", "a Porkbun key"),
    (r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{32,}", "an API secret key"),
)
GENERIC_SECRET = re.compile(
    r"(?i)\b(api[_-]?key|secret|password|passwd|access[_-]?token|auth[_-]?token|client[_-]?secret)\b"
    r"[\"']?\s*[:=]\s*[\"']?([A-Za-z0-9+/=_\-]{24,})"
)
EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

DEMO_PATTERNS = (
    (r"govuk\.ospreyflow\.app", "the GOV.UK demo"),
    (r"/opt/ospreyflow", "the GOV.UK demo's install"),
    (r"\bosprey-small\b", "the GOV.UK demo's containers"),
    (r"ospreyflow-v0\.6\.", "the GOV.UK demo's install"),
    (r"(?i)airbyte|\babctl\b", "airbyte"),
    (r":8000(?!\d)|\bport[= ]8000(?!\d)|-p\s*8000(?!\d)", "port 8000 (airbyte)"),
)
SERVER = re.compile(r"\bssh\b[^|;&]*\bospreyflow-test\b|DOCKER_HOST=\S*ospreyflow-test")
SERVER_CHANGE = re.compile(
    r"\bdocker\s+(compose|stop|start|restart|rm|kill|rmi|tag|build|system|volume|image|network|container|"
    r"pull|run|update)\b|\bospreyflow\s+\w|\bsystemctl\b|\breboot\b|\bcaddy\b"
)

WRITE_MARKERS = re.compile(
    r">|\btee\b|\bsed\s+(?:-[a-zA-Z]*i|--in-place)|\bperl\s+-[a-zA-Z]*i|\b(?:cp|mv|rm|ln|touch|truncate|dd|"
    r"install|rsync|chmod|chown|unlink|patch)\b|\bgit\s+(?:checkout|restore|apply|am|mv|rm|stash)\b|"
    r"open\(|write_text|write_bytes|\.write\(|\bunzip\b|\btar\b"
)
GIT_WRITE = {"commit", "merge", "rebase", "reset", "cherry-pick", "revert", "am", "pull", "update-ref"}
SEAT_LAUNCH = re.compile(r"(?:^|[\s;&|(`])(?:claude|claude-sol|claude-ayan)(?:\s|$)|CLAUDE_CONFIG_DIR=|disableAllHooks|"
                         r"--setting-sources|\.local/bin/claude\b")
ALLOWED_SCRIPT = re.compile(
    r"^\s*(?:[\w./~\-]*python[\d.]*\s+)?[\w./~\-]*OspreyFlow_Build/scripts/slice_line/"
    r"(merge_slice|run_seat|slice_start|board|resume)\.py(?:\s+[^;&|`$()<>\n]*)?\s*$"
)
OWNER_SCRIPTS = re.compile(r"\b(refreeze\.py|install\.sh|push_main\.sh)\b")


class Refuse(Exception):
    pass


# ---------------------------------------------------------------- helpers


def _git(args: List[str], cwd: str) -> Optional[str]:
    try:
        out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=10)
    except Exception:
        return None
    return out.stdout.rstrip() if out.returncode == 0 else None


def repo_root(path: str) -> Optional[Path]:
    p = Path(path)
    for q in [p, *p.parents]:
        if (q / ".git").exists():
            return q
    return None


def rel_in_repo(path: str) -> Optional[str]:
    root = repo_root(path)
    if root is None:
        return None
    try:
        return str(Path(path).resolve().relative_to(root.resolve()))
    except ValueError:
        return None


def main_checkout(cwd: str) -> Optional[Path]:
    common = _git(["rev-parse", "--path-format=absolute", "--git-common-dir"], cwd)
    return Path(common).parent if common else None


def emails() -> set:
    try:
        return {ln.strip() for ln in (DATA / "emails.sha256").read_text().splitlines() if ln.strip()}
    except OSError:
        return set()


def scan_secrets(text: str) -> Optional[str]:
    for pat, what in SECRET_PATTERNS:
        if re.search(pat, text):
            return what
    for m in GENERIC_SECRET.finditer(text):
        value = m.group(2)
        if re.search(r"[A-Za-z]", value) and re.search(r"\d", value):
            return "a " + m.group(1).lower() + " value"
    blocked = emails()
    if blocked:
        for m in EMAIL.finditer(text):
            if hashlib.sha256(m.group(0).lower().encode()).hexdigest() in blocked:
                return "the owner's email address"
    return None


def strip_harmless(cmd: str) -> str:
    cmd = re.sub(r"\d?>&\d", " ", cmd)
    cmd = re.sub(r"\d?>>?\s*/dev/null", " ", cmd)
    return cmd


def is_temp(path: str) -> bool:
    """A scratch path: under a temporary root and inside no git checkout (a checkout in /tmp is still a checkout)."""
    p = str(Path(path).resolve()) + "/"
    tmp = os.environ.get("TMPDIR", "")
    in_tmp = p.startswith(TEMP_ROOTS) or bool(tmp and p.startswith(str(Path(tmp).resolve())))
    return in_tmp and repo_root(path) is None


def under(path: str, root: str) -> bool:
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def tokens(cmd: str) -> List[str]:
    try:
        return shlex.split(cmd, comments=False, posix=True)
    except ValueError:
        return cmd.split()


def segments(cmd: str) -> List[List[str]]:
    """The command split at ; && || | and newlines, each part tokenised."""
    parts = re.split(r"&&|\|\||[;|\n]", cmd)
    return [tokens(p) for p in parts if p.strip()]


def git_calls(cmd: str, cwd: str) -> Iterable[tuple]:
    """Each git invocation as (directory it acts on, subcommand, its arguments). `cd X` carries forward."""
    here = cwd
    for seg in segments(cmd):
        toks = [t for t in seg if not re.match(r"^[A-Z_][A-Z0-9_]*=", t)]
        if not toks:
            continue
        if toks[0] == "cd" and len(toks) > 1:
            here = str((Path(here) / os.path.expanduser(toks[1])).resolve())
            continue
        if toks[0] != "git" and not toks[0].endswith("/git"):
            continue
        d, i = here, 1
        while i < len(toks) and toks[i].startswith("-"):
            if toks[i] == "-C" and i + 1 < len(toks):
                d = str((Path(d) / os.path.expanduser(toks[i + 1])).resolve())
                i += 2
                continue
            if toks[i] in ("-c",) and i + 1 < len(toks):
                i += 2
                continue
            i += 1
        if i < len(toks):
            yield d, toks[i], toks[i + 1:]


def names_path(cmd: str, cwd: str, relpath: str) -> bool:
    """Whether the command names this repository-relative file, spelt out or relative to where it runs."""
    if relpath in cmd:
        return True
    base = relpath.split("/")[-1]
    for tok in re.split(r"[\s'\"=(),;|&<>]+", cmd):
        if tok.endswith(base) and (tok == base or tok.endswith("/" + base)):
            full = (Path(cwd) / os.path.expanduser(tok)).resolve()
            if rel_in_repo(str(full)) == relpath:
                return True
    return False


def current_branch(d: str) -> Optional[str]:
    return _git(["rev-parse", "--abbrev-ref", "HEAD"], d)


# ---------------------------------------------------------------- rules


def check_path_edit(path: str, seat: str, cwd: str) -> None:
    full = str((Path(cwd) / os.path.expanduser(path)).resolve())
    if under(full, str(BIN)) or under(full, str(DATA)):
        raise Refuse("the slice line's records and its installed guard are written only by its scripts.")
    if DASHBOARD in full:
        raise Refuse("the progress dashboard's files are written only by board.py.")
    rel = rel_in_repo(full)
    if rel:
        if rel in PROTECTED:
            raise Refuse(rel + " is the owner's: changes to it go to the owner as a diff.")
        if rel in OWNER_ONLY:
            raise Refuse(rel + " is the owner's file: only the owner edits it.")
        if rel.startswith(LINE_PREFIXES):
            raise Refuse(rel + " is part of the slice line itself: it changes only by the owner's hand.")
    if seat in ("verifier", "scout"):
        raise Refuse("the " + seat + " seat is read-only: it never edits a file.")
    if seat == "builder":
        wt = os.environ.get("OSPREY_SLICE_WORKTREE", "")
        if not wt or not (under(full, wt) or is_temp(full)):
            raise Refuse("a builder edits only inside its own worktree (" + (wt or "none set") + "): " + full)
    if seat == "conductor":
        main = main_checkout(cwd)
        ok = main is not None and under(full, str(main / RECORDS_ROOT))
        if not (ok or is_temp(full)):
            raise Refuse("the conductor writes no product code: it edits only " + RECORDS_ROOT + " (its records).")


def check_bash(cmd: str, seat: str, cwd: str) -> None:
    raw = cmd
    cmd = strip_harmless(cmd)
    if re.search(r"\bOSPREY_(SLICE\w*|SEAT\w*|STATUS_FILE|PUSH\w*|CLAUDE_BIN|ACCOUNT)\b", cmd):
        raise Refuse("the slice line's settings (OSPREY_SLICE_*, OSPREY_SEAT*, OSPREY_STATUS_FILE) are never set "
                     "from a command: records, seats and the status file are fixed by the launcher.")
    if seat in ("builder", "verifier", "scout") and "scripts/slice_line/" in cmd:
        raise Refuse("the line's scripts are run by the conductor, never by a builder, verifier or scout.")
    if ALLOWED_SCRIPT.match(raw) and seat in ("", "conductor"):
        return  # the line's own scripts, run whole (nothing chained), by the conductor or the owner's session
    if OWNER_SCRIPTS.search(cmd):
        raise Refuse("refreeze.py, install.sh and push_main.sh are run by the owner (or, for the push, by the "
                     "merge script after a merge), never by an agent.")
    if re.search(r"\bgit\b[^;&|\n]*\bpush\b", cmd) or re.search(r"\bgh\s+repo\s+sync\b", cmd):
        raise Refuse("agents never push. main reaches origin only through the merge script's push step.")
    if re.search(r"\bgit\b[^;&|\n]*\bremote\s+(add|set-url|rename|remove|rm|set-head|set-branches)\b", cmd):
        raise Refuse("no new or changed remote: the only remote written to is origin, by the push script.")
    if re.search(r"\bgh\s+repo\s+(create|edit|fork|rename|delete|archive|unarchive)\b", cmd) or re.search(
        r"\bgh\s+api\b.*(?:-X|--method)\s*(POST|PATCH|PUT|DELETE)", cmd
    ):
        raise Refuse("no new repository and no change of a repository's visibility or settings.")
    for pat, what in DEMO_PATTERNS:
        if re.search(pat, cmd):
            raise Refuse("no command touches " + what + " (the owner's standing rule for this line).")
    if SERVER.search(cmd) and SERVER_CHANGE.search(cmd):
        raise Refuse("nothing is changed on the test server by hand: test stacks go through stack_lease.sh.")
    if SEAT_LAUNCH.search(cmd):
        raise Refuse("a Claude Code session is started only by run_seat.py, with the guard loaded.")
    if "slice-line" in cmd and ".ospreyflow" in cmd and WRITE_MARKERS.search(cmd):
        raise Refuse("the slice line's records and guard are written only by its own scripts.")
    if (DASHBOARD in cmd or "status.js" in cmd) and WRITE_MARKERS.search(cmd):
        raise Refuse("status.js is written only by board.py.")
    if WRITE_MARKERS.search(cmd):
        for p in PROTECTED + OWNER_ONLY:
            if names_path(cmd, cwd, p):
                raise Refuse(p + " is the owner's: an agent never writes it (changes go to the owner as a diff).")
    for prefix in LINE_PREFIXES:
        if prefix in cmd and WRITE_MARKERS.search(cmd):
            raise Refuse(prefix + " is part of the slice line itself: it changes only by the owner's hand.")
    check_git(cmd, seat, cwd)
    if seat == "builder":
        check_builder_bash(cmd, cwd)
    if seat in ("verifier", "scout"):
        check_readonly_bash(raw)
    if seat == "conductor" and WRITE_MARKERS.search(cmd):
        if re.search(r"OspreyFlow_(Core|Build)/(?!process/lanes/v062/)", cmd) or re.search(r"\b(apps|services|packages|tests)/", cmd):
            raise Refuse("the conductor writes no product code: its shell writes stay in " + RECORDS_ROOT + ".")


def check_git(cmd: str, seat: str, cwd: str) -> None:
    for d, sub, args in git_calls(cmd, cwd):
        joined = " ".join(args)
        if sub in ("add", "stage") or (sub == "commit" and re.search(r"(^|\s)(-a|--all|-[a-zA-Z]*a[a-zA-Z]*)(\s|$)", joined)):
            changed = _git(["status", "--porcelain", "--untracked-files=all"], d) or ""
            paths = [ln[3:].strip().strip('"') for ln in changed.splitlines()]
            risky = [p for p in paths if p.startswith(NEVER_STAGED) or p in NEVER_STAGED]
            root = _git(["rev-parse", "--show-toplevel"], d) or d
            prefix = rel_in_repo(d) or ""
            prefix = "" if prefix == "." else prefix
            if any(a for a in args if any(s in str(Path(prefix, a)) for s in ("osprey.yaml", "OspreyFlow_Core/data"))):
                raise Refuse("OspreyFlow_Core/osprey.yaml and OspreyFlow_Core/data/ are never staged.")
            wide = (sub == "commit") or any(a in (".", "-A", "--all", ":/", "-u", "--update", "*") for a in args) or not args
            if wide and risky:
                raise Refuse("this would stage " + ", ".join(risky) + " (in " + root + "): osprey.yaml and data/ "
                             "are never staged. Name the files to add.")
        writes_main = False
        if sub in GIT_WRITE:
            writes_main = current_branch(d) == "main" or (sub == "update-ref" and "refs/heads/main" in joined)
        if sub == "branch" and re.search(r"(^|\s)(-f|--force|-M|-m|-D|-d|-C|-c)\b", joined) and re.search(r"(^|\s)main(\s|$)", joined):
            writes_main = True
        if sub in ("checkout", "switch") and re.search(r"(-B|-C|--force-create)\s+main\b", joined):
            writes_main = True
        if sub == "fetch" and re.search(r":(refs/heads/)?main\b", joined):
            writes_main = True
        if writes_main:
            raise Refuse("nothing writes to main but the merge script (merge_slice.py merge or records).")
        if seat == "builder":
            if sub in ("switch", "worktree") or (sub == "checkout" and "--" not in args):
                raise Refuse("a builder stays on its own slice branch in its own worktree.")
            if sub == "branch" and re.search(r"(^|\s)(-D|-d|-m|-M|-f|--force|-C|-c)\b", joined):
                raise Refuse("a builder does not change branches: it works on its own slice branch only.")


def check_builder_bash(cmd: str, cwd: str) -> None:
    wt = os.environ.get("OSPREY_SLICE_WORKTREE", "")
    if not wt:
        raise Refuse("this builder has no worktree set: start it with run_seat.py.")
    if re.search(r"--git-dir|--work-tree|\bGIT_DIR=|\bGIT_WORK_TREE=", cmd):
        raise Refuse("a builder never points git outside its own worktree.")
    for seg in segments(cmd):
        if seg and seg[0] in ("cd", "pushd") and len(seg) > 1:
            target = str((Path(cwd) / os.path.expanduser(seg[1])).resolve())
            if not (under(target, wt) or is_temp(target)):
                raise Refuse("a builder stays inside its own worktree (" + wt + "); not " + target + ".")
        for i, t in enumerate(seg):
            if t == "-C" and i + 1 < len(seg):
                target = str((Path(cwd) / os.path.expanduser(seg[i + 1])).resolve())
                if not under(target, wt):
                    raise Refuse("a builder runs git only in its own worktree (" + wt + ").")
    if WRITE_MARKERS.search(cmd):
        for m in re.finditer(r"(?:^|[\s='\"(])((?:~|/)[^\s'\";|&)]+)", cmd):
            p = os.path.expanduser(m.group(1))
            if p.startswith("/dev/") or (os.path.isfile(p) and os.access(p, os.X_OK)):
                continue  # a device, or a program being run (a venv's python), is not a write target
            if not (under(p, wt) or is_temp(p)):
                if repo_root(p) is not None or p.startswith(str(Path.home())):
                    raise Refuse("a builder writes only inside its own worktree (" + wt + "); this names " + p + ".")


def check_readonly_bash(raw: str) -> None:
    if not re.match(r"^\s*git\s+(diff|log|show|status|blame|rev-parse|ls-files|grep|cat-file)\b[^;&|<>`$()]*$", raw):
        raise Refuse("this seat is read-only: its shell runs only git diff, log, show, status, blame, rev-parse, "
                     "ls-files, grep or cat-file, one at a time.")


def pre(event: dict) -> None:
    tool = event.get("tool_name", "")
    ti = event.get("tool_input") or {}
    cwd = event.get("cwd") or os.getcwd()
    seat = os.environ.get("OSPREY_SEAT", "")
    if tool not in ("Read", "Glob", "Grep"):
        what = scan_secrets(json.dumps(ti, ensure_ascii=False))
        if what:
            raise Refuse(what + " is never written to a file or a message. Leave it out, or name where the "
                         "owner keeps it instead.")
    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        check_path_edit(ti.get("file_path") or ti.get("notebook_path") or "", seat, cwd)
    elif tool in ("Bash", "Monitor", "PowerShell"):
        check_bash(ti.get("command") or "", seat, cwd)
    elif tool == "WebFetch" or tool.startswith("mcp__"):
        blob = json.dumps(ti)
        for pat, what in DEMO_PATTERNS:
            if re.search(pat, blob):
                raise Refuse("no request touches " + what + ".")
    elif tool in ("EnterWorktree", "ExitWorktree") and seat == "builder":
        raise Refuse("a builder stays in the worktree it was started in.")


def session_start(event: dict) -> None:
    token = os.environ.get("OSPREY_SEAT_TOKEN")
    if not token:
        return
    sid = event.get("session_id", "unknown")
    me = Path(__file__).resolve()
    digest = hashlib.sha256(me.read_bytes()).hexdigest()
    d = DATA / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    (d / (sid + ".guard")).write_text(json.dumps({"token": token, "guard": str(me), "sha256": digest,
                                                  "seat": os.environ.get("OSPREY_SEAT", "")}))


def stop(event: dict) -> None:
    what = scan_secrets(event.get("last_assistant_message") or "")
    if what:
        print(json.dumps({"decision": "block", "reason": "Your last message contains " + what +
                          ". Send a corrected message without it."}))


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "pre"
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        event = {}
    try:
        if mode == "pre":
            pre(event)
        elif mode == "session-start":
            session_start(event)
        elif mode == "stop":
            stop(event)
    except Refuse as r:
        print("Slice line guard refused this: " + str(r), file=sys.stderr)
        return 2
    except Exception as e:  # fail closed
        if mode == "pre":
            print("Slice line guard refused this: the guard failed (" + type(e).__name__ + ": " + str(e) + ").",
                  file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
