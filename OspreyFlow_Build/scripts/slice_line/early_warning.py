#!/usr/bin/env python3
"""The demo server as an early warning for a verified slice (DEMO_SERVER_EARLY_WARNING_BRIEF.md). ADVICE ONLY.

    early_warning.py <slice>                  bundle main's tip and the slice's tip, send them to the demo server's
                                              runner, poll until it answers, and write the result as a note
    early_warning.py <slice> --result <id>    poll a run already started (its id is in the note of a run that was
                                              still going at the deadline) and write its note

The Mac's merge run (merge_slice.py merge) is the only gate to main. This script changes nothing in merge_slice.py,
stop_check.py or the guard, and writes no record the merge reads: nothing under ~/.ospreyflow/slice-line/records/.
It writes the note, OspreyFlow_Build/process/lanes/v062/early_warning/<slice>-<tip first 8>.md in the main checkout
(the conductor's records folder), and one file of its own, ~/.ospreyflow/slice-line/early-warning/held.json (which
main the server already holds, so the next bundle need carry only what is new).

How the conductor uses a result. Green changes nothing. On red, rerun the named failing check on the Mac before
sending the slice back, because the server is a different kind of machine: a red from the server alone never costs
a builder a round. ("not run" is never green: it says what the server could not check.)

It refuses a slice that is not at `verified` in its records (state.json's phase, at the branch's own tip), and it
never runs while no setting file exists. The setting lives outside the repository and is the owner's:

    ~/.ospreyflow/slice-line/demo-server.json
    {
      "host": "<the server's address>",         required: the SSH host (letters, digits, . - : only)
      "user": "<the runner's account>",         required: the account whose authorized_keys holds the key
      "key_file": "<path to the private key>",  required: the one key, restricted on the server to the runner
      "port": 22,                               optional
      "known_hosts": "<path>",                  optional: a known_hosts file for the server (host keys are checked:
                                                StrictHostKeyChecking=yes; the owner adds the server's key first)
      "poll_seconds": 60,                       optional: how often it asks
      "max_wait_minutes": 240                   optional: when it stops asking and writes "no result"
    }

Nothing of the setting (host, user, key path) is ever written into the note or printed: an unreachable server is
said as "unreachable (ssh exit N)", never with ssh's own words, which name the host.

Exit codes, none of which lies: 0 green (pass); 1 red (fail, or the slice does not merge onto main); 2 refused here
(not verified, no setting, a bad setting); 3 refused by the runner (busy, a bundle it would not take); 4 no result
(unreachable, still running at the deadline, the job died or the runner failed). Only 0 is green.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "demo_server"))
import common as c  # noqa: E402
import protocol as proto  # noqa: E402

SETTING = c.DATA / "demo-server.json"
OWN = c.DATA / "early-warning"
HELD = OWN / "held.json"
NOTES_REL = f"{c.V062_REL}/early_warning"
SAFE_HOST = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9.:-]*\Z")
SAFE_USER = re.compile(r"\A[a-z_][a-z0-9_-]*\Z")
GREEN, RED, REFUSED_HERE, REFUSED_THERE, NO_RESULT = 0, 1, 2, 3, 4
RED_RULE = ("On red, rerun the named failing check on the Mac before sending the slice back, because the server is a "
            "different kind of machine: a red from the server alone never costs a builder a round. Green changes "
            "nothing.")
ADVICE = "advice only; the Mac's merge run is the gate"


class Refused(Exception):
    pass


def load_setting() -> dict:
    if not SETTING.is_file():
        raise Refused(f"No setting file ({SETTING}): the early warning never runs without one. The owner creates it "
                      "once the runner is installed and the key is in place; its schema is in this script's --help.")
    try:
        s = json.loads(SETTING.read_text())
    except (OSError, ValueError):
        raise Refused(f"The setting file ({SETTING}) is not readable JSON.")
    if not isinstance(s, dict) or not all(isinstance(s.get(k), str) and s.get(k) for k in ("host", "user", "key_file")):
        raise Refused("The setting file needs host, user and key_file (see --help).")
    if not SAFE_HOST.match(s["host"]) or not SAFE_USER.match(s["user"]):
        raise Refused("The setting's host or user has characters an SSH destination does not (see --help).")
    if not Path(s["key_file"]).expanduser().is_file():
        raise Refused("The setting's key_file is not a file.")
    for k, d in (("port", 22), ("poll_seconds", 60), ("max_wait_minutes", 240)):
        v = s.get(k, d)
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            raise Refused(f"The setting's {k} must be a whole number.")
        s[k] = v
    return s


def secrets_of(s: dict) -> list[str]:
    """Every value of the setting that must never reach a note or the terminal."""
    out = [s.get("host", ""), s.get("user", ""), s.get("key_file", ""), str(Path(s.get("key_file", "")).expanduser()),
           s.get("known_hosts", "")]
    return sorted({v for v in out if v and len(v) >= 3}, key=len, reverse=True)


def scrub(text: str, s: dict) -> str:
    for v in secrets_of(s):
        text = text.replace(v, "<setting>")
    return text


def verified_tip(slice_id: str) -> tuple[str, str]:
    """The slice's branch and its tip, when its records have it at `verified` at that tip; refused otherwise."""
    rec = c.rec_dir(slice_id)
    frozen = c.read_json(rec / "frozen.json")
    if not frozen or not frozen.get("branch"):
        raise Refused(f"{slice_id} was never started (no frozen record): nothing to warn about.")
    st = c.state(slice_id)
    branch = frozen["branch"]
    tip = c.git(["rev-parse", "--verify", "-q", f"refs/heads/{branch}"], c.REPO, check=False)
    if st.get("phase") != "verified":
        raise Refused(f"{slice_id} is not at verified in its records (it is at {st.get('phase') or 'nothing'}): the "
                      "early warning runs only for a verified slice.")
    if not tip or st.get("tip") != tip:
        raise Refused(f"{slice_id}'s verified tip is not its branch's tip ({(st.get('tip') or '')[:10]} recorded, "
                      f"{tip[:10] or 'no branch'} now): the early warning runs only for the tip the verifier passed.")
    return branch, tip


