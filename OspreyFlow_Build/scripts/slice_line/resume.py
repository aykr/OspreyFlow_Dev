#!/usr/bin/env python3
"""Return a stopped or refused slice to its builder (process/lanes/v062/slice-line/README.md, "Resuming a slice").

    resume.py <slice> <action>     run by the conductor, whole and unchained (the guard refuses it to every other seat)

  refreeze         commits slices.tsv (that slice's frozen columns, nothing else) and refreezes it     owner's line
  add-round        a slice stopped at its rounds limit gets one more round                             owner's line
  clear-stop       a slice stopped on red checks: its red-stop records removed, back to building       owner's line
  send-back        a slice the merge gate refused goes back with the gate's findings, its round        none within the
                   advanced (past its rounds limit it needs the owner's add-round line as well, or     limit
                   his standing permission, standing.tsv: round-after-refusal per-day <N> <date>:     (or his standing
                   one round for the refusal's named cause alone, once; never the same cause twice,   permission past
                   a finding naming a key, a credential or a security rule, a slice stopped for red   it)
                   checks or one he has parked (`<slice> park <date>` in resume.tsv); N a day)
                   a verified slice goes back too, on the owner's send-back line only (a finding the  owner's line
                   owner does not accept narrower), its round advanced; past the limit the add-round  (and add-round
                   line as well. A findings record newer than the tip's pass tells the builder why    past the limit)
  correct-command  the conductor's own malformed command, corrected and proved on main (ruling 3)      none: the code
                                                                                                        holds the limits
  accept           a slice stopped at its rounds limit with a verifier's findings for its exact tip    owner's line
                   is merged narrower: an acceptance record for that tip, phase verified (the merge
                   script takes it in place of the verifier's pass, for that tip only). Without a
                   line, the owner's standing line (standing.tsv: accept-test-gaps from-round N         or the owner's
                   <date>) accepts a slice at round N or later whose newest findings record is the     standing line
                   verifier's for its tip and holds only gaps in a test; run_seat.py tries it after
                   each verifier record with findings
  move-seat <builder|verifier> <account>                                                        owner's line:
                   a started slice's seat moves to another account the owner's accounts.yaml names,   <ID> move-seat
                   signed in and not stopped, while none of its seats runs: state.json's account or  <seat> <account>
                   verifier_account is rewritten, and nothing else (no record, finding or round)      <YYYY-MM-DD>
  undo-seat-failure  a verifier call that was refused, written before seat failures existed as the    owner's line
                   finding "no verdict returned" (CO2, 19 November 2026): the record becomes a
                   seat_failure record, the round goes back by one, the phase to verifying
  self-clear       the line clears a stop itself (LINE_FIXES_5_BRIEF.md, A), when its cause is       none: the code
                   (b) a check the slice did not write that fails identically on main's own tree in    holds the limits;
                   the same worktree shape (the check is removed from the slice's row, recorded),     run_seat.py tries
                   or (a) main having moved under the slice (main merges into the branch cleanly and   it after a red stop
                   the slice's own acceptance and checks are unchanged), or (c) a red stop that is the
                   scan map's alone, whose rows main now has (the conductor wrote them since). Only on
                   the owner's standing permission (standing.tsv: clear-line-stops per-day <N> <date>),
                   N a day (his file 012, A2). Never: an accept, a refreeze that changes what is
                   tested, a stop naming a key, a credential or a security rule, a stop at the eighth
                   round, a stop on a verifier's findings, any red in the slice's own acceptance or its
                   own tests (its acceptance, its uncommitted work, its lint, a test it wrote or
                   changed), a slice the owner has parked. Each clearance is logged (self-clear-<time>
                   .json in the slice's folder, with the red stop's lines; self-clears.tsv, which the
                   board prints for the conductor's morning report; owner-changes.tsv, which the
                   budget counts)

Every action takes the merge lock (no merge runs meanwhile), refuses a worktree with uncommitted changes (one agent
per worktree), brings main's RULINGS.md into the worktree as an untracked, ignored copy (never a commit on the
slice's branch), and, when the branch conflicts with main only in the records folder, merges main into it, taking
main's records, and sends the slice for a fresh check. Nothing is changed on any refusal.

The owner's word is a line in resume.tsv (`<slice> <action> <YYYY-MM-DD>`, today in UTC), a file only the owner can
write: one line, one use, each use logged in owner-changes.tsv in the data folder. RULINGS.md is never the authority:
the conductor writes it.
"""
from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402
import dry_run  # noqa: E402
import merge_slice as ms  # noqa: E402
import run_seat as rs  # noqa: E402

ACTIONS = ("refreeze", "add-round", "clear-stop", "send-back", "correct-command", "accept", "move-seat",
           "undo-seat-failure", "self-clear")
#: What run_seat.py wrote, before 1f, for a verifier session whose call was refused (CO2, 19 November 2026).
NO_VERDICT = "no verdict returned"
#: The seat move-seat moves, and the key of state.json run_seat.py reads its account from.
SEAT_KEYS = {"builder": "account", "verifier": "verifier_account"}
OWNER_ACTIONS = ("refreeze", "add-round", "clear-stop", "accept")
#: What a corrected command may not add: anything that changes what a check tests rather than how it is run.
LOOSENING = ("||", "; true", "exit 0", " -k ", "--deselect", "--ignore", "--grep", " -t ", "--passWithNoTests", "skip",
             "xfail", "set +e", "--last-failed", "--lf", "--testNamePattern", "--only")
TEST_FILE = re.compile(r"[\w./-]*(?:test_[\w-]+\.py|[\w-]+_test\.py|[\w.-]+\.(?:test|spec)\.[cm]?[jt]sx?)(?:::[\w\[\]-]+)?")


class Refused(Exception):
    pass


class Busy(Refused):
    """Refused by a lock alone (a merge whose record names no slice or names this one, or another resume.py action on
    the slice): nothing about the action is wrong, and it can be tried again when the lock frees."""


def today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


# ------------------------------------------------------------------ the owner's word


def resume_lines() -> list[list[str]]:
    """The owner's lines in resume.tsv, each split into its words; comments left out."""
    if not c.RESUME_FILE.is_file():
        return []
    return [ln.split() for ln in c.RESUME_FILE.read_text().splitlines() if ln.strip() and not ln.strip().startswith("#")]


def owner_lines(slice_id: str, action: str) -> int:
    """How many of the owner's lines in resume.tsv name this slice and action today."""
    return sum(1 for parts in resume_lines() if parts == [slice_id, action, today()])


def authority(slice_id: str, action: str) -> str:
    """The owner's unused line for this slice, action and day, as the log names it; refused when there is none."""
    have = owner_lines(slice_id, action)
    tag = f"resume.tsv {today()}"
    used = sum(1 for r in c.owner_changes() if r["slice"] == slice_id and r["detail"].startswith(f"{tag} {action}:"))
    if not have:
        raise Refused(f"no line '{slice_id}\t{action}\t{today()}' in {c.RESUME_FILE} (the owner's word, today, UTC): "
                      "nothing changed.")
    if used >= have:
        raise Refused(f"the owner's line '{slice_id}\t{action}\t{today()}' in resume.tsv is already used ({used} use(s) "
                      "logged in owner-changes.tsv): one line, one use. Nothing changed.")
    return f"{tag} {action}"


# ------------------------------------------------------------------ the worktree


def frozen_of(slice_id: str) -> dict:
    frozen = c.read_json(c.rec_dir(slice_id) / "frozen.json")
    if not frozen:
        raise Refused(f"{slice_id} has not started (no frozen record).")
    if c.read_json(c.rec_dir(slice_id) / "merged.json"):
        raise Refused(f"{slice_id} is merged.")
    return frozen


def clean_worktree(frozen: dict) -> Path:
    wt = Path(frozen["worktree"])
    if not wt.is_dir():
        raise Refused(f"the slice's worktree {wt} is not there.")
    dirty = [ln for ln in c.git(["status", "--porcelain"], wt).splitlines()
             if not ln[3:].startswith(("OspreyFlow_Core/osprey.yaml", "OspreyFlow_Core/data/"))]
    if dirty:
        raise Refused(f"the worktree {wt} has uncommitted changes (one agent per worktree: is a builder still at "
                      "work there?): " + "; ".join(dirty[:5]))
    return wt


def conflicts_with_main(wt: Path) -> list[str] | None:
    """The files the branch conflicts with main in (empty when it merges cleanly); None when git cannot say."""
    p = subprocess.run(["git", "merge-tree", "--write-tree", "--name-only", "--no-messages", "main", "HEAD"],
                       cwd=str(wt), capture_output=True, text=True)
    if p.returncode not in (0, 1):
        return None
    return [ln for ln in p.stdout.splitlines()[1:] if ln.strip()]


