#!/usr/bin/env python3
"""The demo server as an early warning for a slice (DEMO_SERVER_EARLY_WARNING_BRIEF.md). ADVICE ONLY.

    early_warning.py <slice>                  bundle main's tip and the slice's tip, send them to the demo server's
                                              runner, poll until it answers, and write the result as a note
    early_warning.py <slice> --result <id>    poll a run already started (its id is in the note of a run that was
                                              still going at the deadline) and write its note
    early_warning.py <A> <B> [<C>]            a stack (009): main+A, main+A+B and main+A+B+C tested at once, one job
                                              each, in that merge order; one note each. When one is red, the ones
                                              above it are tested again without it, at once after (013, 3)
    early_warning.py <slice>... --again       send it even though a run of the same candidate already has a verdict
                                              on the current main ("Never sent twice", below)
    early_warning.py standing <slice>         what the slice's records let this script do now (013): verified,
                                              tested-not-yet-verified, or refused and why; and each held note of the
                                              slice marked void (its tip moved) or now verified. Exit 0, 2 refused
    early_warning.py fetch <id>               the runner's own result for run <id>, as `result <id>` returns it, on
                                              one line (012 a); exit 0, non-zero when it cannot be fetched. Never
                                              read from a note.
    early_warning.py summary <id>             a red run's summary (010), as the server's `summary <id>` gives it: the
                                              failures' extract by script, the model's advice marked as advice;
                                              exit 0, non-zero when it cannot be fetched
    early_warning.py ask ports|ollama|shield  the owner's read-only questions (24 November), as the server answers
                                              them on one line: which ports in the ephemeral range other accounts
                                              listen on, by uid and how long seen; whether Ollama has a model
                                              loaded; whether the shield would hold now. The server changes nothing.
                                              Exit 0, non-zero when there is no answer
    early_warning.py <slice> --trust <id>|auto --tree <hash>
                                              for the merge (009): ask the server itself for run <id>, never a note,
                                              and say in JSON whether it proves the candidate tree <hash>: every
                                              target the tree's own Makefiles name passed or is on the list the Mac
                                              must still run. Exit 0 trusted, 1 not trusted, 4 no answer.
                                              `auto`: the runs of this slice at its tip that this script recorded,
                                              newest first, until one is trusted.

The build checks (the owner's file 017, item 1, 25 November 2026): when `build-server.json` exists (the same schema as
the setting), each single slice's bundle is also sent, at the same moment, to the build account's forced command,
`checks <ID>` (build_server/runner.py), which runs the merge's container checks in its own rootless Docker. Its result
comes back only through the backup repository, for the merge (server_gate.build_part); this script prints only
whether it was sent, keeps what the build account holds (build-held.json) and one line per send (build-sent.jsonl).
Nothing the build account answers, or fails to, changes this script's result or exit.

The Mac's merge run (merge_slice.py merge) is the only gate to main. This script changes nothing in merge_slice.py,
stop_check.py or the guard, and writes no record the merge reads: nothing under ~/.ospreyflow/slice-line/records/.
It writes the note, OspreyFlow_Build/process/lanes/v062/early_warning/<slice>-<tip first 8>.md in the main checkout
(the conductor's records folder), and one file of its own, ~/.ospreyflow/slice-line/early-warning/held.json (which
main the server already holds, so the next bundle need carry only what is new).

How the conductor uses a result. Green changes nothing. On red, rerun the named failing check on the Mac before
sending the slice back, because the server is a different kind of machine: a red from the server alone never costs
a builder a round. ("not run" is never green: it says what the server could not check.)

What it takes (013, the owner's decision of 22 November 2026, conductor file 015): a slice whose newest verifier
record (verify-<tip>.json; the merge's own verify-gate-* records are not a verifier's) is a pass for the branch's own
tip, whatever its phase (a refused slice its builder has not touched still has that: the line-fix session's rule, as
the owner ruled); a slice at `verified` at the branch's tip (the owner's acceptance); and a slice whose builder's
checks are green at the branch's tip (tests-<tip>.json) and whose verifier has not yet answered (phase `verifying`, no
verify-<tip>.json). That last result is held, "tested, not yet verified", for that tip only: if the verifier's round
moves the tip, its note says it is void, and --trust never counts it (only a verified slice's run, for its exact tip
and tree, can count). Anything else is refused, and so is a merged slice. It never runs while no setting file exists.
The setting lives outside the repository and is the owner's:

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

Never sent twice (the line-fix session's request of 23 November 2026). A candidate is main, the members below the slice in
its stack, and the slice, each at its tip. It is not sent again while a run of exactly that candidate ended with a
verdict (pass, fail or conflict) on the current main, as the server says when asked for that run (never a note); the
earlier run's note stands, and the exit code is that run's. --again sends it anyway. An error (a refusal, a shield
breach, no result) is no verdict, and never stops a send. In a stack, a member already red or in conflict on this main
is left out, as after a red (013, 3), and the ones above are tested without it; a member already green that others
stand on stops the stack (Refused), unless --again.

The runner's result for one job (`result <id>`, as `fetch <id>` prints it), the shape the merge reads:

    state           "done" | "running" | "died" | "unknown" | "refused"; only "done" carries what follows
    id              the job's run id (16 hex)
    slice, tip      the member this job tests: the last of `stack`
    main            the main commit the job was built on
    stack           the members up to and including this one, in merge order, each {"slice", "tip"}: the job tests
                    main + each of them merged in turn. A slice run alone: [itself]. Member k of a stack: its first k
    position, of    this job's place in its group, from 1, and the group's size (1 and 1 when run alone)
    group           the group's run ids in merge order (group[position - 1] is this job's own id)
    stack_id        the stack's own id, for `result <stack_id>`; absent for a slice run alone
    lane            the lane slot whose ports the job used
    verdict         "pass" | "fail" | "conflict" | "error" (error: no verdict on the slice; `words` says why)
    words           one line saying why, for anything but a pass
    tree            the candidate tree it tested: the tree of its own merge commit `merge`
    merges          each member's merge commit, in order
    holds_main      the main the server now holds (for the next bundle)
    checks, passed_targets, failing {targets, tests}, not_run {targets, test_files, docker_skipped, mac_only,
    live_step}      what ran and how it ended; "not run" is never a pass
    duckdb_spatial  {status: installed | failed | not fetched, stage, reason, version, platform, sha256}
    shield          only when the shield check waited for another account's listener and it went (the owner, 24
                    November): what it found and how long it waited; the note says it
    runner_version  "ew-2"; seconds, finished, usage, steps, scan_rows, list_drift, lists_from, client_names, advice

`result <stack_id>` gives {state, id, main, runner_version, stack: [each member job's result above, in merge order],
advice}; its `state` is "running" while any member runs.

Nothing of the setting (host, user, key path) is ever written into the note or printed: an unreachable server is
said as "unreachable (ssh exit N)", never with ssh's own words, which name the host.

Exit codes, none of which lies: 0 green (pass); 1 red (fail, or the slice does not merge onto main); 2 refused here
(not a slice it takes, no setting, a bad setting); 3 refused by the runner (busy, a bundle it would not take); 4 no result
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
import lists as named_lists  # noqa: E402
import protocol as proto  # noqa: E402

SETTING = c.DATA / "demo-server.json"
#: 017, item 1 (the owner, 25 November 2026): the build account's container checks. Its own setting (the same schema,
#: its own key, whose forced command takes `checks <ID>` and a bundle), its own record of the main it holds, and one
#: line per send. Without the setting nothing is sent; nothing it answers changes the early warning's result.
BUILD_SETTING = c.DATA / "build-server.json"
OWN = c.DATA / "early-warning"
HELD = OWN / "held.json"
BUILD_HELD = OWN / "build-held.json"
BUILD_SENT = OWN / "build-sent.jsonl"
#: Every run this script started or polled, one JSON line each (slice, tip, id, tree, stack): only where to ask, never
#: what the answer was. `--trust auto` reads it for the run ids to ask the server about (009, item 3).
RUNS = OWN / "runs.jsonl"
#: One file per run in flight, <slice>-<tip first 8>.json, removed when the run ends, so the board can say "running"
#: (012 d).
RUNNING = OWN / "running"
NOTES_REL = f"{c.V062_REL}/early_warning"
SAFE_HOST = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9.:-]*\Z")
SAFE_USER = re.compile(r"\A[a-z_][a-z0-9_-]*\Z")
GREEN, RED, REFUSED_HERE, REFUSED_THERE, NO_RESULT = 0, 1, 2, 3, 4
RED_RULE = ("On red, rerun the named failing check on the Mac before sending the slice back, because the server is a "
            "different kind of machine: a red from the server alone never costs a builder a round. Green changes "
            "nothing.")
ADVICE = "advice only; the Mac's merge run is the gate"
#: The runner versions whose results carry one check per target (009); an older result is never trusted.
TRUSTED_VERSIONS = ("ew-2",)
#: The checks the server never runs, whatever its result says: the Mac runs these for every candidate (009, item 4).
ALWAYS_ON_THE_MAC = ("client-name-check", "the live step")
#: What a slice's records make it for this script (013): its result can count (verified), or is held (not yet).
VERIFIED, NOT_YET = "verified", "tested, not yet verified"
#: A held note's marker, so `standing` finds it again; and the words that open it.
HELD_MARK = "<!-- held: tested, not yet verified, tip %s -->"
HELD_WORDS = ("**Tested, not yet verified.** The verifier had not answered when this ran. This result is held for tip "
              "`%s` only: it counts for nothing until the verifier passes that exact commit, and if the verifier's "
              "round moves the tip, it is void (this note will say so).")


class Refused(Exception):
    pass


def load_setting(path: Path = SETTING) -> dict:
    if not path.is_file():
        raise Refused(f"No setting file ({path}): the early warning never runs without one. The owner creates it "
                      "once the runner is installed and the key is in place; its schema is in this script's --help.")
    try:
        s = json.loads(path.read_text())
    except (OSError, ValueError):
        raise Refused(f"The setting file ({path}) is not readable JSON.")
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


def verifier_records(rec: Path) -> list[Path]:
    """The slice's verifier records, oldest first, as resume.py orders them (by when each was written); the merge's
    own verify-gate-* records are findings the merge wrote, not a verifier's, so they are not among them."""
    return sorted((x for x in rec.glob("verify-*.json") if not x.name.startswith("verify-gate-")),
                  key=lambda x: x.stat().st_mtime)