def make_bundle(branch: str, dest: Path, full: bool) -> None:
    """A git bundle of main's tip and the slice's tip, from commits only (never a working-tree file); less what the
    server already holds, unless `full`."""
    main = c.git(["rev-parse", "refs/heads/main"], c.REPO)
    held = (c.read_json(HELD) or {}).get("main", "")
    args = ["bundle", "create", "-q", str(dest), "refs/heads/main", f"refs/heads/{branch}"]
    if not full and re.fullmatch(r"[0-9a-f]{40}", held or "") and \
            subprocess.run(["git", "merge-base", "--is-ancestor", held, main], cwd=c.REPO).returncode == 0:
        # git leaves out a ref whose tip is excluded, so when the server holds main itself the bundle stops at main's
        # parents (which it holds too): main's tip is always in the bundle, by name
        args += [f"^{held}"] if held != main else [f"^{x}" for x in c.git(["rev-parse", f"{main}^@"], c.REPO).split()]
    c.git(args, c.REPO)


def ssh(s: dict, words: list[str], stdin=None, timeout: int = 1800) -> tuple[int, dict | None]:
    """One call of the forced command. (ssh's exit, the runner's JSON) — ssh's own words are never kept."""
    cmd = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=yes",
           "-o", "ConnectTimeout=20", "-o", "ServerAliveInterval=30", "-i", str(Path(s["key_file"]).expanduser()),
           "-p", str(s["port"])]
    if s.get("known_hosts"):
        cmd += ["-o", "UserKnownHostsFile=" + str(Path(s["known_hosts"]).expanduser())]
    cmd += ["--", f"{s['user']}@{s['host']}", *words]
    try:
        r = subprocess.run(cmd, stdin=stdin if stdin is not None else subprocess.DEVNULL, capture_output=True,
                           timeout=timeout)
    except subprocess.TimeoutExpired:
        return 255, None
    for ln in reversed(r.stdout.decode(errors="replace").splitlines()):
        try:
            data = json.loads(ln)
            if isinstance(data, dict) and "state" in data:
                return r.returncode, data
        except ValueError:
            continue
    return r.returncode, None