def bring_main(slice_id: str, wt: Path) -> str:
    """Merge main into a branch whose only conflicts are in the records folder, taking main's records. What was done."""
    files = conflicts_with_main(wt)
    if not files:
        return ""
    outside = [f for f in files if not f.startswith(c.V062_REL + "/")]
    if outside:
        return ("the branch conflicts with main outside the records folder (" + ", ".join(outside[:5]) +
                "): left to the builder, who merges or rebases it.")
    old = c.git(["rev-parse", "HEAD"], wt)
    msg = f"merge: main into lane for slice {slice_id}, taking main's records ({', '.join(files)})"
    if subprocess.run(["git", "merge", "--no-edit", "-m", msg, "main"], cwd=str(wt), capture_output=True).returncode != 0:
        unmerged = c.git(["diff", "--name-only", "--diff-filter=U"], wt).splitlines()
        if any(not f.startswith(c.V062_REL + "/") for f in unmerged):
            c.git(["merge", "--abort"], wt, check=False)
            return "merging main met conflicts outside the records folder: undone, left to the builder."
        c.git(["checkout", "--theirs", "--", *unmerged], wt)
        c.git(["add", "--", *unmerged], wt)
        c.git(["commit", "--no-edit", "-q"], wt)
    if any(c.git(["diff", "main", "HEAD", "--", f], wt) for f in files):
        c.git(["reset", "-q", "--hard", old], wt)
        raise Refused("after merging main the records folder is not main's: undone, nothing changed.")
    tip = c.git(["rev-parse", "HEAD"], wt)
    finding = {"file": files[0],
               "what": ("Main has been merged into this branch, taking main's text for the records folder, where the "
                        "branch had fallen behind (" + ", ".join(files) + "). Change nothing else. Run the checks and "
                        "the acceptance command; if either is red, the cause is in what main brought in."),
               "evidence": f"git log -1 shows the merge commit {tip[:10]}; the records folder equals main's."}
    c.write_json(c.rec_dir(slice_id) / f"verify-gate-{tip}.json",
                 {"slice": slice_id, "commit": tip, "verdict": "findings", "passes": [], "findings": [finding],
                  "note": "written by resume.py after merging main into the branch; not a verifier session", "at": c.now()})
    return f"main merged into the branch ({old[:10]} -> {tip[:10]}), taking main's records: a fresh check is needed."


def back_to_building(slice_id: str, wt: Path, **kw) -> list[str]:
    said = []
    merged = bring_main(slice_id, wt)
    if merged:
        said.append(merged)
    st = c.state(slice_id)
    st.pop("note", None)
    st.update(kw, phase="building", updated=c.now())
    c.write_json(c.rec_dir(slice_id) / "state.json", st)
    copy = c.deliver_rulings(wt)
    said.append(f"main's rulings are at {copy}" if copy else "main's rulings could not be copied into the worktree")
    return said


def send_back_verified(slice_id: str, wt: Path, st: dict, rnd: int, limit: int) -> list[str]:
    """A verified slice back to its builder, on the owner's line `<slice> send-back <date>` alone (22 November 2026,
    SE9: a finding the owner does not accept narrower, at a tip a second verifier passed). The round advances by one.
    The line does not raise the rounds limit: past it, the owner's add-round line is needed as well, as for a refused
    slice's send-back, and both are used. Neither line is used on a refusal. The builder is told why it is back by a
    findings record newer than the tip's pass (verify-gate-*, the line's own records, never a verifier's)."""
    try:
        tag = authority(slice_id, "send-back")
    except Refused as e:
        raise Refused(f"{slice_id} is verified, not refused by the merge gate: a verified slice goes back only on the "
                      f"owner's line. {e}") from None
    more = None
    if rnd >= limit:
        try:
            more = authority(slice_id, "add-round")
        except Refused as e:
            raise Refused(f"{slice_id} is at its rounds limit (round {rnd} of {limit}): the owner's send-back line "
                          f"does not raise it; the add-round line does. {e} The send-back line is not used.") from None
    new_round, new_limit = rnd + 1, limit + (1 if more else 0)
    tip = st.get("tip") or c.git(["rev-parse", "HEAD"], wt)
    said = back_to_building(slice_id, wt, round=new_round, rounds_limit=new_limit)
    table = f"{c.V062_REL}/slices/{slice_id}_ROUND{new_round}_TABLE.md"
    finding = {"file": table if new_round >= c.TABLE_ROUND else f"{c.V062_REL}/slices/{slice_id}.md",
               "what": (f"This slice was verified at {tip[:10]} and sent back by the owner (resume.tsv, {today()}): a "
                        "finding at that tip stands that the owner does not accept narrower, whatever a verifier's "
                        "pass said. This round's work is " +
                        (f"in the scout's table for round {new_round} ({table})." if new_round >= c.TABLE_ROUND else
                         "in the brief and in what the conductor gives you from the owner.")),
               "evidence": f"owner-changes.tsv: {tag}"}
    head = c.git(["rev-parse", "HEAD"], wt)
    f = c.rec_dir(slice_id) / f"verify-gate-{tip}.json"
    kept = [*((c.read_json(f) or {}).get("findings") or []),
            *(((c.read_json(c.rec_dir(slice_id) / f"verify-gate-{head}.json") or {}).get("findings") or [])
              if head != tip else [])]
    c.write_json(f, {"slice": slice_id, "commit": tip, "verdict": "findings", "passes": [], "findings": [finding, *kept],
                     "note": "written by resume.py: a verified slice sent back by the owner; not a verifier session",
                     "at": c.now()})
    c.log_owner_change(slice_id, "send-back", f"{tag}: a verified slice sent back at {tip[:10]}; round {rnd} -> "
                                              f"{new_round}" + ("" if more else f", limit {limit} unchanged"))
    if more:
        c.log_owner_change(slice_id, "send-back", f"{more}: past the limit; limit {limit} -> {new_limit}")
    if new_round >= c.TABLE_ROUND and not (c.REPO / table).is_file():
        said.append(f"no round from {c.TABLE_ROUND} on starts without its table: {table} is not on main yet.")
    return [f"{slice_id}: a verified slice back to the builder on the owner's line, round {new_round} of {new_limit}.",
            *said]


#: The owner's standing permission for one more round after a merge refusal (his file 012, A1; common.py).
RAR = "round-after-refusal"


def refusal_cause(rec: Path, tip: str) -> list[str]:
    """The refusal's cause as the gate recorded it: the file of each failing test or target its findings name, or []
    when a finding names none (a red with no name: the cause is not recorded)."""
    files = [str(f.get("file") or "").strip() for f in (c.read_json(rec / f"verify-gate-{tip}.json") or {}).get("findings") or []]
    return sorted(set(files)) if files and all(files) else []


def given_before(rec: Path) -> list[dict]:
    """Each round the permission gave this slice before, with the cause it was given for."""
    return [c.read_json(f) or {} for f in sorted(rec.glob(f"{RAR}-*.json"))]


def red_stopped(slice_id: str, rec: Path) -> str:
    """How the slice is known to have been stopped for red checks (the Stop hook's six red stops), or '': a red stop
    now, or one cleared by the owner's line, a corrected command or the line itself."""
    if (rec / "red_stop.json").exists():
        return "a red stop now"
    for r in c.owner_changes():
        if r["slice"] == slice_id and r["action"] in ("clear-stop", "correct-command"):
            return f"{r['action']} at {r['at']}"
    for r in c.self_clears():
        if r["slice"] == slice_id and r["stop"] == "red":
            return f"cleared by the line at {r['at']}"
    return ""


