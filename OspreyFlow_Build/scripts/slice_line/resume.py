#!/usr/bin/env python3
"""Return a stopped or refused slice to its builder (process/lanes/v062/slice-line/README.md, "Resuming a slice").

    resume.py <slice> <action>     run by the conductor, whole and unchained (the guard refuses it to every other seat)

  refreeze         commits slices.tsv (that slice's frozen columns, nothing else) and refreezes it     owner's line
  add-round        a slice stopped at its rounds limit gets one more round                             owner's line
  clear-stop       a slice stopped on red checks: its red-stop records removed, back to building       owner's line
  send-back        a slice the merge gate refused goes back with the gate's findings, its round        none within the
                   advanced (past its rounds limit it needs the owner's add-round line as well)        limit
  correct-command  the conductor's own malformed command, corrected and proved on main (ruling 3)      none: the code
                                                                                                        holds the limits
  accept           a slice stopped at its rounds limit with a verifier's findings for its exact tip    owner's line
                   is merged narrower: an acceptance record for that tip, phase verified (the merge
                   script takes it in place of the verifier's pass, for that tip only). Without a
                   line, the owner's standing line (standing.tsv: accept-test-gaps from-round N         or the owner's
                   <date>) accepts a slice at round N or later whose newest findings record is the     standing line
                   verifier's for its tip and holds only gaps in a test; run_seat.py tries it after
                   each verifier record with findings

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
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402
import dry_run  # noqa: E402
import merge_slice as ms  # noqa: E402
import run_seat as rs  # noqa: E402

ACTIONS = ("refreeze", "add-round", "clear-stop", "send-back", "correct-command", "accept")
OWNER_ACTIONS = ("refreeze", "add-round", "clear-stop", "accept")
#: What a corrected command may not add: anything that changes what a check tests rather than how it is run.
LOOSENING = ("||", "; true", "exit 0", " -k ", "--deselect", "--ignore", "--grep", " -t ", "--passWithNoTests", "skip",
             "xfail", "set +e", "--last-failed", "--lf", "--testNamePattern", "--only")
TEST_FILE = re.compile(r"[\w./-]*(?:test_[\w-]+\.py|[\w-]+_test\.py|[\w.-]+\.(?:test|spec)\.[cm]?[jt]sx?)(?:::[\w\[\]-]+)?")


class Refused(Exception):
    pass


def today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


# ------------------------------------------------------------------ the owner's word


def owner_lines(slice_id: str, action: str) -> int:
    """How many of the owner's lines in resume.tsv name this slice and action today."""
    if not c.RESUME_FILE.is_file():
        return 0
    n = 0
    for ln in c.RESUME_FILE.read_text().splitlines():
        if ln.strip().startswith("#"):
            continue
        parts = ln.split()
        if len(parts) == 3 and parts[0] == slice_id and parts[1] == action and parts[2] == today():
            n += 1
    return n


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


# ------------------------------------------------------------------ slices.tsv: one row's frozen columns


def changed_row(slice_id: str, allowed: tuple[str, ...]) -> tuple[dict, dict]:
    """The slice's row on main and in the working copy, when the working copy differs from main in that row only, and
    there only in `allowed` columns; refused otherwise."""
    branch = c.git(["rev-parse", "--abbrev-ref", "HEAD"], c.REPO)
    if branch != "main":
        raise Refused(f"the main checkout is not on main ({branch}).")
    dirty = [ln[3:] for ln in c.git(["status", "--porcelain", "--untracked-files=no"], c.REPO).splitlines()
             if not ln[3:].startswith(ms.OWNERS_LOCAL)]
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
    c.git(["add", "--", c.SLICES_REL], c.REPO)
    staged = c.git(["diff", "--cached", "--name-only"], c.REPO).splitlines()
    if staged != [c.SLICES_REL]:
        c.git(["reset", "-q", "--", c.SLICES_REL], c.REPO)
        raise Refused("something besides slices.tsv would be committed: " + ", ".join(staged))
    c.git(["commit", "-q", "-m", f"{message}\n\nSlice-Records: yes"], c.REPO)
    subprocess.run([str(Path(__file__).resolve().parent / "push_main.sh")], cwd=c.REPO, capture_output=True)
    return c.git(["rev-parse", "HEAD"], c.REPO)


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
                      f"{tip[:10]}: the standing accept reads only the newest verifier record. Nothing changed.")


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
    acc = write_acceptance(slice_id, tip, verify, rule["line"], "standing",
                           {"rule": f"standing.tsv: {rule['line']} (RULINGS.md, 19 November 2026, ruling 5: from a "
                                    "slice's third round on, a gap in a test never blocks)", "round": rnd})
    n = len(acc["findings"])
    c.log_owner_change(slice_id, "accept", f"standing (standing.tsv: {rule['line']}): tip {tip}; round {rnd}; {n} "
                                           "gaps in a test accepted, each for a backlog row")
    return [f"{slice_id}: accepted narrower at {tip[:10]} on the owner's standing line: {n} gaps in a test, each to "
            f"become a backlog row; verified. The conductor runs merge_slice.py merge {slice_id} and tells the owner."]