def owners_acceptance(slice_id: str, tip: str) -> bool:
    """The owner's acceptance of the verifier's findings for exactly this tip, as the merge itself takes it
    (merge_slice.acceptance, read, never changed): a slice he accepted that is later refused is taken (the owner, 22
    November 2026, on 013's question). A record that is missing or does not stand is no acceptance."""
    import merge_slice
    try:
        return merge_slice.acceptance(slice_id, tip) is not None
    except merge_slice.Refused:
        return False


def standing_of(slice_id: str) -> tuple[str, str, str, str]:
    """(branch, tip, standing, why) for the branch's tip now; Refused, in words, when this script does not take it.

    verified: the newest verifier record is a pass for exactly the branch's tip, in any phase (013, 2: a refused slice
    its builder has not touched still has that, and one the builder has touched has a new tip, which no pass names);
    or it is the findings for that tip and the owner's acceptance of them stands as the merge would take it;
    or the records have it at verified at that tip (the owner's acceptance of findings). Not yet: the builder's checks
    are green at the tip (the Stop hook's tests-<tip>.json) and the verifier has not answered (phase verifying, no
    verify-<tip>.json) (013, 1)."""
    rec = c.rec_dir(slice_id)
    frozen = c.read_json(rec / "frozen.json")
    if not frozen or not frozen.get("branch"):
        raise Refused(f"{slice_id} was never started (no frozen record): nothing to warn about.")
    st = c.state(slice_id)
    phase = st.get("phase") or "nothing"
    branch = frozen["branch"]
    tip = c.git(["rev-parse", "--verify", "-q", f"refs/heads/{branch}"], c.REPO, check=False)
    if not tip:
        raise Refused(f"{slice_id} has no branch {branch}: nothing to test.")
    if phase == "merged":
        raise Refused(f"{slice_id} is merged: it is on main already.")
    recs = verifier_records(rec)
    newest = c.read_json(recs[-1]) if recs else None
    if newest and recs[-1].name == f"verify-{tip}.json" and newest.get("commit") == tip \
            and newest.get("verdict") == "pass":
        return branch, tip, VERIFIED, (f"the newest verifier record is a pass for the branch's tip {tip[:10]}"
                                       + ("" if phase == "verified" else f" (phase {phase})"))
    if newest and recs[-1].name == f"verify-{tip}.json" and owners_acceptance(slice_id, tip):
        return branch, tip, VERIFIED, (f"the owner accepted the verifier's findings for the branch's tip {tip[:10]}, "
                                       "as the merge would take it" + ("" if phase == "verified" else f" (phase {phase})"))
    if phase == "verified":
        if st.get("tip") != tip:
            raise Refused(f"{slice_id}'s verified tip is not its branch's tip ({(st.get('tip') or '')[:10]} recorded, "
                          f"{tip[:10]} now): the early warning runs only for the tip the verifier passed.")
        return branch, tip, VERIFIED, f"at verified in its records at the branch's tip {tip[:10]}"
    tests = c.read_json(rec / f"tests-{tip}.json") or {}
    if phase == "verifying" and st.get("tip") == tip and tests.get("green") is True and tests.get("commit") == tip:
        if (rec / f"verify-{tip}.json").exists():
            raise Refused(f"{slice_id}'s verifier has answered for {tip[:10]} and it is not a pass: not a slice to "
                          "test before its verifier, and not verified.")
        return branch, tip, NOT_YET, (f"the builder's checks are green at {tip[:10]} and the verifier has not "
                                      "answered: tested, not yet verified")
    why = ("its newest verifier record is not a pass for the branch's tip" if recs else "it has no verifier record")
    raise Refused(f"{slice_id} is not at verified in its records (it is at {phase}), {why}, and it is not a tip whose "
                  "builder's checks are green waiting on its verifier: the early warning takes only those.")