def round_after_refusal(slice_id: str, wt: Path, st: dict, rec: Path, rnd: int, limit: int, no_line: str) -> list[str]:
    """One more round past the rounds limit after a merge refusal, on the owner's standing permission (standing.tsv:
    round-after-refusal per-day <N> <date>) in place of his add-round line, to fix the refusal's named cause alone,
    once for that refusal. Never: the same cause a second time for the slice; a finding naming a key, a credential or
    a security rule; a slice stopped for red checks; a slice the owner has parked; past the day's budget. Refused in
    words, with nothing changed, otherwise."""
    tip = st.get("tip") or c.git(["rev-parse", "HEAD"], wt)

    def refuse(why: str):
        raise Refused(f"{no_line} The standing permission {RAR} does not give it: {why}. Nothing changed.")

    grant, why = c.standing_grant(RAR)
    if not grant:
        refuse(why)
    if c.parked(slice_id):
        refuse(f"the owner has parked {slice_id} ({c.parked(slice_id)} in resume.tsv)")
    red = red_stopped(slice_id, rec)
    if red:
        refuse(f"{slice_id} has been stopped for red checks ({red}): its rounds are the owner's")
    hit = SECURITY_WORDS.search(stop_words(st, rec, tip))  # the self-clear's word check, unchanged
    if hit:
        refuse(f"the refusal names a key, a credential or a security rule ({hit.group(0)!r} in its findings)")
    cause = refusal_cause(rec, tip)
    if not cause:
        refuse("the gate's record names no failing test or target for this refusal (its cause is not recorded)")
    for before in given_before(rec):
        same = sorted(set(before.get("cause") or []) & set(cause))
        if same:
            refuse(f"it gave {slice_id} a round for the same cause before ({', '.join(same)}, at {before.get('at')}): "
                   "a second time is the owner's")
    new_round, new_limit = rnd + 1, limit + 1
    said = back_to_building(slice_id, wt, rounds_limit=new_limit, round=new_round)
    named = ", ".join(cause)
    f = rec / f"verify-gate-{tip}.json"
    gate = c.read_json(f) or {}
    c.write_json(f, {**gate, "findings": [{
        "file": cause[0],
        "what": (f"This round ({new_round} of {new_limit}) is given by the owner's standing permission for this merge "
                 f"refusal alone ({RAR}): fix only the cause the gate names below ({named}) and change nothing else. "
                 "If the same cause is red again, the slice goes to the owner."),
        "evidence": f"owner-changes.tsv: standing.tsv {RAR}"}, *(gate.get("findings") or [])]})
    c.write_json(rec / f"{RAR}-{tip}.json", {"slice": slice_id, "tip": tip, "cause": cause, "round": new_round,
                                            "rounds_limit": new_limit, "at": c.now()})
    what = (f"one more round after the merge refusal at {tip[:10]}, for its named cause alone ({named}), without the "
            f"owner's add-round line; round {rnd} -> {new_round}, limit {limit} -> {new_limit}; use {grant['used'] + 1} "
            f"of {grant['per_day']} today")
    c.log_standing_use(slice_id, RAR, "send-back", "refused", RAR, what)
    return [f"{slice_id}: back to the builder on the owner's standing permission ({RAR}): {what}.", *said]


# ------------------------------------------------------------------ slices.tsv: one row's frozen columns


def changed_row(slice_id: str, allowed: tuple[str, ...], briefs_aside: bool = False) -> tuple[dict, dict]:
    """The slice's row on main and in the working copy, when the working copy differs from main in that row only, and
    there only in `allowed` columns; refused otherwise. `briefs_aside` (refreeze, 8.1): other uncommitted files under
    the slices folder (the conductor's briefs) stay as they are, uncommitted; only slices.tsv is committed."""
    branch = c.git(["rev-parse", "--abbrev-ref", "HEAD"], c.REPO)
    if branch != "main":
        raise Refused(f"the main checkout is not on main ({branch}).")
    dirty = [ln[3:] for ln in c.git(["status", "--porcelain", "--untracked-files=no"], c.REPO).splitlines()
             if not ln[3:].startswith(ms.OWNERS_LOCAL)
             and not (briefs_aside and ln[3:].startswith(f"{c.V062_REL}/slices/") and ln[:2].strip() == "M")]
    if dirty != [c.SLICES_REL]:
        raise Refused(f"the main checkout must differ from main in {c.SLICES_REL} alone (and the owner's own files): "
                      + (", ".join(dirty[:5]) or "nothing changed"))
    if c.git(["diff", "--cached", "--name-only"], c.REPO):
        raise Refused("something is already staged in the main checkout.")
    head = c.git(["show", f"HEAD:{c.SLICES_REL}"], c.REPO).splitlines()
    work = (c.REPO / c.SLICES_REL).read_text().splitlines()
    if len(head) != len(work):
        raise Refused(f"{c.SLICES_REL} adds or removes lines: only {slice_id}'s row may change.")
    diff = [i for i, (a, b) in enumerate(zip(head, work)) if a != b]
    if len(diff) != 1 or not head[diff[0]].startswith(slice_id + "\t") or not work[diff[0]].startswith(slice_id + "\t"):
        raise Refused(f"{c.SLICES_REL} must differ from main in {slice_id}'s row alone.")
    old, new = c.parse_slices(head[diff[0]])[0], c.parse_slices(work[diff[0]])[0]
    beyond = [k for k in c.COLUMNS if k not in allowed and old[k] != new[k]]
    if beyond:
        raise Refused(f"{slice_id}'s row changes {', '.join(beyond)}: only {', '.join(allowed)} may change here.")
    return old, new


def commit_row(slice_id: str, message: str) -> str:
    """slices.tsv committed alone in records mode, one commit at a time with every other (the records lock). While a
    merge of another slice runs (LINE_FIXES_5_BRIEF.md, 2) it is not pushed: the merge lands beneath its result and
    pushes it with the merge, as a records commit made meanwhile."""
    with ms.records_lock():
        c.git(["add", "--", c.SLICES_REL], c.REPO)
        staged = c.git(["diff", "--cached", "--name-only"], c.REPO).splitlines()
        if staged != [c.SLICES_REL]:
            c.git(["reset", "-q", "--", c.SLICES_REL], c.REPO)
            raise Refused("something besides slices.tsv would be committed: " + ", ".join(staged))
        c.git(["commit", "-q", "-m", f"{message}\n\nSlice-Records: yes"], c.REPO)
        sha = c.git(["rev-parse", "HEAD"], c.REPO)
    if MERGE_RUNNING is None:
        subprocess.run([str(Path(__file__).resolve().parent / "push_main.sh")], cwd=c.REPO, capture_output=True)
    return sha


# ------------------------------------------------------------------ correct-command's limits


def test_files(cmd: str) -> list[str]:
    out = []
    for m in TEST_FILE.finditer(cmd or ""):
        t = m.group(0)
        while t.startswith(("./", "../")):
            t = t[2:] if t.startswith("./") else t[3:]
        out.append(t)
    return sorted(out)


def same_tests(old: dict, new: dict) -> None:
    for k in ("acceptance", "checks"):
        a, b = test_files(old.get(k, "")), test_files(new.get(k, ""))
        if a != b:
            raise Refused(f"the corrected {k} names other test files than the old ({', '.join(a) or 'none'} -> "
                          f"{', '.join(b) or 'none'}): a correction never changes what a check tests.")
        for marker in LOOSENING:
            if (new.get(k) or "").count(marker) > (old.get(k) or "").count(marker):
                raise Refused(f"the corrected {k} adds {marker.strip()!r}, which changes what a check tests.")


def only_malformed(slice_id: str) -> str:
    red = c.read_json(c.rec_dir(slice_id) / "red_stop.json")
    if not red:
        raise Refused(f"{slice_id} has no red-stop record: correct-command is for a slice the Stop hook stopped on its "
                      "own malformed command.")
    last = red.get("last") or []
    if not last:
        raise Refused("the red-stop record has no output to read.")
    whys = []
    for problem in last:
        why = dry_run.malformed(problem)
        if not why or dry_run.genuine(problem) or not problem.startswith(("RED: checks", "RED: acceptance")):
            raise Refused("the slice's last red is not only a malformed command (a failing test, uncommitted work, or "
                          "a failure no signature names): it needs the owner, not correct-command.\n" + problem[:600])
        whys.append(why)
    return "; ".join(sorted(set(whys)))


# ------------------------------------------------------------------ accept: what a verifier saw, at the exact tip


def findings_at_tip(slice_id: str, frozen: dict) -> tuple[str, dict]:
    """The branch's tip and the verifier's findings record for it, when the tip has the Stop hook's green test record
    and a verifier session that did not build it returned findings for exactly that commit; refused otherwise."""
    rec = c.rec_dir(slice_id)
    tip = c.git(["rev-parse", frozen["branch"]], c.REPO)
    tests = c.read_json(rec / f"tests-{tip}.json")
    if not (tests and tests.get("green") and tests.get("commit") == tip):
        raise Refused(f"the tip {tip[:10]} has no green test record (the Stop hook's): nothing a verifier saw is there "
                      "to accept. Nothing changed.")
    verify = c.read_json(rec / f"verify-{tip}.json")
    if not verify or verify.get("commit") != tip:
        raise Refused(f"no verifier record for the tip {tip[:10]}: the owner accepts what a verifier saw, at the tip "
                      "it saw, and the branch has moved since or was never verified. Nothing changed.")
    if verify.get("verdict") == "pass":
        raise Refused(f"the verifier passed {tip[:10]}: there is nothing to accept (merge_slice.py merge it). "
                      "Nothing changed.")
    if verify.get("verdict") != "findings" or not verify.get("findings"):
        raise Refused(f"the verifier's record for {tip[:10]} holds no findings ({verify.get('verdict')}). Nothing changed.")
    try:
        ms.verifier_sessions(slice_id, tip, verify)
    except ms.Refused as e:
        raise Refused(f"{e} Nothing changed.")
    return tip, verify


def newest_record_is(slice_id: str, tip: str) -> None:
    """The verifier's record for the tip is the newest findings record of the slice (no merge gate's or resume.py's
    record written after it); refused otherwise."""
    recs = sorted(c.rec_dir(slice_id).glob("verify-*.json"), key=lambda p: p.stat().st_mtime)
    if not recs or recs[-1].name != f"verify-{tip}.json":
        raise Refused(f"the newest findings record is {recs[-1].name if recs else 'none'}, not the verifier's for "
                      f"{tip[:10]}: an accept reads only the newest verifier record. Nothing changed.")