def act(slice_id: str, action: str, standing_only: bool = False) -> list[str]:
    fh = ms.lock()
    try:
        frozen = frozen_of(slice_id)
        wt = clean_worktree(frozen)
        st = c.state(slice_id)
        phase, rnd, limit = st.get("phase"), st.get("round", 1), st.get("rounds_limit", 1)
        rec = c.rec_dir(slice_id)

        if action == "refreeze":
            _old, new = changed_row(slice_id, c.FROZEN_KEYS)
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
            if phase != "stopped" or (rec / "red_stop.json").exists() or rnd < limit:
                raise Refused(f"{slice_id} is not stopped at its rounds limit (phase {phase}, round {rnd} of {limit}).")
            tag = authority(slice_id, action)
            said = back_to_building(slice_id, wt, round=rnd + 1, rounds_limit=limit + 1)
            c.log_owner_change(slice_id, action, f"{tag}: round {rnd} -> {rnd + 1}, limit {limit} -> {limit + 1}")
            return [f"{slice_id}: one more round ({rnd + 1} of {limit + 1}); building.", *said]

        if action == "clear-stop":
            if phase != "stopped" or not (rec / "red_stop.json").exists():
                raise Refused(f"{slice_id} is not stopped on red checks (phase {phase}, no red_stop.json).")
            tag = authority(slice_id, action)
            red = c.read_json(rec / "red_stop.json") or {}
            (rec / "red_stop.json").unlink()
            (rec / "red_stops").unlink(missing_ok=True)
            said = back_to_building(slice_id, wt)
            c.log_owner_change(slice_id, action, f"{tag}: red stop at {str(red.get('commit', ''))[:10]} cleared")
            return [f"{slice_id}: red stop cleared; building.", *said]

        if action == "send-back":
            if phase != "refused":
                raise Refused(f"{slice_id} was not refused by the merge gate (phase {phase}).")
            if st.get("refused_for") == "records":  # the line's own fault: no round is spent on it
                said = back_to_building(slice_id, wt)
                c.log_owner_change(slice_id, action, "standing: a records-only conflict; main merged in; round unchanged")
                return [f"{slice_id}: back to building (round {rnd} of {limit}), main merged in.", *said]
            if rnd < limit:
                said = back_to_building(slice_id, wt, round=rnd + 1)
                c.log_owner_change(slice_id, action, f"standing (within the rounds limit): round {rnd} -> {rnd + 1}")
                return [f"{slice_id}: back to the builder with the gate's findings, round {rnd + 1} of {limit}.", *said]
            tag = authority(slice_id, "add-round")
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
            if not at_limit:
                raise Refused(f"{slice_id} is not stopped at its rounds limit (phase {phase}, round {rnd} of {limit}): "
                              "the owner accepts a slice narrower only once its rounds are spent. Nothing changed.")
            tag = authority(slice_id, action)
            acc = write_acceptance(slice_id, tip, verify, f"{slice_id} {action} {today()}", "owner (resume.tsv)")
            n = len(acc["findings"])
            c.log_owner_change(slice_id, action, f"{tag}: tip {tip}; {n} findings accepted "
                                                 f"({rs.kinds_said(rs.kinds_of(acc['findings'], rs.is_legacy(verify)))})")
            return [f"{slice_id}: accepted narrower at {tip[:10]} with {n} findings, on the owner's word; verified. "
                    f"The conductor runs merge_slice.py merge {slice_id}: every other gate still runs."]
        raise Refused(f"unknown action {action}")
    finally:
        fh.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slice")
    ap.add_argument("action", choices=ACTIONS)
    a = ap.parse_args()
    try:
        said = act(a.slice, a.action)
    except (Refused, ms.Refused) as e:
        print(f"Refused: {e}", file=sys.stderr)
        return 1
    print("\n".join(said))
    subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "board.py"), "--quiet"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