def start(s: dict, branch: str) -> tuple[str, dict | None, int]:
    """Send the bundle; once more in full if the server lacks what an incremental one is built on."""
    with tempfile.TemporaryDirectory(prefix="early-warning-") as d:
        for full in (False, True):
            b = Path(d) / "slice.bundle"
            b.unlink(missing_ok=True)
            make_bundle(branch, b, full)
            with b.open("rb") as fh:
                code, data = ssh(s, ["run"], stdin=fh)
            if data and data.get("state") == "refused" and data.get("reason") == "bundle-prerequisites" and not full:
                continue
            return ("started" if data and data.get("state") == "started" else "failed"), data, code
    return "failed", None, 255


def poll(s: dict, jid: str) -> tuple[dict | None, int]:
    deadline = time.monotonic() + s["max_wait_minutes"] * 60
    misses = 0
    last = None
    while True:
        code, data = ssh(s, ["result", jid], timeout=120)
        if data is None:
            misses += 1
            if misses >= 5:
                return None, code
        else:
            misses, last = 0, data
            if data.get("state") != "running":
                return data, code
        if time.monotonic() + s["poll_seconds"] > deadline:
            return last, code
        time.sleep(s["poll_seconds"])


def outcome(data: dict | None, ssh_code: int) -> tuple[str, int, str]:
    """(the note's headline, the exit code, one line saying why). Only a finished run with verdict pass is green."""
    if data is None:
        return "NO RESULT", NO_RESULT, f"the server could not be reached or gave no answer (ssh exit {ssh_code})"
    st = data.get("state")
    if st == "refused":
        return "REFUSED", REFUSED_THERE, f"the runner refused the run: {data.get('reason', '?')}"
    if st == "running":
        return "NO RESULT", NO_RESULT, f"still running at the deadline ({data.get('seconds', '?')} s so far)"
    if st in ("died", "unknown"):
        return "NO RESULT", NO_RESULT, f"the runner has no result for this run ({st})"
    if st != "done":
        return "NO RESULT", NO_RESULT, "the runner's answer was not one this script knows"
    v = data.get("verdict")
    if v == "pass":
        return "GREEN", GREEN, "every check the server could run passed"
    if v == "fail":
        return "RED", RED, "a check the server ran failed"
    if v == "conflict":
        return "RED", RED, "the slice does not merge cleanly onto main"
    return "NO RESULT", NO_RESULT, f"the run ended without a verdict on the slice ({v}): {data.get('words', '')}"


def spatial_line(s) -> str:
    """The runner's duckdb_spatial entry in one line (006): installed, with what; or where it stopped, and why."""
    if not isinstance(s, dict) or not s.get("status"):
        return "not reported"
    if s["status"] == "installed":
        return "installed (DuckDB %s, %s, sha256 %s…)" % (s.get("version", "?"), s.get("platform", "?"),
                                                         str(s.get("sha256", "?"))[:16])
    if not s.get("stage") and not s.get("reason"):
        return str(s["status"])  # a runner before 006: its status alone
    where = " at the %s" % s["stage"] if s.get("stage") else ""
    return "%s%s: %s" % (s["status"], where, " ".join(str(s.get("reason") or "no reason given").split()))