def before_the_limit(slice_id: str, phase: str, rnd: int, limit: int, tip: str, verify: dict, rec: Path) -> None:
    """The owner's accept before the rounds limit (the owner's word of 21 November 2026): the verifier's findings for
    the tip are on record (findings_at_tip), and it is refused, in words, while a seat of the slice is at work, when a
    newer record than the verifier's is the newest, and when the slice is stopped on red checks. A key or security
    finding is refused at any round (no_key_finding)."""
    if phase == "stopped" and (rec / "red_stop.json").exists():
        raise Refused(f"{slice_id} is stopped on red checks (red_stop.json), not on findings: there is no verifier "
                      "finding to accept (clear-stop or refreeze). Nothing changed.")
    for r in c.running_seats(slice_id):
        raise Refused(f"{slice_id}'s {r.get('seat')} is at work (pid {r.get('pid')}): the accept waits until its "
                      "session ends, and is refused if it commits (the tip it accepts must be the verifier's). Run it "
                      "again then. Nothing changed.")
    newest_record_is(slice_id, tip)


def no_key_finding(verify: dict) -> None:
    """The owner's word of 21 November 2026 (his file 003): a fault that can expose a key, show it back, log it or send
    it where it was not given is never accepted, at any round, on the standing word or on his own line."""
    hit = SECURITY_WORDS.search(" ".join(" ".join(str(f.get(k, "")) for k in ("file", "what", "evidence"))
                                         for f in verify["findings"]))
    if hit:
        raise Refused(f"a finding names a key, a credential or a security rule ({hit.group(0)!r}): the owner's accept "
                      "never covers one, at any round (his word of 21 November 2026). It needs the builder's fix. "
                      "Nothing changed.")


def only_gaps(findings: list[dict], legacy: bool) -> None:
    faults = [f for f in findings if rs.kind_of(f, legacy) == rs.FAULT]
    other = [f for f in findings if rs.kind_of(f, legacy) not in rs.KINDS]
    if faults or other:
        raise Refused(f"the verifier's findings are not only gaps in a test "
                      f"({rs.kinds_said(rs.kinds_of(findings, legacy))}): "
                      "a fault in behaviour, or a finding with no kind, is never accepted on the standing word. "
                      "It needs the owner's resume.tsv line (accept). Nothing changed.")


def write_acceptance(slice_id: str, tip: str, verify: dict, line: str, by: str, extra: dict | None = None) -> dict:
    """accepted-<tip>.json: the owner's line, the date, every finding verbatim, split by kind. Changes no finding."""
    findings = verify["findings"]
    legacy = rs.is_legacy(verify)
    split = {"faults_in_behaviour": [f for f in findings if rs.kind_of(f, legacy) == rs.FAULT],
             "gaps_in_a_test": [f for f in findings if rs.kind_of(f, legacy) == rs.GAP],
             "no_kind": [f for f in findings if rs.kind_of(f, legacy) is None]}
    acc = {"slice": slice_id, "tip": tip, "line": line, "date": today(), "by": by,
           "verifier_record": f"verify-{tip}.json", "findings": findings, **split,
           "kinds_read_from": "prefixes (a record written before the kind field)" if legacy else "the kind field",
           **(extra or {}), "at": c.now()}
    c.write_json(c.rec_dir(slice_id) / f"accepted-{tip}.json", acc)
    st = c.state(slice_id)
    st.pop("note", None)
    st.update(phase="verified", accepted=True, tip=tip, updated=c.now())
    c.write_json(c.rec_dir(slice_id) / "state.json", st)
    return acc


# ------------------------------------------------------------------ the actions


def standing_accept(slice_id: str, frozen: dict, st: dict, rec: Path) -> list[str]:
    """accept on the owner's standing line (standing.tsv), with no line per slice: refused in words unless it holds."""
    rule, why = c.standing_rule()
    if not rule:
        raise Refused(f"no line '{slice_id}\taccept\t{today()}' in {c.RESUME_FILE} (the owner's word, today, UTC), and "
                      f"no standing accept: {why}. Nothing changed.")
    phase, rnd = st.get("phase"), st.get("round", 1)
    if rnd < rule["from_round"]:
        raise Refused(f"{slice_id} is in round {rnd}: the owner's standing line ({rule['line']}) starts at round "
                      f"{rule['from_round']}. Nothing changed.")
    if not (phase == "verifying" or (phase == "stopped" and not (rec / "red_stop.json").exists())):
        raise Refused(f"{slice_id} is not waiting on its verifier's findings (phase {phase}). Nothing changed.")
    tip, verify = findings_at_tip(slice_id, frozen)
    newest_record_is(slice_id, tip)
    legacy = rs.is_legacy(verify)
    only_gaps(verify["findings"], legacy)
    hit = SECURITY_WORDS.search(" ".join(" ".join(str(f.get(k, "")) for k in ("file", "what", "evidence"))
                                         for f in verify["findings"]))
    if hit:  # LINE_FIXES_5_BRIEF.md, 3: a security or key finding is never covered by the standing word
        raise Refused(f"a finding names a key, a credential or a security rule ({hit.group(0)!r}): never accepted on "
                      "the standing word, gap or not. It needs the owner's resume.tsv line (accept). Nothing changed.")
    acc = write_acceptance(slice_id, tip, verify, rule["line"], "standing",
                           {"rule": f"standing.tsv: {rule['line']} (RULINGS.md, 19 November 2026, ruling 5: from a "
                                    "slice's third round on, a gap in a test never blocks)", "round": rnd})
    n = len(acc["findings"])
    c.log_owner_change(slice_id, "accept", f"standing (standing.tsv: {rule['line']}): tip {tip}; round {rnd}; {n} "
                                           "gaps in a test accepted, each for a backlog row")
    return [f"{slice_id}: accepted narrower at {tip[:10]} on the owner's standing line: {n} gaps in a test, each to "
            f"become a backlog row; verified. The conductor runs merge_slice.py merge {slice_id} and tells the owner."]


def move_seat(slice_id: str, args: list[str] | tuple[str, ...]) -> list[str]:
    """A started slice's builder or verifier seat moves to another account, on the owner's line `<ID> move-seat <seat>
    <account> <YYYY-MM-DD>` (LINE_FIXES_3_BRIEF.md, 1g). Rewrites that one key of state.json, nothing else. The
    builder and the verifier stay apart by session, not by account: the merge refuses a pass from a session that built
    the slice (merge_slice.verifier_sessions), on any account, and every launch is a new session."""
    if len(args) != 2 or args[0] not in SEAT_KEYS:
        raise Refused("move-seat takes the seat (builder or verifier) and the account: resume.py <ID> move-seat "
                      "<builder|verifier> <account>. Nothing changed.")
    seat, to = args
    key = SEAT_KEYS[seat]
    want = [slice_id, "move-seat", seat, to, today()]
    have = sum(1 for parts in resume_lines() if parts == want)
    tag = f"resume.tsv {today()} move-seat {seat} {to}"
    used = sum(1 for r in c.owner_changes()
               if r["slice"] == slice_id and r["action"] == "move-seat" and r["detail"].startswith(tag + ":"))
    if not have:
        raise Refused(f"no line '{chr(9).join(want)}' in {c.RESUME_FILE} (the owner's word, today, UTC): nothing "
                      "changed.")
    if used >= have:
        raise Refused(f"the owner's line '{chr(9).join(want)}' in resume.tsv is already used ({used} use(s) logged in "
                      "owner-changes.tsv): one line, one use. Nothing changed.")
    known = c.known_accounts()
    if to not in known:
        raise Refused(f"{to!r} is not an account the owner's accounts.yaml names ({', '.join(sorted(known))}). "
                      "Nothing changed.")
    st = c.state(slice_id)
    frm = st.get(key, "")
    if frm == to:
        raise Refused(f"{slice_id}'s {seat} is already on {to}. Nothing changed.")
    running = c.running_seats(slice_id)
    if running:
        raise Refused(f"a seat of {slice_id} is running (" + "; ".join(
            f"{r.get('seat')} on {r.get('account')}, pid {r.get('pid')}" for r in running) +
            "): a seat moves only between sessions. Nothing changed.")
    stop = c.account_stop(to)
    if stop:
        raise Refused(f"account {to} is stopped ({stop.get('error')} at {stop.get('at')}): the owner clears it first. "
                      "Nothing changed.")
    if not c.signed_in(to):
        raise Refused(f"account {to} is signed out: the owner signs in to it first. Nothing changed.")
    path = c.rec_dir(slice_id) / "state.json"
    raw = c.read_json(path) or {}
    raw[key] = to
    c.write_json(path, raw)
    c.log_owner_change(slice_id, "move-seat", f"{tag}: {seat} {frm or '(none)'} -> {to}")
    return [f"{slice_id}: its {seat} seat moves from {frm or '(none)'} to {to}; its phase, round and records are "
            f"unchanged ({st.get('phase')}, round {st.get('round', 1)})."]