def verified_tip(slice_id: str) -> tuple[str, str]:
    """The branch and tip of a slice whose result can count; Refused otherwise (a held one included)."""
    branch, tip, standing, _ = standing_of(slice_id)
    if standing != VERIFIED:
        raise Refused(f"{slice_id} is {standing} at {tip[:10]}.")
    return branch, tip


def held_notes(slice_id: str) -> list[Path]:
    d = c.REPO / NOTES_REL
    return sorted(d.glob(f"{slice_id}-*.md")) if d.is_dir() else []


def review_held(slice_id: str) -> dict:
    """Every held note of the slice, checked against its records now: void when the branch's tip is no longer the
    tip tested; now verified when the verifier has since passed that exact tip. Said at the top of the note, once."""
    try:
        _, tip, standing, _ = standing_of(slice_id)
    except Refused:
        frozen = c.read_json(c.rec_dir(slice_id) / "frozen.json") or {}
        tip = c.git(["rev-parse", "--verify", "-q", f"refs/heads/{frozen.get('branch', '')}"], c.REPO,
                    check=False) if frozen.get("branch") else ""
        standing = ""
    said = {"void": [], "now_verified": []}
    for n in held_notes(slice_id):
        text = n.read_text()
        m = re.search(r"<!-- held: tested, not yet verified, tip ([0-9a-f]{40}) -->", text)
        if not m or "\n**VOID.**" in text or "\n**Now verified.**" in text:
            continue
        held = m.group(1)
        if tip != held:
            line = (f"**VOID.** This result was for tip `{held[:10]}`, which the verifier never passed; the branch is "
                    f"now at `{(tip or 'nothing')[:10]}` (the verifier's round moved it). It counts for nothing. "
                    f"Seen {c.now()}.")
            said["void"].append(n.name)
        elif standing == VERIFIED:
            line = (f"**Now verified.** The verifier has since passed this exact tip `{held[:10]}`, so this result "
                    f"stands as a verified slice's would (the merge still asks the server itself). Seen {c.now()}.")
            said["now_verified"].append(n.name)
        else:
            continue
        title, _, rest = text.partition("\n")
        n.write_text(f"{title}\n\n{line}\n{rest}")
    return said


def standing_cmd(argv: list) -> int:
    """`early_warning.py standing <slice>`: what this script may do for the slice now, and its held notes reviewed."""
    if len(argv) != 2 or not re.fullmatch(proto.SLICE_PATTERN, argv[1]):
        print("Refused: standing takes one slice id.", file=sys.stderr)
        return REFUSED_HERE
    said = {"slice": argv[1], "notes": review_held(argv[1])}
    try:
        _, tip, standing, why = standing_of(argv[1])
        said.update(tip=tip, standing=standing, why=why, counts=standing == VERIFIED)
        code = GREEN
    except Refused as e:
        said.update(standing="refused", why=str(e), counts=False)
        code = REFUSED_HERE
    print(json.dumps(said, indent=1, sort_keys=True))
    return code


#: The train in flight (merge_slice.py train writes it while its gate runs), and the base a stack named on it is sent on
#: (--on-train; 65, the conductor's word of 27 November 2026): its gated commit, main plus the train. None: main.
INFLIGHT = c.DATA / "trains" / "inflight.json"
ON_TRAIN: str | None = None