def note_text(slice_id: str, tip: str, data: dict | None, headline: str, why: str, jid: str) -> str:
    d = data or {}
    fail = d.get("failing") or {}
    nr = d.get("not_run") or {}
    out = [f"# Early warning: {slice_id} at {tip[:8]}: {headline}", "",
           f"**{ADVICE}.** {RED_RULE}", "",
           f"- Result: {headline} ({why})",
           f"- Slice tip: `{tip}`",
           f"- Main: `{d.get('main', '?')}`",
           f"- Candidate tree hash: `{d.get('tree', 'none')}` (merge commit `{d.get('merge', 'none')}`)",
           f"- Time taken: {d.get('seconds', '?')} s",
           f"- Runner version: {d.get('runner_version', 'unknown')}; this script's: {proto.RUNNER_VERSION}",
           f"- Run id: `{jid or 'none'}`", f"- Written: {c.now()}", ""]
    if "duckdb_spatial" in d:  # what made the DuckDB tests' extension, or why not, in one line (006)
        out.insert(out.index(f"- Run id: `{jid or 'none'}`"), f"- DuckDB's spatial extension: {spatial_line(d['duckdb_spatial'])}")
    if headline == "NO RESULT" and jid:
        out += [f"Ask again later: `early_warning.py {slice_id} --result {jid}`.", ""]
    if fail.get("targets") or fail.get("tests"):
        out += ["## Failing (rerun each on the Mac before sending the slice back)", ""]
        by = fail.get("by_target") or {}
        named = set()
        for t in fail.get("targets", []):
            out.append(f"- make target `{t}`" + ("" if by.get(t) else ": no failing test named in its output"))
            out += [f"  - test `{n}`" for n in by.get(t, [])]
            named.update(by.get(t, []))
        for step, tests in by.items():
            if step not in fail.get("targets", []):
                out.append(f"- {step}")
                out += [f"  - test `{n}`" for n in tests]
                named.update(tests)
        out += [f"- test `{t}`" for t in fail.get("tests", []) if t not in named]
        out.append("")
    if d.get("conflicts"):
        out += ["## Conflicting files", ""] + [f"- `{f}`" for f in d["conflicts"]] + [""]
    out += ["## Not run on the server (never counted as passed)", "",
            f"- The client-name check: {d.get('client_names', 'not run (no client-name list on this machine)')}",
            f"- The live step: {nr.get('live_step') or 'not run'}"]
    out += [f"- make target `{t['name']}`: {t.get('why', '')}" for t in nr.get("targets", [])]
    out += [f"- test file `{t['name']}`: {t.get('why', '')}" for t in nr.get("test_files", [])]
    out += [f"- `{t['name']}`: {t.get('why', '')}" for t in nr.get("mac_only", [])]
    if nr.get("docker_skipped"):
        out.append(f"- {len(nr['docker_skipped'])} test files' docker calls were skipped (the repository's docker "
                   "guard): " + ", ".join(f"`{n}`" for n in nr["docker_skipped"][:40]))
    if d.get("list_drift"):
        out += ["", "## The named lists do not match the candidate (lists.py)", ""] + [f"- {x}" for x in d["list_drift"]]
    out += ["", f"_{ADVICE}._", ""]
    return "\n".join(out)


def write_note(slice_id: str, tip: str, data: dict | None, headline: str, why: str, jid: str, s: dict) -> Path:
    path = c.REPO / NOTES_REL / f"{slice_id}-{tip[:8]}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(scrub(note_text(slice_id, tip, data, headline, why, jid), s))
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slice")
    ap.add_argument("--result", metavar="ID", help="poll a run already started")
    a = ap.parse_args(argv)
    s: dict = {}
    try:
        if not re.fullmatch(r"[A-Za-z0-9]+", a.slice):
            raise Refused("A slice id is letters and digits only.")
        if a.result is not None and not re.fullmatch(proto.ID_PATTERN, a.result):
            raise Refused(f"A run id is {proto.ID_LENGTH} lower-case hexadecimal characters.")
        s = load_setting()
        branch, tip = verified_tip(a.slice)
    except Refused as e:
        print(f"Refused: {e}", file=sys.stderr)
        return REFUSED_HERE
    if a.result:
        jid, sent = a.result, None
    else:
        state, sent, code = start(s, branch)
        if state != "started":
            headline, exit_code, why = outcome(sent, code)
            path = write_note(a.slice, tip, sent, headline, why, "", s)
            print(scrub(f"{headline}: {why}. Note: {path}", s))
            return exit_code
        jid = sent["id"]
    data, code = poll(s, jid)
    if data and data.get("state") == "done" and re.fullmatch(r"[0-9a-f]{40}", str(data.get("holds_main", ""))):
        OWN.mkdir(parents=True, exist_ok=True)
        c.write_json(HELD, {"main": data["holds_main"], "at": c.now()})
    if data and data.get("state") == "done" and data.get("tip") != tip:
        data = {"state": "unknown"}  # an answer for another tip is no answer for this one
    headline, exit_code, why = outcome(data, code)
    path = write_note(a.slice, tip, data, headline, why, jid, s)
    print(scrub(f"{headline}: {why}. Note: {path}", s))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