def refused_results(rec: Path, session: str) -> list[dict]:
    """The result lines, in the slice's seat logs, of this session, when run_seat.py reads each as a seat failure."""
    out = []
    for f in sorted(rec.glob("verifier-*.jsonl")):
        for ln in f.read_text(errors="replace").splitlines():
            try:
                d = json.loads(ln)
            except ValueError:
                continue
            if isinstance(d, dict) and d.get("type") == "result" and d.get("session_id") == session \
                    and rs.seat_failure(d, wants_verdict=True):
                out.append(d)
    return out


def undo_seat_failure(slice_id: str, frozen: dict, st: dict, rec: Path) -> list[str]:
    """A verifier session whose call was refused, written before 1f as a findings record ("no verdict returned") that
    sent the slice back to its builder (CO2, 19 November 2026): the record becomes a seat_failure record, the round
    goes back by one and the phase to verifying, so the verifier runs again on the same tip. Only when every pass of
    the record is that line and the session's own stream shows its call refused; on the owner's line."""
    phase, rnd = st.get("phase"), st.get("round", 1)
    tip = c.git(["rev-parse", frozen["branch"]], c.REPO)
    vf = rec / f"verify-{tip}.json"
    v = c.read_json(vf)
    if phase != "building" or rnd < 2:
        raise Refused(f"{slice_id} was not sent back by a verifier record (phase {phase}, round {rnd}). Nothing changed.")
    if not v or v.get("commit") != tip or v.get("verdict") != "findings":
        raise Refused(f"no verifier findings record for the tip {tip[:10]}. Nothing changed.")
    passes = v.get("passes") or []
    if not passes or any([f.get("what") for f in (p.get("findings") or [])] != [NO_VERDICT] or p.get("commit")
                         for p in passes) or any(f.get("what") != NO_VERDICT for f in v.get("findings") or []):
        raise Refused(f"the verifier record for {tip[:10]} is not a refused call written as a finding: its findings "
                      f"are not only '{NO_VERDICT}'. A verifier's real findings are never undone. Nothing changed.")
    results = {}
    for p in passes:
        got = refused_results(rec, p.get("session", ""))
        if not got:
            raise Refused(f"the verifier session {str(p.get('session'))[:8]}'s stream shows no refused call (no result "
                          "line read as a seat failure): not a refused call. Nothing changed.")
        results[p["session"]] = got[-1]
    tests = c.read_json(rec / f"tests-{tip}.json")
    if not (tests and tests.get("green") and tests.get("commit") == tip):
        raise Refused(f"the tip {tip[:10]} has no green test record: the verifier cannot run on it. Nothing changed.")
    newest_record_is(slice_id, tip)
    tag = authority(slice_id, "undo-seat-failure")
    first = next(iter(results.values()))
    name = f"seat-failure-verifier-undone-{tip[:10]}.json"
    c.write_json(rec / name, {"kind": "seat_failure", "slice": slice_id, "seat": "verifier",
                              "account": passes[0].get("account"), "tip": tip, "error": rs.refusal_words(first),
                              "result": first, "results": results, "replaces": v, "line": tag, "at": c.now(),
                              "note": "a refused call that run_seat.py wrote as a finding before 1f; undone"})
    vf.unlink()
    st.pop("note", None)
    st.update(phase="verifying", round=rnd - 1, tip=tip, updated=c.now())
    c.write_json(rec / "state.json", st)
    c.log_owner_change(slice_id, "undo-seat-failure", f"{tag}: tip {tip}; verify-{tip[:10]}.json -> {name}; "
                                                      f"round {rnd} -> {rnd - 1}; building -> verifying")
    return [f"{slice_id}: the refused verifier call at {tip[:10]} is a seat failure, not a finding; round "
            f"{rnd - 1}, verifying. The conductor runs run_seat.py verifier {slice_id} once its account is clear."]


# ------------------------------------------------------------------ self-clear: the line clears a stop itself (A)


#: Any stop at this round or later is the owner's alone, whatever its cause (LINE_FIXES_5_BRIEF.md, A: "any stop at the
#: eighth round"; the balanced dial's 8 rounds, the owner, 21 November 2026).
OWNERS_ROUND = 8
#: A stop whose findings name a key, a credential or a security rule is never cleared by the line. Matched anywhere in a
#: word, in any case, on purpose: a word too many leaves the stop with the owner, as before; a word too few never can.
SECURITY_WORDS = re.compile(r"key|credential|secret|token|passw|security|secure|auth|oidc|cve|vulnerab|certificate|"
                            r"encrypt|signing|guard\.py|emails\.sha256|sha256", re.I)


def unapplied(slice_id: str, action: str) -> list[str]:
    """The owner's lines in resume.tsv for this slice and action, of any day, not yet used (no use logged)."""
    return list(dict.fromkeys(ln["text"] for ln in c.unapplied_lines() if ln["slice"] == slice_id and ln["action"] == action))


def stop_of(st: dict, rec: Path) -> str:
    """What stopped the slice: 'red' (the Stop hook's six red stops), 'findings' (the verifier's, at the rounds limit),
    'refused' (the merge gate), or '' (not stopped, or stopped for its account)."""
    phase = st.get("phase")
    if phase == "stopped" and (rec / "red_stop.json").exists():
        return "red"
    if phase == "stopped" and st.get("round", 1) >= st.get("rounds_limit", 1):
        return "findings"
    if phase == "refused":
        return "refused"
    return ""


def stop_words(st: dict, rec: Path, tip: str) -> str:
    """The stop's findings, in their own words: the red stop's failure lines (not the command it echoes), the
    verifier's and the gate's findings for the tip, and the stop's note."""
    parts = []
    for problem in (c.read_json(rec / "red_stop.json") or {}).get("last") or []:
        head, _, body = str(problem).partition("\n")
        parts.append(body if head.startswith(("RED: checks", "RED: acceptance", "RED: scans")) else str(problem))
    for name in (f"verify-{tip}.json", f"verify-gate-{tip}.json"):
        for f in (c.read_json(rec / name) or {}).get("findings") or []:
            parts.append(" ".join(str(f.get(k, "")) for k in ("file", "what", "evidence")))
    parts.append(str(st.get("note", "")))
    return "\n".join(parts)


def owners_alone(slice_id: str, frozen: dict, st: dict, rec: Path, stop: str, tip: str) -> None:
    """Refused, in words, when the stop is the owner's alone whatever its cause: the eighth round, a key or a security
    rule, a stop on a verifier's findings (a fault in behaviour, or open findings only the owner accepts), a refreeze
    that changes what is tested."""
    rnd = st.get("round", 1)
    if rnd >= OWNERS_ROUND:
        raise Refused(f"{slice_id} is in round {rnd}: any stop at the eighth round is the owner's alone. It waits for "
                      "the owner's line. Nothing changed.")
    hit = SECURITY_WORDS.search(stop_words(st, rec, tip))
    if hit:
        raise Refused(f"{slice_id}'s stop names a key, a credential or a security rule ({hit.group(0)!r} in its "
                      "findings): the line never clears it. It waits for the owner's line. Nothing changed.")
    if stop == "findings":
        verify = c.read_json(rec / f"verify-{tip}.json") or {}
        legacy = rs.is_legacy(verify)
        kinds = [rs.kind_of(f, legacy) for f in verify.get("findings") or []]
        if not kinds or any(k != rs.GAP for k in kinds):
            raise Refused(f"{slice_id} stopped on its verifier's findings, with a fault in behaviour (or a finding with "
                          "no kind): the line never clears that. The owner adds a round or accepts. Nothing changed.")
        raise Refused(f"{slice_id} stopped at its rounds limit with open findings ({len(kinds)} gaps in a test): "
                      "accepting a slice with open findings is the owner's (his line, or his standing line), never the "
                      "line's. Nothing changed.")
    row = c.slice_row(slice_id)
    moved = [k for k in c.FROZEN_KEYS if (frozen.get(k) or "") != (row.get(k) or "")]
    waiting = unapplied(slice_id, "refreeze")
    if moved or waiting:
        raise Refused(f"{slice_id}'s frozen commands differ from main's row ({', '.join(moved) or 'none yet'})"
                      + (f" and the owner's refreeze line is waiting ({'; '.join(waiting)})" if waiting else "")
                      + ": a refreeze changes what is tested and is the owner's alone. Nothing changed.")


#: The owner's standing permission for the line to clear a stop whose cause is the line's (his file 012, A2; common.py).
CLS = "clear-line-stops"
#: The Stop hook's scan-map red (stop_check.py), and the tests it names.
SCAN_RED = "RED: scan map:"
SCAN_NAMES = re.compile(r"on main\): (.+?)\. Say so", re.S)


def red_lines(rec: Path) -> list[str]:
    return [str(x) for x in (c.read_json(rec / "red_stop.json") or {}).get("last") or []]