def train_base(slices: list[str]) -> dict:
    """The train in flight, for a stack named on main plus it: refused when no train is in flight, when a slice of the
    stack is one of the train's parts, or when its gated commit is not here."""
    t = c.read_json(INFLIGHT) or {}
    gated = str(t.get("gated") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", gated):
        raise Refused("no train is in flight (no gated commit in trains/inflight.json): send the stack on main.")
    inside = [x for x in slices if x in (t.get("parts") or [])]
    if inside:
        raise Refused(f"{inside[0]} is in the train {t.get('train')}: a stack on the train holds none of its parts.")
    if c.git(["cat-file", "-t", gated], c.REPO, check=False) != "commit":
        raise Refused(f"the train's gated commit {gated[:10]} is not in this repository.")
    return t


def make_bundle(branch, dest: Path, full: bool, held_file: Path = HELD, base: str | None = None) -> None:
    """A git bundle of main's tip and the slice's tip (or each slice's, for a stack), from commits only (never a
    working-tree file); less what the server already holds, unless `full`. With `base` (--on-train: the train's gated
    commit), the bundle's refs/heads/main is that commit, main plus the train, and the Mac's own main is untouched: the
    bundle is made in a throwaway repository that borrows this one's objects."""
    branches = [branch] if isinstance(branch, str) else list(branch)
    if "main" in branches:
        raise Refused("a bundle's slices are their branches, never main")
    main = base or c.git(["rev-parse", "refs/heads/main"], c.REPO)
    held = (c.read_json(held_file) or {}).get("main", "")
    args = ["bundle", "create", "-q", str(dest), "refs/heads/main", *[f"refs/heads/{b}" for b in branches]]
    if not full and re.fullmatch(r"[0-9a-f]{40}", held or "") and \
            subprocess.run(["git", "merge-base", "--is-ancestor", held, main], cwd=c.REPO).returncode == 0:
        # git leaves out a ref whose tip is excluded, so when the server holds main itself the bundle stops at main's
        # parents (which it holds too): main's tip is always in the bundle, by name
        args += [f"^{held}"] if held != main else [f"^{x}" for x in c.git(["rev-parse", f"{main}^@"], c.REPO).split()]
    if not base:
        c.git(args, c.REPO)
        return
    with tempfile.TemporaryDirectory(prefix="early-warning-base-") as d:
        objects = c.git(["rev-parse", "--path-format=absolute", "--git-common-dir"], c.REPO) + "/objects"
        c.git(["init", "-q", "--bare", d], c.REPO)
        Path(d, "objects", "info", "alternates").write_text(objects + "\n")
        c.git(["update-ref", "refs/heads/main", base], d)
        for b in branches:
            c.git(["update-ref", f"refs/heads/{b}", c.git(["rev-parse", f"refs/heads/{b}"], c.REPO)], d)
        c.git(args, d)


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
                LAST_LINE[0] = ln
                return r.returncode, data
        except ValueError:
            continue
    return r.returncode, None


#: The runner's own line for the last answer ssh() parsed, unchanged: what `fetch` prints.
LAST_LINE = [""]


def running_file(slice_id: str, tip: str) -> Path:
    return RUNNING / f"{slice_id}-{tip[:8]}.json"


def mark_running(slice_id: str, tip: str, jid: str, stack_id: str = "", standing: str = VERIFIED) -> None:
    RUNNING.mkdir(parents=True, exist_ok=True)
    c.write_json(running_file(slice_id, tip), {"slice": slice_id, "tip": tip, "id": jid, "started": c.now(),
                                                "standing": standing, **({"stack_id": stack_id} if stack_id else {})})


def unmark_running(slice_id: str, tip: str) -> None:
    try:
        running_file(slice_id, tip).unlink()
    except OSError:
        pass


def start(s: dict, branch, order: list | None = None) -> tuple[str, dict | None, int]:
    """Send the bundle; once more in full if the server lacks what an incremental one is built on. With `order`, a
    stack: the slices' branches, and the command names them in merge order."""
    with tempfile.TemporaryDirectory(prefix="early-warning-") as d:
        for full in (False, True):
            b = Path(d) / "slice.bundle"
            b.unlink(missing_ok=True)
            make_bundle(branch, b, full, base=ON_TRAIN)
            with b.open("rb") as fh:
                code, data = ssh(s, ["stack", *order] if order else ["run"], stdin=fh)
            if data and data.get("state") == "refused" and data.get("reason") == "bundle-prerequisites" and not full:
                continue
            return ("started" if data and data.get("state") == "started" else "failed"), data, code
    return "failed", None, 255


def send_checks(slice_id: str, branch: str, tip: str) -> str:
    """017, item 1: the same bundle's shape (main's tip and the slice's) sent to the build account's forced command,
    `checks <ID>`, at the moment the early warning is sent; once more in full if the build account lacks what an
    incremental one is built on. Its result comes back only through the backup repository (server_gate.build_part),
    never over SSH. Words for the terminal, which never name the setting; one line in build-sent.jsonl."""
    if not BUILD_SETTING.is_file():
        return "not sent (no build setting)"
    try:
        bs = load_setting(BUILD_SETTING)
    except Refused:
        return "not sent (the build setting is not usable)"
    data, code = None, 255
    with tempfile.TemporaryDirectory(prefix="build-checks-") as d:
        for full in (False, True):
            b = Path(d) / "slice.bundle"
            b.unlink(missing_ok=True)
            make_bundle(branch, b, full, BUILD_HELD)
            with b.open("rb") as fh:
                code, data = ssh(bs, ["checks", slice_id], stdin=fh, timeout=900)
            if not (data and data.get("state") == "refused" and data.get("reason") == "bundle-prerequisites"):
                break
    state = (data or {}).get("state")
    OWN.mkdir(parents=True, exist_ok=True)
    if state == "started" and re.fullmatch(r"[0-9a-f]{40}", str(data.get("holds_main", ""))):
        c.write_json(BUILD_HELD, {"main": data["holds_main"], "at": c.now()})
    with BUILD_SENT.open("a") as fh:
        fh.write(json.dumps({"slice": slice_id, "tip": tip, "at": c.now(), "state": state or "no answer",
                             "id": (data or {}).get("id"), "reason": (data or {}).get("reason"), "ssh": code}) + "\n")
    if state == "started" and re.fullmatch(proto.ID_PATTERN, str(data.get("id", ""))):
        return f"sent (run {data['id']}; its result comes back through the backup repository)"
    if state == "refused":
        return f"refused by the build account ({data.get('reason')})"
    return f"no answer from the build account (ssh exit {code})"


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


#: The most of the slice's own files read when looking for a path main moved (item 4), and the most bytes of each.
MAX_FILES_READ, MAX_FILE_BYTES = 400, 1024 * 1024


def merged_ahead(tip: str, d: dict) -> list[str]:
    """013, item 4: why a red is of the kind broken by what merged ahead, in plain words; [] when nothing shows it.
    A conflict always is. Otherwise: a path that main (or a slice merged before this one in the stack) renamed or
    removed since this slice's base, which a file this slice changed still names. Read with git, on this machine."""
    said = []
    if d.get("verdict") == "conflict":
        files = ", ".join(f"`{f}`" for f in (d.get("conflicts") or [])[:10]) or "files the runner named"
        ahead = "main" + "".join(f" + {x['slice']}" for x in (d.get("stack") or [])[:-1])
        said.append(f"it does not merge onto {ahead}: a conflict in {files}. What merged ahead of it changed the same "
                    "lines since it was built.")
        return said
    if d.get("verdict") != "fail":
        return said
    ahead = [str(d.get("main") or "")] + [x.get("tip", "") for x in (d.get("stack") or [])[:-1]]
    ahead = [x for x in ahead if re.fullmatch(r"[0-9a-f]{40}", x)]
    moved = {}
    for a in ahead:
        base = c.git(["merge-base", tip, a], c.REPO, check=False)
        if not base:
            continue
        for ln in c.git(["diff", "--name-status", "-M", base, a], c.REPO, check=False).splitlines():
            parts = ln.split("\t")
            if parts and parts[0][:1] in ("R", "D") and len(parts) >= 2:
                moved.setdefault(parts[1], parts[2] if parts[0][:1] == "R" and len(parts) > 2 else "")
    if not moved:
        return said
    base = c.git(["merge-base", tip, ahead[0]], c.REPO, check=False) if ahead else ""
    mine = c.git(["diff", "--name-only", "--diff-filter=AM", base, tip], c.REPO, check=False).splitlines() if base else []
    hits = {}
    for f in mine[:MAX_FILES_READ]:
        try:
            raw = subprocess.run(["git", "show", f"{tip}:{f}"], cwd=c.REPO, capture_output=True, timeout=30).stdout
        except (OSError, subprocess.TimeoutExpired):
            continue
        if b"\0" in raw[:8000]:
            continue
        text = raw[:MAX_FILE_BYTES].decode(errors="replace")
        for old in moved:
            short = old.split("/", 1)[1] if "/" in old else old  # as a component's own files name it
            if old in text or ("/" in short and short in text):
                hits.setdefault(old, []).append(f)
    for old, files in sorted(hits.items()):
        new = moved[old]
        said.append(f"what merged ahead of it {'moved' if new else 'removed'} `{old}`" + (f" to `{new}`" if new else "")
                    + ", and this slice's " + ", ".join(f"`{f}`" for f in files[:5]) + " still names the old path.")
    return said


def failures_of(d: dict | None) -> set:
    f = (d or {}).get("failing") or {}
    return set(f.get("tests") or []) | {n for v in (f.get("by_target") or {}).values() for n in v}


def note_text(slice_id: str, tip: str, data: dict | None, headline: str, why: str, jid: str,
              standing: str = VERIFIED, retest: dict | None = None, carried: list | None = None) -> str:
    d = data or {}
    fail = d.get("failing") or {}
    nr = d.get("not_run") or {}
    stack = d.get("stack") or []
    out = [f"# Early warning: {slice_id} at {tip[:8]}: {headline}" + (f" ({NOT_YET})" if standing == NOT_YET else ""),
           ""]
    if standing == NOT_YET:
        out += [HELD_MARK % tip, HELD_WORDS % tip, ""]
    if headline == "RED":
        try:
            ahead = merged_ahead(tip, d)
        except Exception:  # advice: a look that fails says nothing, and never stops the note
            ahead = []
        if carried:  # a stack: every failure here fails for a slice merged before it (013, 4)
            ahead = [f"every failing test here also fails for {' and '.join(carried)}, merged before it in this stack, "
                     f"so it is {' and '.join(carried)}'s red carried up; this slice is tested again without it."] + ahead
        if ahead:
            out += ["**Broken by what merged ahead, not by the server.** This red is the slice meeting what merged "
                    "before it, so the Mac's merge would be refused for it too: " + " ".join(ahead), ""]
    if retest and retest.get("earlier"):
        out += [f"**Tested without {retest['without']}**, which already had a verdict of red on this main in run "
                f"`{retest['stack_id']}` (`early_warning.py fetch {retest['stack_id']}`), so it was not sent again "
                ": this is its own result, in the stack named below.", ""]
    elif retest:
        out += [f"**Tested again without {retest['without']}**, which was red in stack `{retest['stack_id']}` "
                f"(`early_warning.py fetch {retest['stack_id']}`): this is its own result, in the stack named below.", ""]
    out += [f"**{ADVICE}.** {RED_RULE}", "",
           f"- Result: {headline} ({why})",
           f"- Slice tip: `{tip}`",
           f"- Main: `{d.get('main', '?')}`",
           f"- Candidate tree hash: `{d.get('tree', 'none')}` (merge commit `{d.get('merge', 'none')}`)",
           f"- Time taken: {d.get('seconds', '?')} s",
           f"- Runner version: {d.get('runner_version', 'unknown')}; this script's: {proto.RUNNER_VERSION}",
           f"- Run id: `{jid or 'none'}`", f"- Written: {c.now()}", ""]
    if d.get("stack_id"):
        out.insert(out.index(f"- Run id: `{jid or 'none'}`") + 1, f"- The stack's run id: `{d['stack_id']}` "
                   f"(`early_warning.py fetch {d['stack_id']}` gives the stack's one result)")
    if len(stack) > 1:  # a stack's candidate: main with every slice before this one merged first, in that order
        out.insert(out.index(f"- Main: `{d.get('main', '?')}`") + 1, "- Stack: candidate %d of %d, main + %s (merged in "
                   "that order)" % (d.get("position", len(stack)), d.get("of", len(stack)),
                                    " + ".join(f"{x['slice']} `{x['tip'][:10]}`" for x in stack)))
    if d.get("shield"):  # the shield check waited for another account's listener, and it went (24 November)
        out.insert(out.index(f"- Run id: `{jid or 'none'}`"), f"- Shield: {d['shield']}")
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
    if d.get("checks"):
        block = {"run_id": jid, "slice": slice_id, "tip": tip, "main": d.get("main"), "tree": d.get("tree"),
                 "stack": stack, "verdict": d.get("verdict"), "runner_version": d.get("runner_version"),
                 "passed": [x["name"] for x in d["checks"] if x.get("status") == "passed"],
                 "failed": [x["name"] for x in d["checks"] if x.get("status") == "failed"],
                 "not_run": [x["name"] for x in d["checks"] if x.get("status") == "not run"]}
        out += ["", "## The checks, for scripts", "",
                "The merge never reads this block, or this note: it asks the server for the run by its id itself "
                f"(`early_warning.py {slice_id} --trust {jid or '<id>'} --tree <candidate tree>`), so a note written "
                "by hand proves nothing.", "", "```json", json.dumps(block, indent=1), "```"]
    out += ["", f"_{ADVICE}._", ""]
    return "\n".join(out)


def record_run(slice_id: str, tip: str, jid: str, data: dict | None, standing: str = VERIFIED) -> None:
    """Where to ask later (RUNS): this run's id, for this slice and tip, and whether it was verified when it ran.
    Never its verdict: the server says that."""
    if not jid:
        return
    d = data or {}
    OWN.mkdir(parents=True, exist_ok=True)
    with RUNS.open("a") as fh:
        fh.write(json.dumps({"slice": slice_id, "tip": tip, "id": jid, "tree": d.get("tree"), "main": d.get("main"),
                             "stack": [x.get("slice") for x in d.get("stack") or []], "standing": standing,
                             "at": c.now()}) + "\n")


def recorded_runs(slice_id: str, tip: str, tree: str) -> list[str]:
    """The run to ask about for this slice at this tip: the newest RUNS holds for this candidate tree, else the newest
    of any (the server's answer then says which tree it tested). Only ever one: a newer red is never passed over for
    an older green."""
    seen = []
    try:
        lines = RUNS.read_text().splitlines()
    except OSError:
        return []
    for ln in reversed(lines):
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        jid = r.get("id") if isinstance(r, dict) else None
        if r.get("slice") == slice_id and r.get("tip") == tip and isinstance(jid, str) \
                and re.fullmatch(proto.ID_PATTERN, jid) and jid not in [x for x, _ in seen]:
            seen.append((jid, r.get("tree")))
    same = [x for x, tr in seen if tr == tree]
    return (same or [x for x, _ in seen])[:1]


#: How many recorded runs of one candidate are asked about before it is sent (never sent twice): the newest few are enough.
ANSWERED_ASKS = 3


def current_main() -> str:
    """The main a run is sent on: main, or with --on-train the train's gated commit (main plus the train)."""
    return ON_TRAIN or c.git(["rev-parse", "refs/heads/main"], c.REPO)


def answered(s: dict, slice_id: str, tip: str, below: list, main: str) -> tuple[str, dict] | None:
    """Never sent twice: (the run's id, its result) for the newest run RUNS holds of exactly this candidate (main, then each of
    `below` as (slice, tip), then this slice at this tip) that the server says ended with a verdict on `main`; None
    when there is none, or the server cannot say. Only the server's own answer counts, never a note."""
    want = [{"slice": x, "tip": t} for x, t in below] + [{"slice": slice_id, "tip": tip}]
    try:
        lines = RUNS.read_text().splitlines()
    except OSError:
        return None
    asked = 0
    for ln in reversed(lines):
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if not isinstance(r, dict) or r.get("slice") != slice_id or r.get("tip") != tip \
                or r.get("stack") != [x["slice"] for x in want] or r.get("main") not in (None, main) \
                or not re.fullmatch(proto.ID_PATTERN, str(r.get("id"))):
            continue
        asked += 1
        if asked > ANSWERED_ASKS:
            return None
        _, data = ssh(s, ["result", r["id"]], timeout=120)
        if data and data.get("state") == "done" and data.get("verdict") in ("pass", "fail", "conflict") \
                and data.get("main") == main and data.get("tip") == tip and data.get("stack") == want:
            return r["id"], data
    return None


def not_again(slice_id: str, tip: str, jid: str, data: dict, s: dict) -> int:
    headline, exit_code, why = outcome(data, 0)
    print(scrub(f"{slice_id}: not sent again: run {jid} already gave a verdict for tip {tip[:10]} on this main "
                f"({headline}: {why}). Its note stands; --again sends it anyway.", s))
    return exit_code


def write_note(slice_id: str, tip: str, data: dict | None, headline: str, why: str, jid: str, s: dict,
               before: list | None = None, standing: str = VERIFIED, retest: dict | None = None,
               carried: list | None = None) -> Path:
    name = f"{slice_id}-{tip[:8]}" + ("-after-" + "-".join(before) if before else "") + \
        (f"-without-{retest['without']}" if retest else "")
    path = c.REPO / NOTES_REL / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(scrub(note_text(slice_id, tip, data, headline, why, jid, standing, retest, carried), s))
    record_run(slice_id, tip, jid, data, standing)
    return path


def expected_checks(tree: str) -> list[str]:
    """Every target `make -k ci` runs on this candidate (core-check as Core's check targets) and make test: read from
    the candidate tree's own Makefiles, here, never from the server's answer."""
    build = c.git(["show", f"{tree}:{named_lists.BUILD_MAKEFILE}"], c.REPO)
    core = c.git(["show", f"{tree}:{named_lists.CORE_MAKEFILE}"], c.REPO)
    names = [x for x in named_lists.prerequisites(build, "ci") if x != "core-check"]
    names += named_lists.prerequisites(core, "check")
    return names + ["test"]


def trust(s: dict, jid: str, slice_id: str, tip: str, tree: str) -> tuple[int, dict]:
    """Whether the server's run `jid` proves the candidate `tree` for `slice_id` at `tip` (009, item 3), asked of the
    server itself over the forced command, never read from a note. (exit code, the answer)."""
    said = {"trusted": False, "run_id": jid, "slice": slice_id, "tip": tip, "tree": tree}
    code, data = ssh(s, ["result", jid], timeout=120)
    if data is None:
        return NO_RESULT, {**said, "why": f"the server could not be reached or gave no answer (ssh exit {code})"}
    why = None
    checks = {x.get("name"): x for x in data.get("checks") or [] if isinstance(x, dict)}
    if data.get("state") != "done" or data.get("id") != jid:
        why = f"the server holds no finished run {jid} (it says: {data.get('state', '?')})"
    elif data.get("runner_version") not in TRUSTED_VERSIONS:
        why = f"run {jid} is by runner {data.get('runner_version', 'unknown')}, which records no check per target"
    elif data.get("slice") != slice_id or data.get("tip") != tip:
        why = f"run {jid} tested {data.get('slice')} at {str(data.get('tip'))[:10]}, not {slice_id} at {tip[:10]}"
    elif data.get("tree") != tree:
        why = f"run {jid} tested tree {str(data.get('tree'))[:12]}, not this candidate's {tree[:12]}"
    elif data.get("verdict") != "pass":
        why = f"run {jid}'s verdict is {data.get('verdict')}, not pass"
    elif data.get("list_drift"):
        why = "the server's named lists did not match the candidate: " + "; ".join(map(str, data["list_drift"]))[:300]
    else:
        try:
            want = expected_checks(tree)
        except RuntimeError:
            want = None
        if want is None:
            why = f"this machine cannot read the candidate tree {tree[:12]}'s Makefiles"
        else:
            missing = [n for n in want if n not in checks]
            failed = [n for n, x in checks.items() if x.get("status") not in ("passed", "not run")]
            if missing:
                why = "the result does not say what became of " + ", ".join(missing)
            elif failed:
                why = "these checks did not pass: " + ", ".join(failed)
            elif checks["test"].get("status") != "passed":
                why = "make test did not pass on the server"
    if not why:  # only a verified slice's run can count (013, 1): a held one is held, whatever the server says
        try:
            _, now_tip, standing, _ = standing_of(slice_id)
            if standing != VERIFIED or now_tip != tip:
                why = (f"{slice_id} is {standing} at {now_tip[:10]}: only a verified slice's run, for its exact tip "
                       "and tree, can count")
        except Refused as e:
            why = f"not a slice whose run can count: {e}"
    nr = data.get("not_run") or {}
    mac = {"targets": sorted({n for n, x in checks.items() if x.get("status") == "not run"} | {"client-name-check"}),
           "test_files": [x.get("name") for x in nr.get("test_files", [])],
           "docker_guarded_test_files": list(nr.get("docker_skipped", [])),
           "mac_only": [x.get("name") for x in nr.get("mac_only", [])],
           "live_step": True}
    said.update(main=data.get("main"), stack=data.get("stack"), seconds=data.get("seconds"),
                passed=sorted(n for n, x in checks.items() if x.get("status") == "passed"), mac_must_run=mac)
    if why:
        return RED, {**said, "why": why}
    return GREEN, {**said, "trusted": True,
                   "why": "the server ran this exact tree and every check it could run passed; the Mac runs the rest"}


def run_stack(s: dict, order: list, again: bool = False) -> int:
    """009's stack: one bundle, one command, then each candidate's note. 013, item 3: when one candidate is red, the
    slices above it are tested again at once without it (main + the ones below + the ones above), and again if one of
    those is red, so one bad slice does not cost the ones behind it a whole run each. Each such result is its own
    note, naming the stack it was tested in and the one that was left out."""
    found = [(sid, *standing_of(sid)[:3]) for sid in order]
    for sid in order:
        review_held(sid)
    finals, without, prev, earlier = {}, [], "", False
    if not again:  # never sent twice: no candidate of the request is sent again while a run of it has a verdict on this main. The
        # retests below are this request's own (013, 3, the owner's ruling: the ones below a red are run again as the
        # base of the ones above), so they are not looked at again
        found, left, finals = answered_members(s, found, current_main())
        if left:
            without, prev, earlier = [sid for sid, _ in left], left[-1][1], True
        if not found:
            return max(finals.values())
    while True:
        results = one_stack(s, found, without, prev, earlier)
        finals.update({sid: r[0] for sid, r in results.items()})
        red = next((k for k, (sid, *_) in enumerate(found) if results.get(sid, (GREEN, ""))[0] == RED), None)
        stack_id = next((r[1] for r in results.values() if r[1]), "")
        if red is None or red == len(found) - 1 or not stack_id:
            return max(finals.values())
        without, prev, earlier = without + [found[red][0]], stack_id, False
        found = found[:red] + found[red + 1:]
        print(scrub(f"Tested again at once without {without[-1]}, which was red in stack {prev}: "
                    + ", ".join(sid for sid, *_ in found[red:]), s))


def answered_members(s: dict, found: list, main: str) -> tuple[list, list, dict]:
    """Never sent twice: the request's members less those whose own candidate already has a verdict on this main: (the members
    still to send, [(each one left out as red or in conflict, its run id)], {each one not sent: that run's exit code}).
    The lowest red one is left out first, and the candidates above it change, so they are looked at again. Then the
    ones with a verdict at the top are not sent, from the top down. A green one others still stand on is Refused,
    unless --again."""
    left, finals, seen = [], {}, {}

    def hit(k):
        sid, _, tip, _ = found[k]
        key = (sid, tip, tuple((x, t) for x, _, t, _ in found[:k]))
        if key not in seen:
            seen[key] = answered(s, sid, tip, list(key[2]), main)
        return seen[key]

    while True:
        hits = [hit(k) for k in range(len(found))]
        red = next((k for k, h in enumerate(hits) if h and h[1]["verdict"] in ("fail", "conflict")), None)
        if red is None:
            break
        sid, _, tip, _ = found[red]
        finals[sid] = not_again(sid, tip, *hits[red], s)
        left.append((sid, hits[red][0]))
        found = found[:red] + found[red + 1:]
    while found and hits[len(found) - 1]:
        sid, _, tip, _ = found[-1]
        finals[sid] = not_again(sid, tip, *hits[len(found) - 1], s)
        found = found[:-1]
    under = next((k for k in range(len(found)) if hits[k]), None)
    if under is not None:
        sid, jid = found[under][0], hits[under][0]
        above = ", ".join(x for x, *_ in found[under + 1:])
        raise Refused(f"{sid} is green on this main in run {jid}, and {above} stand on it: a stack would test it "
                      "again. Send it with --again, or the ones above once it has merged.")
    return found, left, finals


def start_when_free(s: dict, branches, order: list | None) -> tuple[str, dict | None, int]:
    """start(), asked again while the runner is busy, up to the setting's wait: a retest waits for its slots."""
    deadline = time.monotonic() + s["max_wait_minutes"] * 60
    while True:
        state, sent, code = start(s, branches, order)
        if state == "started" or not (sent and sent.get("state") == "refused" and sent.get("reason") == "busy") \
                or time.monotonic() + s["poll_seconds"] > deadline:
            return state, sent, code
        time.sleep(s["poll_seconds"])


def one_stack(s: dict, found: list, without: list, prev_stack: str, earlier: bool = False) -> dict:
    """One stack (or, with one slice left, one run): {slice: (exit code, the stack's or run's id, "" if none)}.
    `earlier`: the last one left out had a verdict of red before this request, and was not sent again."""
    order = [sid for sid, *_ in found]
    retest = {"without": "-".join(without), "stack_id": prev_stack, **({"earlier": True} if earlier else {})} \
        if without else None
    if len(found) == 1:
        sid, branch, tip, standing = found[0]
        state, sent, code = start_when_free(s, branch, None) if retest else start(s, branch)
    else:
        state, sent, code = (start_when_free if retest else start)(s, [b for _, b, _, _ in found], order)
    if state != "started":
        headline, exit_code, why = outcome(sent, code)
        for k, (sid, _, tip, standing) in enumerate(found):
            path = write_note(sid, tip, sent, headline, why, "", s, order[:k], standing, retest)
            print(scrub(f"{sid}: {headline}: {why}. Note: {path}", s))
        return {sid: (exit_code, "") for sid, *_ in found}
    if len(found) == 1:
        jid = str(sent["id"])
        mark_running(sid, tip, jid, "", standing)
        try:
            data, code = poll(s, jid)
        finally:
            unmark_running(sid, tip)
        if data and data.get("state") == "done" and data.get("tip") != tip:
            data = {"state": "unknown"}
        headline, exit_code, why = outcome(data, code)
        path = write_note(sid, tip, data, headline, why, jid, s, None, standing, retest)
        print(scrub(f"{sid}: {headline}: {why}. Note: {path}", s))
        return {sid: (exit_code, jid)}
    ids = list(sent.get("ids") or [])
    stack_id = str(sent.get("id") or "")
    for k, (sid, _, tip, standing) in enumerate(found):
        mark_running(sid, tip, ids[k] if k < len(ids) else "", stack_id, standing)
    try:
        poll(s, stack_id)  # the stack's one result, until it is no longer running
        return stack_notes(s, found, ids, stack_id, order, retest)
    finally:
        for sid, _, tip, _ in found:
            unmark_running(sid, tip)


def stack_notes(s: dict, found: list, ids: list, stack_id: str, order: list, retest: dict | None = None) -> dict:
    results, below = {}, []
    for k, (sid, _, tip, standing) in enumerate(found):
        jid = ids[k] if k < len(ids) else ""
        code, data = ssh(s, ["result", jid], timeout=120) if jid else (255, None)
        if data and data.get("state") == "done" and re.fullmatch(r"[0-9a-f]{40}", str(data.get("holds_main", ""))):
            OWN.mkdir(parents=True, exist_ok=True)
            c.write_json(HELD, {"main": data["holds_main"], "at": c.now()})
        want = [{"slice": x, "tip": t} for x, _, t, _ in found[:k + 1]]
        if data and data.get("state") == "done" and (data.get("tip") != tip or data.get("stack") != want):
            data = {"state": "unknown"}  # an answer for another candidate is no answer for this one
        headline, exit_code, why = outcome(data, code)
        mine = failures_of(data) if headline == "RED" else set()
        carried = [b for b, fs in below if fs & mine] if mine and mine <= set().union(*[fs for _, fs in below]) \
            else []
        path = write_note(sid, tip, data, headline, why, jid, s, order[:k], standing, retest, carried)
        print(scrub(f"{sid}: {headline}: {why}. Note: {path}", s))
        results[sid] = (exit_code, stack_id)
        below.append((sid, mine))
    return results


def ask_cmd(argv: list) -> int:
    """`early_warning.py ask ports|ollama|shield`: the runner's own answer line, unchanged."""
    if len(argv) != 2 or argv[1] not in ("ports", "ollama", "shield"):
        print("Refused: ask takes one of ports, ollama, shield.", file=sys.stderr)
        return REFUSED_HERE
    try:
        s = load_setting()
    except Refused as e:
        print(f"Refused: {e}", file=sys.stderr)
        return REFUSED_HERE
    LAST_LINE[0] = ""
    code, data = ssh(s, ["ask", argv[1]], timeout=120)
    if data is None:
        print(f"No answer: the server could not be reached or gave no answer (ssh exit {code}).", file=sys.stderr)
        return NO_RESULT
    print(LAST_LINE[0])
    return REFUSED_THERE if data.get("state") != "done" else GREEN  # REFUSED_THERE: the runner refused it


def fetch(argv: list) -> int:
    """`early_warning.py fetch <id>` (012 a): the runner's own result line for that run, unchanged, from the server.
    `early_warning.py summary <id>` (010): the same for the server's summary of a red run."""
    if len(argv) != 2 or not re.fullmatch(proto.ID_PATTERN, argv[1]):
        print(f"Refused: {argv[0]} takes one run id ({proto.ID_LENGTH} lower-case hexadecimal characters).",
              file=sys.stderr)
        return REFUSED_HERE
    try:
        s = load_setting()
    except Refused as e:
        print(f"Refused: {e}", file=sys.stderr)
        return REFUSED_HERE
    LAST_LINE[0] = ""
    code, data = ssh(s, ["result" if argv[0] == "fetch" else "summary", argv[1]], timeout=120)
    if data is None:
        print(f"No answer: the server could not be reached or gave no answer (ssh exit {code}).", file=sys.stderr)
        return NO_RESULT
    if data.get("state") == "unknown":
        print(LAST_LINE[0])
        return REFUSED_THERE  # the server holds no such run
    print(LAST_LINE[0])
    return GREEN


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    # the owner, 25 November 2026: a long run says it is still running; its words name the slices only, never a setting
    words = "early_warning.py " + " ".join(x for x in argv if re.fullmatch(r"[A-Za-z0-9]+", x))[:120]
    with c.heartbeat(words.strip()):
        return _main(argv)


def _main(argv: list[str]) -> int:
    if argv[:1] in (["fetch"], ["summary"]):
        return fetch(argv)
    if argv[:1] == ["standing"]:
        return standing_cmd(argv)
    if argv[:1] == ["ask"]:
        return ask_cmd(argv)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slices", nargs="+", metavar="slice")
    ap.add_argument("--result", metavar="ID", help="poll a run already started")
    ap.add_argument("--trust", metavar="ID", help="for the merge: does the server's run ID prove --tree?")
    ap.add_argument("--tree", metavar="HASH", help="the candidate tree the merge built (with --trust)")
    ap.add_argument("--on-train", action="store_true",
                    help="send it on main plus the train in flight (its gated commit), not on main")
    ap.add_argument("--again", action="store_true",
                    help="send it even though a run of the same candidate has a verdict on this main")
    a = ap.parse_args(argv)
    s: dict = {}
    global ON_TRAIN
    try:
        if not all(re.fullmatch(proto.SLICE_PATTERN, x) for x in a.slices):
            raise Refused("A slice id is letters and digits only.")
        if len(a.slices) > proto.MAX_STACK or len(set(a.slices)) != len(a.slices):
            raise Refused(f"A stack is two to {proto.MAX_STACK} different slices, in merge order.")
        if len(a.slices) > 1 and (a.result or a.trust):
            raise Refused("--result and --trust take one slice.")
        for v in (a.result, None if a.trust == "auto" else a.trust):
            if v is not None and not re.fullmatch(proto.ID_PATTERN, v):
                raise Refused(f"A run id is {proto.ID_LENGTH} lower-case hexadecimal characters.")
        if (a.trust is None) != (a.tree is None) or (a.tree is not None and not re.fullmatch(r"[0-9a-f]{40}", a.tree)):
            raise Refused("--trust <id> goes with --tree <the candidate's 40-character tree hash>.")
        if a.on_train:  # 65: before the setting is read, so a stack on no train is refused as that, whatever the setting
            if a.result or a.trust:
                raise Refused("--on-train sends a slice or a stack; --result and --trust send nothing.")
            t = train_base(a.slices)
            ON_TRAIN = t["gated"]
            print(f"On main plus the train {t.get('train')} ({', '.join(t.get('parts') or [])}): its gated commit "
                  f"{ON_TRAIN[:10]} is this run's main.")
        s = load_setting()
        if a.trust:
            frozen = c.read_json(c.rec_dir(a.slices[0]) / "frozen.json") or {}
            tip = c.git(["rev-parse", "--verify", "-q", f"refs/heads/{frozen.get('branch', '')}"], c.REPO,
                        check=False) if frozen.get("branch") else ""
            if not tip:
                raise Refused(f"{a.slices[0]} has no branch in its records.")
            ids = recorded_runs(a.slices[0], tip, a.tree) if a.trust == "auto" else [a.trust]
            code, said = RED, {"trusted": False, "slice": a.slices[0], "tip": tip, "tree": a.tree,
                               "why": f"no run of {a.slices[0]} at {tip[:10]} is recorded here"}
            for jid in ids:
                code, said = trust(s, jid, a.slices[0], tip, a.tree)
            print(scrub(json.dumps(said, indent=1, sort_keys=True), s))
            return code
        if a.again and (a.result or a.trust):
            raise Refused("--again sends a slice; --result and --trust send nothing.")
        if len(a.slices) > 1:
            return run_stack(s, a.slices, a.again)
        a.slice = a.slices[0]
        review_held(a.slice)
        branch, tip, standing, _ = standing_of(a.slice)
        hit = None if a.result or a.again else answered(s, a.slice, tip, [], current_main())
        if hit:
            return not_again(a.slice, tip, *hit, s)
    except Refused as e:
        print(f"Refused: {e}", file=sys.stderr)
        return REFUSED_HERE
    if a.result:
        jid, sent = a.result, None
    else:
        state, sent, code = start(s, branch)
        try:  # 017: at the same moment; its result never comes back here, and its failure never stops this one
            built = send_checks(a.slice, branch, tip)
        except Exception as e:  # noqa: BLE001
            built = f"not sent (the send failed: {type(e).__name__})"
        print("Build checks: " + built)
        if state != "started":
            headline, exit_code, why = outcome(sent, code)
            path = write_note(a.slice, tip, sent, headline, why, "", s, None, standing)
            print(scrub(f"{headline}: {why}. Note: {path}", s))
            return exit_code
        jid = sent["id"]
    mark_running(a.slice, tip, jid, "", standing)
    try:
        data, code = poll(s, jid)
    finally:
        unmark_running(a.slice, tip)
    if data and data.get("state") == "done" and re.fullmatch(r"[0-9a-f]{40}", str(data.get("holds_main", ""))):
        OWN.mkdir(parents=True, exist_ok=True)
        c.write_json(HELD, {"main": data["holds_main"], "at": c.now()})
    if data and data.get("state") == "done" and data.get("tip") != tip:
        data = {"state": "unknown"}  # an answer for another tip is no answer for this one
    headline, exit_code, why = outcome(data, code)
    path = write_note(a.slice, tip, data, headline, why, jid, s, None, standing)
    print(scrub(f"{headline}: {why}. Note: {path}", s))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