def own_red(frozen: dict, rec: Path, tip: str) -> str:
    """Where a red of the stop is the slice's own ('' when none is): its acceptance red, its own work uncommitted, the
    lint of the files its branch changed, or a failing test in a file it wrote or changed or that is its acceptance's
    (his file 012, A2: never cleared when any red is in the part's own acceptance or its own tests)."""
    last = red_lines(rec)
    for x in last:
        head = x.split("\n", 1)[0]
        if head.startswith("RED: acceptance"):
            return "its acceptance is red"
        if head.startswith("RED: uncommitted"):
            return "its own work is uncommitted"
        if head.startswith(("RED: ruff", "RED: eslint")):
            return f"the lint of the files its branch changed is red ({head[5:].split(' (', 1)[0]})"
    main = c.git(["rev-parse", "main"], c.REPO)
    base = c.git(["merge-base", main, tip], c.REPO, check=False) or frozen["base"]
    own = set(dry_run.acceptance_files(frozen)) | set(c.git(["diff", "--name-only", f"{base}...{tip}"], c.REPO).split())
    acceptance = frozen.get("acceptance") or ""
    for i in dry_run.failing_ids("\n".join(last)):
        path = dry_run.id_path(i)
        if Path(path).name in acceptance or any(f == path or f.endswith("/" + path) or path.endswith("/" + f) for f in own):
            return f"{i} is in a test the slice wrote or changed, or its acceptance's"
    return ""


def cause_c(slice_id: str, rec: Path, wt: Path) -> tuple[str, list[str]]:
    """Why a scan-map red whose rows the conductor has since written is not the cause ('' when it is), and the tests
    it named: every red in the red stop is the scan map's (a new test that walks a folder with no row, which a builder
    cannot add), and main's map (main's committed scan_map.tsv beside the installed copy, and scan_rows/<ID>.tsv on main)
    now has a row for each test it named, read as the Stop hook reads them: a row not yet committed does not count."""
    last = red_lines(rec)
    if not last or any(not x.startswith(SCAN_RED) for x in last):
        return "the red stop is not the scan map alone", []
    names = sorted({n.strip() for x in last for m in SCAN_NAMES.finditer(x) for n in m.group(1).split(",") if n.strip()})
    if not names:
        return "the scan-map red names no test", []
    import scan_select
    import stop_check
    installed = c.DATA / "bin" / "scan_map.tsv"  # the Stop hook's own reading: the installed copy and main's, never a
    table = (scan_select.entries(installed) if installed.is_file() else []) + stop_check.main_map(str(wt))  # row uncommitted
    rows = subprocess.run(["git", "show", f"main:{stop_check.SCAN_ROWS}{slice_id}.tsv"], cwd=str(wt), capture_output=True,
                          text=True)
    if rows.returncode == 0:
        table += scan_select.load(rows.stdout)
    missing = scan_select.unmapped(wt / "OspreyFlow_Build", table, only=set(names))
    if missing:
        return f"main still has no scan-map row for {', '.join(missing)}", []
    return "", names


def cause_a(slice_id: str, frozen: dict, wt: Path, tip: str) -> str:
    """Why main having moved under the slice is not the cause ('' when it is): main has commits the branch lacks; they
    merge into it cleanly; they change none of the slice's own acceptance files; and the line has not cleared this
    slice for this main already (one clearance per move of main, so a slice red for its own reasons is not cleared
    again and again)."""
    main = c.git(["rev-parse", "main"], c.REPO)
    if subprocess.run(["git", "merge-base", "--is-ancestor", main, tip], cwd=str(c.REPO)).returncode == 0:
        return "main has not moved under the slice (the branch already holds main)"
    if any(r["slice"] == slice_id and r["cause"] == "a" and main in r["what"] for r in c.self_clears()):
        return f"the line already cleared {slice_id} once for main at {main[:10]}"
    files = conflicts_with_main(wt)
    if files is None or files:
        return "main does not merge into the branch cleanly" + (f" ({', '.join(files[:5])})" if files else "")
    base = c.git(["merge-base", main, tip], c.REPO)
    own = dry_run.acceptance_files(frozen)
    touched = c.git(["diff", "--name-only", base, main, "--", *own], c.REPO).split() if own else []
    if touched:
        return f"main's move changes the slice's own acceptance files ({', '.join(touched)})"
    return ""


def cause_b(slice_id: str, frozen: dict, st: dict, rec: Path, tip: str, log: Path) -> tuple[str, dict]:
    """Why a broken check that is not the slice's is not the cause ('' when it is), and when it is, what the line
    removes: every red in the red stop is in the checks; each failing test is one the slice did not write (not among
    its acceptance files, not changed by its branch, not the acceptance's); all of them are run by one pytest step;
    that step, run on main's own tree made as a builder's worktree is made, fails on exactly the same tests; and
    with those tests deselected the step is green there."""
    red = c.read_json(rec / "red_stop.json") or {}
    last = [str(x) for x in red.get("last") or []]
    if not last or any(not x.startswith("RED: checks") for x in last):
        return "the red stop is not the checks alone (" + "; ".join(x.split("\n", 1)[0][:80] for x in last) + ")", {}
    ids = dry_run.failing_ids("\n".join(last))
    if not ids:
        return "the red stop names no failing test", {}
    own = set(dry_run.acceptance_files(frozen))
    own |= set(c.git(["diff", "--name-only", f"{frozen['base']}...{tip}"], c.REPO).split())
    acceptance = frozen.get("acceptance") or ""
    for i in ids:
        path = dry_run.id_path(i)
        name = Path(path).name
        if name in acceptance or any(name == Path(f).name for f in dry_run.acceptance_files(frozen)):
            return f"{i} is the acceptance's test: the acceptance is never removed", {}
        if any(f == path or f.endswith("/" + path) or path.endswith("/" + f) for f in own):
            return f"{i} is in a file the slice wrote or changed", {}
    checks = frozen.get("checks") or ""
    spans = dry_run.step_spans(checks)

    def runs(step: str, test_id: str) -> bool:
        path = dry_run.id_path(test_id)
        parents = [str(Path(path).parent)] + [str(q) for q in Path(path).parents][1:-1]
        return "pytest" in step and (Path(path).name in step or any(f"{q}/" in step or step.rstrip("/").endswith(q)
                                                                     for q in parents))
    where = [n for n, (a, b) in enumerate(spans) if all(runs(checks[a:b], i) for i in ids)]
    if len(where) != 1:
        return f"no one pytest step of the checks runs all of {', '.join(ids)}", {}
    a, b = spans[where[0]]
    step = checks[a:b]
    narrowed = step + "".join(f" --deselect {shlex.quote(i)}" for i in ids)
    tree = dry_run.scratch_tree("main")
    try:
        dry_run.builder_shaped(tree)
        if c.slice_row(slice_id).get("env") == "full":  # the worktree's own environment, as slice_start.py builds it
            ms.slice_env(tree, log, st.get("slot"))
        env = stop_check_env(tree, st.get("slot"))
        stood = dry_run.stand_in(tree, dry_run.acceptance_files(frozen))
        try:
            code, out, _ = dry_run.run_marked(step, tree, env, log)
            on_main = dry_run.failing_ids(out)
            if code == 0 or sorted(on_main) != sorted(ids):
                return (f"the step does not fail identically on main's own tree (main: exit {code}, failing "
                        f"{', '.join(on_main) or 'none'}; the slice: {', '.join(ids)})"), {}
            code2, out2, _ = dry_run.run_marked(narrowed, tree, env, log)
            if code2 != 0:
                return (f"with {', '.join(ids)} removed the step is still red on main's own tree (exit {code2}): "
                        + dry_run.tail(out2, 4)), {}
        finally:
            for f in stood:
                (tree / f).unlink(missing_ok=True)
    finally:
        dry_run.drop_tree(tree)
    return "", {"ids": ids, "step": step, "narrowed": narrowed, "checks": checks[:a] + narrowed + checks[b:]}


def stop_check_env(tree: Path, slot) -> dict:
    import stop_check  # the Stop hook's own environment for a builder's commands (standard library only)
    return stop_check.seat_env(str(tree), slot)


def row_with_checks(slice_id: str, checks: str) -> None:
    """slices.tsv in the main checkout, the slice's checks column alone changed (written whole, then renamed)."""
    f = c.REPO / c.SLICES_REL
    lines = f.read_text().split("\n")
    hits = [n for n, ln in enumerate(lines) if ln.startswith(slice_id + "\t")]
    if len(hits) != 1:
        raise Refused(f"{c.SLICES_REL} holds {len(hits)} rows for {slice_id}. Nothing changed.")
    cols = lines[hits[0]].split("\t")
    if len(cols) != len(c.COLUMNS):
        raise Refused(f"{slice_id}'s row has {len(cols)} columns, not {len(c.COLUMNS)}. Nothing changed.")
    cols[c.COLUMNS.index("checks")] = checks
    lines[hits[0]] = "\t".join(cols)
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_text("\n".join(lines))
    tmp.replace(f)


def self_clear(slice_id: str, frozen: dict, st: dict, rec: Path, wt: Path) -> list[str]:
    """The line's own clearance of a stop, with no line from the owner (LINE_FIXES_5_BRIEF.md, A), or a refusal in
    words. The exclusions come first and hold whatever the cause; then (b), the narrower diagnosis, then (a)."""
    stop = stop_of(st, rec)
    if not stop:
        raise Refused(f"{slice_id} is not stopped on red checks or at its rounds limit (phase {st.get('phase')}): "
                      "nothing for the line to clear. Nothing changed.")
    if stop == "refused":
        raise Refused(f"{slice_id} was refused by the merge gate: resume.py {slice_id} send-back is the action (no line "
                      "within the rounds limit, or for a conflict). Nothing changed.")
    tip = c.git(["rev-parse", frozen["branch"]], c.REPO)
    owners_alone(slice_id, frozen, st, rec, stop, tip)
    grant, why = c.standing_grant(CLS)  # the owner's file 012, A2: on his standing permission, within its budget
    if not grant:
        raise Refused(f"{slice_id}'s stop waits for the owner's line: the line clears a stop itself only on his standing "
                      f"permission ({CLS}), and {why}. Nothing changed.")
    if c.parked(slice_id):
        raise Refused(f"the owner has parked {slice_id} ({c.parked(slice_id)} in resume.tsv): the line never clears its "
                      "stop. Nothing changed.")
    mine = own_red(frozen, rec, tip)
    if mine:
        raise Refused(f"{slice_id}'s red stop is its own ({mine}): the line never clears a red in the slice's own "
                      "acceptance or its own tests. It waits for the owner's line. Nothing changed.")
    red = c.read_json(rec / "red_stop.json") or {}
    use = f"; on the owner's standing permission ({CLS}), use {grant['used'] + 1} of {grant['per_day']} today"
    log = c.DATA / "dry-runs" / f"{slice_id}-self-clear-{int(time.time())}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    why_b, removal = cause_b(slice_id, frozen, st, rec, tip, log) if stop == "red" else ("not a red stop", {})
    if not why_b:
        changed_row_free = [ln for ln in c.git(["status", "--porcelain", "--untracked-files=no"], c.REPO).splitlines()
                            if not ln[3:].startswith(ms.OWNERS_LOCAL)]
        if c.git(["rev-parse", "--abbrev-ref", "HEAD"], c.REPO) != "main" or changed_row_free or \
                c.git(["diff", "--cached", "--name-only"], c.REPO):
            raise Refused(f"cause (b) holds for {slice_id}, but the main checkout is not on main with nothing "
                          "uncommitted: the line commits the slice's narrowed row there. Commit or set aside first. "
                          "Nothing changed.")
        row_with_checks(slice_id, removal["checks"])
        removed = ", ".join(removal["ids"])
        sha = commit_row(slice_id, f"docs(process): {slice_id}'s checks without {removed}, which fail identically on "
                                   "main (the line's self-clear, cause b)")
        c.refreeze(slice_id, f"line (self-clear, cause b): removed {removed}")
        (rec / "red_stop.json").unlink()
        (rec / "red_stops").unlink(missing_ok=True)
        said = back_to_building(slice_id, wt)
        what = (f"removed {removed} from the checks (a check the slice did not write, failing identically on main's "
                f"own tree; committed {sha[:10]}; the acceptance unchanged); red stop at {tip[:10]} cleared; building, "
                f"round {st.get('round', 1)} unchanged{use}")
        c.log_standing_use(slice_id, CLS, "self-clear", "red", "b", what, {"red_stop": red})
        return [f"{slice_id}: cleared by the line (cause b): {what}.", *said]
    why_c, names = cause_c(slice_id, rec, wt) if stop == "red" else ("not a red stop", [])
    if not why_c:
        (rec / "red_stop.json").unlink()
        (rec / "red_stops").unlink(missing_ok=True)
        said = back_to_building(slice_id, wt)
        what = (f"the red stop at {tip[:10]} was the scan map's alone, and main now has the row for {', '.join(names)} "
                f"(written since by the conductor; a builder cannot add one); cleared; building, round "
                f"{st.get('round', 1)} unchanged{use}")
        c.log_standing_use(slice_id, CLS, "self-clear", "red", "c", what, {"red_stop": red})
        return [f"{slice_id}: cleared by the line (cause c): {what}.", *said]
    why_a = cause_a(slice_id, frozen, wt, tip)
    if not why_a:
        main = c.git(["rev-parse", "main"], c.REPO)
        if subprocess.run(["git", "merge", "--no-edit", "-m", f"merge: main into lane for slice {slice_id} (the line's "
                           "self-clear, cause a: main moved under the slice)", main], cwd=str(wt),
                          capture_output=True).returncode != 0:
            c.git(["merge", "--abort"], wt, check=False)
            raise Refused(f"merging main into {slice_id}'s branch failed: undone. Nothing changed.")
        (rec / "red_stop.json").unlink(missing_ok=True)
        (rec / "red_stops").unlink(missing_ok=True)
        said = back_to_building(slice_id, wt)
        what = (f"main {main} merged into the branch (clean; the slice's acceptance and checks unchanged); {stop} stop "
                f"at {tip[:10]} cleared; building, round {st.get('round', 1)} unchanged{use}")
        c.log_standing_use(slice_id, CLS, "self-clear", stop, "a", what, {"red_stop": red})
        return [f"{slice_id}: cleared by the line (cause a): {what}.", *said]
    raise Refused(f"{slice_id}'s stop is not one the line clears: not (b): {why_b}; not (c): {why_c}; not (a): {why_a}. "
                  "It waits for the "
                  "owner's line, as before. Nothing changed.")


#: The actions that go on while a merge of another slice runs (LINE_FIXES_5_BRIEF.md, 2b; the owner, 21 November 2026:
#: a running merge held six of his lines and two standing accepts). Each touches only the records folder, the slice's own
#: worktree and, for refreeze and self-clear's cause (b), the slice's own row of slices.tsv, committed under the records
#: lock and landed beneath the merge's tested result as any records commit is. The others (correct-command, move-seat),
#: and any action on the slice being merged, wait for it.
DURING_MERGE = ("add-round", "clear-stop", "send-back", "accept", "refreeze", "undo-seat-failure", "self-clear")
#: The slice a running merge is merging, while this action goes on beside it (set by locks()); None otherwise.
MERGE_RUNNING: str | None = None


def locks(slice_id: str, action: str) -> list:
    """The merge lock, or, while a merge of another slice runs, nothing of it for the actions that may go on; and the
    slice's own lock, so two actions on one slice never run together. Refused in words otherwise."""
    held = []
    try:
        held.append(ms.lock())
    except ms.Refused:
        busy = ms.merging()
        if busy is None:  # it ended between the two looks
            try:
                held.append(ms.lock())
            except ms.Refused as e:
                raise Busy(str(e)) from None
        elif action not in DURING_MERGE:
            raise Busy(f"another merge is running ({busy}): {action} waits for it (only {', '.join(DURING_MERGE)}, on "
                          "another slice, go on meanwhile). Nothing changed.")
        elif busy in (slice_id, "?"):
            raise Busy(f"another merge is running ({slice_id if busy == slice_id else 'of a slice its record does not name'}"
                          f"): {action} on {slice_id} waits for it. Nothing changed.")
        else:
            global MERGE_RUNNING
            MERGE_RUNNING = busy
    import fcntl
    f = c.DATA / "locks" / f"resume-{slice_id}.lock"  # beside the records, never in them
    f.parent.mkdir(parents=True, exist_ok=True)
    fh = f.open("w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fh.close()
        for h in held:
            h.close()
        raise Busy(f"another resume.py action on {slice_id} is running. Nothing changed.")
    return [*held, fh]


def act(slice_id: str, action: str, standing_only: bool = False, args: list[str] | tuple[str, ...] = ()) -> list[str]:
    held = locks(slice_id, action)
    try:
        frozen = frozen_of(slice_id)
        if action == "move-seat":  # touches state.json's one key only: a builder at work in the worktree is no matter
            return move_seat(slice_id, args)
        wt = clean_worktree(frozen)
        st = c.state(slice_id)
        phase, rnd, limit = st.get("phase"), st.get("round", 1), st.get("rounds_limit", 1)
        rec = c.rec_dir(slice_id)

        if action == "undo-seat-failure":
            return undo_seat_failure(slice_id, frozen, st, rec)

        if action == "self-clear":
            return self_clear(slice_id, frozen, st, rec, wt)

        if action == "refreeze":
            _old, new = changed_row(slice_id, c.FROZEN_KEYS, briefs_aside=True)
            if all((frozen.get(k) or "") == new[k] for k in c.FROZEN_KEYS):
                raise Refused(f"{slice_id}'s row in the working copy is what is already frozen.")
            tag = authority(slice_id, action)
            sha = commit_row(slice_id, f"docs(process): {slice_id}'s frozen commands, on the owner's word (resume.py refreeze)")
            fz = c.refreeze(slice_id, "owner (resume.tsv)")
            c.log_owner_change(slice_id, action, f"{tag}: committed {sha[:10]}; " +
                               "; ".join(f"{k}: {fz['history'][-1].get(k)} -> {fz[k]}" for k in c.FROZEN_KEYS
                                         if fz['history'][-1].get(k) != fz[k]))
            return [f"{slice_id}: refrozen from main ({sha[:10]}); its phase is unchanged ({phase})."]

        if action == "add-round":
            if phase == "refused":  # 8.4: the owner's add-round line is send-back's authority past the limit
                raise Refused(f"{slice_id} was refused by the merge gate (phase refused, round {rnd} of {limit}): the "
                              f"action is resume.py {slice_id} send-back, which uses this add-round line past the rounds "
                              "limit (and needs none within it). The line is not used. Nothing changed.")
            if phase != "stopped" or (rec / "red_stop.json").exists() or rnd < limit:
                raise Refused(f"{slice_id} is not stopped at its rounds limit (phase {phase}, round {rnd} of {limit}).")
            tag = authority(slice_id, action)
            said = back_to_building(slice_id, wt, round=rnd + 1, rounds_limit=limit + 1)
            c.log_owner_change(slice_id, action, f"{tag}: round {rnd} -> {rnd + 1}, limit {limit} -> {limit + 1}")
            return [f"{slice_id}: one more round ({rnd + 1} of {limit + 1}); building.", *said]

        if action == "clear-stop":
            if phase != "stopped" or not (rec / "red_stop.json").exists():
                raise Refused(f"{slice_id} is not stopped on red checks (phase {phase}, no red_stop.json).")
            waiting = unapplied(slice_id, "refreeze")
            if waiting:  # 8.2: building on the old checks would only meet the same stop again
                raise Refused(f"the owner's refreeze line for {slice_id} is waiting ({'; '.join(waiting)}): apply it first "
                              f"(resume.py {slice_id} refreeze), then clear-stop, so the builder starts on the new checks. "
                              "Nothing changed.")
            tag = authority(slice_id, action)
            red = c.read_json(rec / "red_stop.json") or {}
            (rec / "red_stop.json").unlink()
            (rec / "red_stops").unlink(missing_ok=True)
            said = back_to_building(slice_id, wt)
            c.log_owner_change(slice_id, action, f"{tag}: red stop at {str(red.get('commit', ''))[:10]} cleared")
            return [f"{slice_id}: red stop cleared; building.", *said]

        if action == "send-back":
            if phase == "verified":  # on the owner's line only (22 November 2026, SE9)
                return send_back_verified(slice_id, wt, st, rnd, limit)
            if phase != "refused":
                raise Refused(f"{slice_id} was not refused by the merge gate (phase {phase}).")
            if st.get("refused_for") == "records":  # the line's own fault: no round is spent on it
                said = back_to_building(slice_id, wt)
                c.log_owner_change(slice_id, action, "standing: a records-only conflict; main merged in; round unchanged")
                return [f"{slice_id}: back to building (round {rnd} of {limit}), main merged in.", *said]
            if st.get("refused_for") == "conflict":  # main moved under a verified slice: no round, no line (1a)
                gate = c.read_json(rec / f"verify-gate-{st.get('tip') or ''}.json") or {}
                files = ((gate.get("findings") or [{}])[0]).get("file") or "see the gate's finding"
                said = back_to_building(slice_id, wt)
                c.log_owner_change(slice_id, action, f"standing: a merge conflict with main ({files}); the builder merges "
                                                     "main in; round unchanged")
                return [f"{slice_id}: back to the builder to merge main in (a conflict in {files}), round {rnd} of "
                        f"{limit}, no round spent.", *said]
            if rnd < limit:
                said = back_to_building(slice_id, wt, round=rnd + 1)
                c.log_owner_change(slice_id, action, f"standing (within the rounds limit): round {rnd} -> {rnd + 1}")
                return [f"{slice_id}: back to the builder with the gate's findings, round {rnd + 1} of {limit}.", *said]
            try:
                tag = authority(slice_id, "add-round")
            except Refused as no_line:  # the owner's file 012, A1: his standing permission in place of the line
                return round_after_refusal(slice_id, wt, st, rec, rnd, limit, str(no_line))
            said = back_to_building(slice_id, wt, round=rnd + 1, rounds_limit=limit + 1)
            c.log_owner_change(slice_id, action, f"{tag}: past the limit; round {rnd} -> {rnd + 1}, limit {limit} -> {limit + 1}")
            return [f"{slice_id}: back to the builder with the gate's findings, round {rnd + 1} of {limit + 1}.", *said]

        if action == "correct-command":
            if phase != "stopped":
                raise Refused(f"{slice_id} is not stopped (phase {phase}).")
            why = only_malformed(slice_id)
            old, new = changed_row(slice_id, ("acceptance", "checks"))
            olds = {k: frozen.get(k) or "" for k in c.FROZEN_KEYS}
            if any(olds[k] != old[k] for k in c.FROZEN_KEYS):
                raise Refused(f"main's row for {slice_id} is not what is frozen: that needs the owner (refreeze).")
            if all(olds[k] == new[k] for k in c.FROZEN_KEYS):
                raise Refused(f"{slice_id}'s row in the working copy is unchanged: nothing to correct.")
            same_tests(olds, new)
            tip = c.git(["rev-parse", frozen["branch"]], c.REPO)
            log = c.DATA / "dry-runs" / f"{slice_id}-correct-{int(time.time())}.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            problems = dry_run.prove(new, slot=st.get("slot"), tip=tip, log=log)
            if problems:
                raise Refused("the corrected commands are not proved on main:\n" + "\n".join(problems) + f"\nSee {log}.")
            sha = commit_row(slice_id, f"docs(process): {slice_id}'s malformed command corrected (resume.py correct-command)")
            c.refreeze(slice_id, "conductor (correct-command, ruling 3)")
            (rec / "red_stop.json").unlink()
            (rec / "red_stops").unlink(missing_ok=True)
            said = back_to_building(slice_id, wt)
            shown = "; ".join(f"{k}: {olds[k]} -> {new[k]}" for k in ("acceptance", "checks") if olds[k] != new[k])
            c.log_owner_change(slice_id, action, f"standing (ruling 3): {why}; proved on main; committed {sha[:10]}; "
                                                 f"command corrected: {shown}")
            return [f"{slice_id}: command corrected ({why}): {shown}. Building; tell the owner in the next report.", *said]
        if action == "accept" and (standing_only or not owner_lines(slice_id, action)):
            return standing_accept(slice_id, frozen, st, rec)
        if action == "accept":
            tip, verify = findings_at_tip(slice_id, frozen)
            at_limit = rnd >= limit and (phase == "refused" or (phase == "stopped" and not (rec / "red_stop.json").exists()))
            if not at_limit:  # the owner's word of 21 November 2026: at any round, once the verifier's record is there
                before_the_limit(slice_id, phase, rnd, limit, tip, verify, rec)
            no_key_finding(verify)  # at any round (the owner's file 003)
            tag = authority(slice_id, action)
            seen_in = rnd - 1 if phase == "building" else rnd  # a slice sent back to building is a round on
            acc = write_acceptance(slice_id, tip, verify, f"{slice_id} {action} {today()}", "owner (resume.tsv)",
                                   None if at_limit else {"round": seen_in, "before_the_limit": True})
            n = len(acc["findings"])
            c.log_owner_change(slice_id, action, f"{tag}: tip {tip}; {n} findings accepted "
                                                 f"({rs.kinds_said(rs.kinds_of(acc['findings'], rs.is_legacy(verify)))})"
                                                 + ("" if at_limit else f"; before the rounds limit, round {seen_in} "
                                                                        f"of {limit}"))
            return [f"{slice_id}: accepted narrower at {tip[:10]} with {n} findings, on the owner's word; verified. "
                    f"The conductor runs merge_slice.py merge {slice_id}: every other gate still runs."]
        raise Refused(f"unknown action {action}")
    finally:
        for fh in held:
            fh.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slice")
    ap.add_argument("action", choices=ACTIONS)
    ap.add_argument("args", nargs="*", help="move-seat: the seat (builder or verifier) and the account")
    a = ap.parse_args()
    try:
        if a.args and a.action != "move-seat":
            raise Refused(f"{a.action} takes no arguments ({' '.join(a.args)}). Nothing changed.")
        said = act(a.slice, a.action, args=a.args)
    except (Refused, ms.Refused) as e:
        print(f"Refused: {e}", file=sys.stderr)
        return 1
    print("\n".join(said))
    subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "board.py"), "--quiet"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
