#!/usr/bin/env python3
"""Start a seat as its own Claude Code session, on the account the accounts file names, with the guard loaded.

    run_seat.py builder <slice>     the slice's builder, in its worktree (one round)
    run_seat.py verifier <slice>    the verifier, read-only, on a detached copy of the branch's tip
    run_seat.py conductor           the owner's interactive conductor session

A seat refuses to start unless the guard is loaded: the installed hooks match the install manifest, the fixed
settings register them, no settings file the session reads turns hooks off, and the session's own SessionStart
hook has answered with this launch's token before any prompt is sent (stream-json input: the prompt is written
only after the guard has answered). Permission mode: dontAsk, with each seat's tools pre-allowed; anything else
is denied, never prompted. Scouts are not launched here: they are the conductor's subagents, on its account.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402

HOOKS = ("guard.py", "stop_check.py", "usage_hook.py", "scan_select.py", "scan_map.tsv")
#: The seat shim (seat_shim.sh, installed under bin/shim/ by install.sh): every seat's `claude`, first on its PATH.
SHIM_NAMES = ("claude", "claude-sol", "claude-ayan")
TOOLS = {
    "builder": "Read,Grep,Glob,Edit,Write,Bash",
    "verifier": "Read,Grep,Glob,Bash(git diff *),Bash(git log *),Bash(git show *),Bash(git status *)",
}
#: A finding's kind (the owner's rulings 4 and 5 of 19 November 2026; ACCEPT_STEP_BRIEF.md, "The standing mode"): a
#: fault in the code's behaviour, or a gap in a test (the behaviour may be right, but no test would fail if it were
#: wrong). Kept verbatim in the verifier's record; a finding without one of these two exact values has no kind, which
#: counts as a fault: nothing accepts it on the standing word.
FAULT, GAP = "fault", "test_gap"
KINDS = (FAULT, GAP)
#: Before the field existed, the extra rounds' briefs asked the verifier to begin each finding's text with one of these
#: (RULINGS.md, 19 November, ruling 5). Read as the kind only in a record written before the field (no `kinds` in it),
#: and nowhere else.
LEGACY_PREFIXES = (("FAULT IN BEHAVIOUR:", FAULT), ("GAP IN A TEST:", GAP))


def kind_of(finding: dict, legacy: bool = False) -> str | None:
    """A finding's kind: its field, or, in a record written before the field existed, its text's prefix; else None."""
    if not isinstance(finding, dict):
        return None
    if finding.get("kind") in KINDS:
        return finding["kind"]
    if legacy and "kind" not in finding:
        text = str(finding.get("what") or "").lstrip()
        for prefix, kind in LEGACY_PREFIXES:
            if text.startswith(prefix):
                return kind
    return None


def is_legacy(record: dict) -> bool:
    """A verifier record written before the kind field: it has no `kinds` count."""
    return "kinds" not in (record or {})
VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"enum": ["pass", "findings"]},
        "commit": {"type": "string"},
        "findings": {"type": "array", "items": {"type": "object", "properties": {
            "what": {"type": "string"}, "evidence": {"type": "string"}, "kind": {"enum": list(KINDS)},
            "file": {"type": "string"}, "line": {"type": "integer"}}, "required": ["what", "evidence", "kind"]}},
    },
    "required": ["verdict", "commit", "findings"],
}
PASS_FOCUS = {
    "acceptance": "Check the slice against its brief and acceptance list, the standing rules in process/CLAUDE.md, "
                  "and the spec sections it names.",
    "security": "Check the slice for security faults only: access control on every read path (rules 3, 4, 7), "
                "secrets, injection, and anything that widens what a principal can see.",
    "accessibility": "Check the slice for accessibility faults only: keyboard reach (rule 13), labels, focus, "
                     "contrast from tokens.css, and screen-reader words.",
}


def kinds_of(findings: list[dict], legacy: bool = False) -> dict:
    """How many findings are of each kind; any other value, or none, is counted as "no kind"."""
    out = {FAULT: 0, GAP: 0, "no kind": 0}
    for f in findings or []:
        k = kind_of(f, legacy)
        out[k if k in KINDS else "no kind"] += 1
    return out


def kinds_said(kinds: dict) -> str:
    n_f, n_g, n_n = kinds.get(FAULT, 0), kinds.get(GAP, 0), kinds.get("no kind", 0)
    return (f"{n_f} {'fault' if n_f == 1 else 'faults'} in behaviour, {n_g} {'gap' if n_g == 1 else 'gaps'} in a test"
            + (f", {n_n} with no kind" if n_n else ""))


class NotLoaded(SystemExit):
    pass


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def preflight(account: str, cwd: Path) -> dict:
    manifest = c.read_json(c.BIN / "manifest.json")
    if not manifest:
        raise NotLoaded("REFUSED TO START: the guard is not installed (no manifest): run install.sh.")
    for h in HOOKS:
        p = c.BIN / "bin" / h
        if not p.is_file() or sha(p) != manifest.get(h):
            raise NotLoaded(f"REFUSED TO START: the installed {h} is missing or differs from the install manifest.")
    settings = c.read_json(c.BIN / "settings.json") or {}
    hooks = json.dumps(settings.get("hooks", {}))
    for need in ("guard.py pre", "guard.py session-start", "stop_check.py", "guard.py stop", "usage_hook.py stop-failure"):
        if need not in hooks:
            raise NotLoaded(f"REFUSED TO START: the fixed settings do not register '{need}'.")
    for f in (c.config_dir(account) / "settings.json", c.REPO / ".claude/settings.json",
              c.REPO / ".claude/settings.local.json", cwd / ".claude/settings.json", cwd / ".claude/settings.local.json"):
        if f.is_file() and "disableAllHooks" in f.read_text():
            raise NotLoaded(f"REFUSED TO START: {f} turns hooks off (disableAllHooks).")
    shim = c.BIN / "bin/shim"
    for name in SHIM_NAMES:
        p = shim / name
        if not p.is_file() or not manifest.get("shim/claude") or sha(p) != manifest.get("shim/claude"):
            raise NotLoaded(f"REFUSED TO START: the seat shim ({p}) is missing or differs from the install manifest: "
                            "run install.sh.")
    if c.account_stop(account):
        raise NotLoaded(f"STOPPED: account {account} is stopped ({c.account_stop(account)['error']}); the owner decides.")
    if not c.signed_in(account):
        raise NotLoaded(f"STOPPED: account {account} is signed out. The owner signs in to it.")
    return manifest


def record_limits(account: str, info: dict) -> None:
    windows = info.get("unifiedWindows") or {info.get("rateLimitType", "window"): info}
    st = c.account_state(account)
    st.setdefault("windows", {}).update({k: {"utilization": v.get("utilization"), "resetsAt": v.get("resetsAt"),
                                             "status": v.get("status")} for k, v in windows.items()})
    st["at"] = c.now()
    c.write_json(c.DATA / "accounts" / f"{account}.json", st)


def append_usage(slice_id: str, build: str, seat: str, account: str, model: str, effort: str, result: dict) -> None:
    u = result.get("usage") or {}
    st = c.account_state(account).get("windows", {})
    f = c.DATA / "usage.tsv"
    if not f.exists():
        f.write_text("at\tslice\tbuild\tseat\taccount\tmodel\teffort\tsession\tinput\tcache_create\tcache_read\toutput\t"
                     "cost_usd\tfive_hour\tseven_day\n")
    row = [c.now(), slice_id, build, seat, account, model, effort, result.get("session_id", ""),
           u.get("input_tokens", 0), u.get("cache_creation_input_tokens", 0), u.get("cache_read_input_tokens", 0),
           u.get("output_tokens", 0), result.get("total_cost_usd", ""),
           (st.get("five_hour") or {}).get("utilization", ""), (st.get("seven_day") or {}).get("utilization", "")]
    with f.open("a") as fh:
        fh.write("\t".join(str(x) for x in row) + "\n")


def seat_command(seat: str, account: str, model: str, effort: str, env_extra: dict, token: str,
                 session: str = "") -> tuple[list[str], dict]:
    """The seat's command and environment: started through the seat shim with a one-time launch token (F1, layer 3),
    the shim's folder first on the seat's PATH, so every `claude` the seat itself runs meets the shim's refusal."""
    shim = c.BIN / "bin/shim"
    launch_token = uuid.uuid4().hex
    (c.DATA / "launch").mkdir(parents=True, exist_ok=True)
    (c.DATA / "launch" / launch_token).write_text(f"{seat} {env_extra.get('OSPREY_SLICE', '')} {c.now()}\n")
    env = c.claude_env(account)
    env.update({"OSPREY_SEAT": seat, "OSPREY_SEAT_TOKEN": token, "OSPREY_ACCOUNT": account,
                "OSPREY_SLICE_HOME": str(c.DATA), "OSPREY_CLAUDE_BIN": c.CLAUDE, "OSPREY_LAUNCH_TOKEN": launch_token,
                **env_extra})
    env["PATH"] = os.pathsep.join([str(shim), *[p for p in env.get("PATH", "").split(os.pathsep) if p and p != str(shim)]])
    args = [str(shim / "claude"), "--agent", f"slice-{seat}", "--settings", str(c.BIN / "settings.json"),
            "--session-id", session or str(uuid.uuid4()), "--model", model, "--effort", effort]
    return args, env


def launch(seat: str, account: str, cwd: Path, prompt: str, model: str, effort: str, env_extra: dict,
           log: Path, extra: list[str] | None = None, interactive: bool = False) -> dict:
    manifest = preflight(account, cwd)
    token, session = uuid.uuid4().hex, str(uuid.uuid4())
    args, env = seat_command(seat, account, model, effort, env_extra, token, session)
    if not interactive:
        args += ["-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
                 "--permission-mode", "dontAsk", "--allowedTools", TOOLS[seat]]
    args += extra or []
    log.parent.mkdir(parents=True, exist_ok=True)
    err = (log.with_suffix(".stderr")).open("w")
    if interactive:
        proc = subprocess.Popen(args, cwd=str(cwd), env=env)
    else:
        proc = subprocess.Popen(args, cwd=str(cwd), env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=err, text=True)
    marker = c.DATA / "sessions" / f"{session}.guard"
    deadline = time.time() + 60
    while time.time() < deadline and proc.poll() is None:
        m = c.read_json(marker)
        if m and m.get("token") == token and m.get("sha256") == manifest["guard.py"]:
            break
        time.sleep(0.25)
    else:
        proc.kill()
        raise NotLoaded(f"REFUSED TO START: the {seat} session's guard never answered (no SessionStart marker); "
                        "the session was ended before any prompt was sent.")
    if interactive:
        proc.wait()
        return {"session_id": session}
    assert proc.stdin and proc.stdout
    proc.stdin.write(json.dumps({"type": "user", "message": {"role": "user", "content": prompt}}) + "\n")
    proc.stdin.close()
    result: dict = {}
    with log.open("w") as fh:
        for line in proc.stdout:
            fh.write(line)
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("type") == "rate_limit_event":
                record_limits(account, d.get("rate_limit_info") or {})
            elif d.get("type") == "result":
                result = d
    proc.wait()
    result.setdefault("session_id", session)
    return result


def transcript_of(account: str, session: str) -> str:
    hits = list((c.config_dir(account) / "projects").glob(f"*/{session}.jsonl"))
    return str(hits[0]) if hits else ""


def board() -> None:
    subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "board.py"), "--quiet"])


def brief_text(slice_id: str) -> str:
    try:
        return c.git(["show", f"main:{c.V062_REL}/slices/{slice_id}.md"], c.REPO)
    except RuntimeError:
        return "(no brief file on main)"


def last_findings(slice_id: str) -> str:
    """The newest findings record (a verifier's, or the merge gate's verify-gate-*), for the builder's prompt."""
    last = sorted(c.rec_dir(slice_id).glob("verify-*.json"), key=lambda p: p.stat().st_mtime)
    if last:
        v = c.read_json(last[-1]) or {}
        if v.get("verdict") != "pass":
            return "\n\nThe findings from the last round, to fix:\n" + json.dumps(v.get("findings"), indent=1)
    return ""


def rulings_note(tree: Path) -> str:
    """Main's RULINGS.md, brought into the seat's checkout (a snapshot from the slice's start) as an ignored copy."""
    copy = c.deliver_rulings(tree)
    if not copy:
        return "\n\nThe owner's rulings as on main today could not be copied into your checkout: read RULINGS.md there."
    return (f"\n\nThe owner's rulings as on main today are in {copy} (your checkout's own RULINGS.md is from the "
            "slice's start and may be older): read them before you begin; they bind this slice.")


@contextlib.contextmanager
def seat_running(slice_id: str, seat: str, account: str):
    """A running record for the slice's seat while this process runs it (running-<seat>.json, with its pid):
    resume.py move-seat refuses while one is alive."""
    f = c.rec_dir(slice_id) / f"running-{seat}.json"
    c.write_json(f, {"slice": slice_id, "seat": seat, "account": account, "pid": os.getpid(), "at": c.now()})
    try:
        yield
    finally:
        f.unlink(missing_ok=True)


#: A seat failure (LINE_FIXES_3_BRIEF.md, 1f): a session whose call was refused analysed nothing, so it is never a
#: verdict, a finding, a round or a red stop. CO2's verifier on 19 November 2026 came back in 332 ms with is_error,
#: api_error_status 403, api_error_code oauth_not_allowed_for_organization, and was written as a finding.
REFUSED_STATUSES = (401, 403, 408, 429)  # and every 5xx
SEAT_TRIES = 3
SEAT_PAUSES = (60, 300, 0)  # seconds before the second and the third try: growing


class SeatFailed(Exception):
    pass


def verdict_of(res: dict) -> dict:
    """The verifier's structured verdict in a session's result line, or {}."""
    out = res.get("structured_output")
    if isinstance(out, dict):
        return out
    try:
        out = json.loads(res.get("result") or "{}")
    except ValueError:
        return {}
    return out if isinstance(out, dict) else {}


def refusal_words(res: dict) -> str:
    head = " ".join(str(x) for x in (res.get("api_error_status"), res.get("api_error_code")) if x not in (None, ""))
    text = str(res.get("result") or "").strip()[:300]
    return (head + (": " if head and text else "") + text) or f"is_error with subtype {res.get('subtype')}"


def seat_failure(res: dict, wants_verdict: bool) -> str | None:
    """Why a session's result is a seat failure (its call refused, nothing analysed), or None for a real result.

    A refused status (401, 403, 408, 429, 5xx); is_error from a session that ran no more than the refused turn (a
    session that ran out of turns has analysed something, and is the seat's own result); no result line at all; or,
    for a verifier, no structured verdict and no turns of analysis."""
    if not res or res.get("type") != "result":
        return "the session ended with no result line"
    status = res.get("api_error_status")
    refused = isinstance(status, int) and (status in REFUSED_STATUSES or 500 <= status <= 599)
    if refused or (res.get("is_error") is True and (status is not None or (res.get("num_turns") or 0) <= 1)):
        return refusal_words(res)
    if wants_verdict and not verdict_of(res) and not res.get("num_turns"):
        return "no verdict and no turns of analysis"
    return None


def launch_seat(slice_id: str, seat: str, label: str, account: str, tip: str, call, usage,
                wants_verdict: bool = False) -> dict:
    """A seat's session (`call`), tried up to SEAT_TRIES times while its call is refused, the pause growing. Each refused
    try is a record of kind seat_failure (seat-failure-*.json: no board verdict, merge, standing accept or builder
    prompt reads it). When the tries are used, or the account is stopped meanwhile (the StopFailure hook stops it at
    the first refusal, and then a retry would be refused at the account check), the account is recorded stopped, the
    slice's state names the failure and the account, its phase and round untouched, and SeatFailed is raised."""
    why, attempt = "", 0
    for attempt in range(1, SEAT_TRIES + 1):
        with seat_running(slice_id, seat, account):
            res = call()
        usage(res)
        why = seat_failure(res, wants_verdict)
        if not why:
            st = c.state(slice_id)
            if "seat_failure" in st:
                st.pop("seat_failure")
                c.write_json(c.rec_dir(slice_id) / "state.json", st)
            return res
        c.write_json(c.rec_dir(slice_id) / f"seat-failure-{seat}-{uuid.uuid4().hex[:8]}.json",
                     {"kind": "seat_failure", "slice": slice_id, "seat": seat, "pass": label, "account": account,
                      "tip": tip, "try": attempt, "of": SEAT_TRIES, "error": why, "result": res, "at": c.now(),
                      "note": "a refused call, not a verdict: no finding, no round, no red stop"})
        print(f"{slice_id}: the {seat}'s call on account {account} was refused (try {attempt} of {SEAT_TRIES}): {why}")
        if c.account_stop(account):
            break
        if attempt < SEAT_TRIES:
            time.sleep(SEAT_PAUSES[attempt - 1])
    if not c.account_stop(account):
        c.write_json(c.DATA / "accounts" / f"{account}.stopped.json",
                     {"account": account, "error": f"seat failure after {attempt} tries: {why}", "at": c.now(),
                      "seat": seat, "slice": slice_id, "message": why})
    c.set_state(slice_id, seat_failure={"seat": seat, "account": account, "error": why, "tries": attempt,
                                        "at": c.now()})
    raise SeatFailed(f"SEAT FAILURE {slice_id}: the {seat}'s call on account {account} was refused {attempt} "
                     f"time(s); the slice stays where it was and account {account} is stopped "
                     f"({(c.account_stop(account) or {}).get('error')}). Tell the owner at once, in its words: {why}. "
                     f"The owner clears the account (clear_account.py {account}, on a resume.tsv line) or moves the "
                     "seat (resume.py move-seat).")


def stop_slice(slice_id: str, note: str) -> None:
    c.set_state(slice_id, phase="stopped", note=note)
    board()
    print(f"STOPPED {slice_id}: {note}")


def builder(slice_id: str) -> int:
    st, frozen = c.state(slice_id), c.read_json(c.rec_dir(slice_id) / "frozen.json")
    if not frozen or st.get("phase") != "building":
        raise SystemExit(f"{slice_id} is not in the building phase ({st.get('phase')}): slice_start.py first.")
    seat = c.seat_settings("builder", st["setting"])
    findings = last_findings(slice_id)
    prompt = (f"You are the builder for slice {slice_id} (build {frozen['build']}), round {st['round']} of "
              f"{st['rounds_limit']}. Your worktree is {frozen['worktree']}, on branch {frozen['branch']}.\n\n"
              f"The brief:\n{brief_text(slice_id)}\n\nFrozen for this slice (you cannot change them):\n"
              f"- acceptance files: {frozen['acceptance_files']}\n- acceptance: {frozen['acceptance']}\n"
              f"- checks: {frozen['checks']}{findings}")
    wt = Path(frozen["worktree"])
    prompt += rulings_note(wt)
    tip0 = c.git(["rev-parse", frozen["branch"]], c.REPO)
    try:
        res = launch_seat(
            slice_id, "builder", f"round {st['round']}", st["account"], tip0,
            lambda: launch("builder", st["account"], wt, prompt, seat["model"], seat["effort"],
                           {"OSPREY_SLICE": slice_id, "OSPREY_SLICE_WORKTREE": str(wt),
                            **({"OSPREY_PORTS_SLOT": str(st["slot"])} if st.get("slot") else {})},
                           c.rec_dir(slice_id) / f"builder-r{st['round']}-{uuid.uuid4().hex[:6]}.jsonl"),
            lambda r: append_usage(slice_id, frozen["build"], "builder", st["account"], seat["model"], seat["effort"], r))
    except SeatFailed as e:
        board()
        print(e)
        return 2
    sess = c.read_json(c.rec_dir(slice_id) / "sessions.json") or {"builder": [], "verifier": []}
    sess["builder"].append(res.get("session_id"))
    c.write_json(c.rec_dir(slice_id) / "sessions.json", sess)
    red = c.read_json(c.rec_dir(slice_id) / "red_stop.json")
    tip = c.git(["rev-parse", frozen["branch"]], c.REPO)
    if c.account_stop(st["account"]):
        stop_slice(slice_id, f"account {st['account']} stopped mid-slice ({c.account_stop(st['account'])['error']}): "
                             "wait for it, or tell the line to carry the slice on the same account later?")
        return 1
    if red:
        stop_slice(slice_id, f"the builder could not get the checks green in {red['red_stops']} tries: "
                             "narrow the slice, or change its checks (your word)?")
        return 0 if self_clear(slice_id) else 1
    tests = c.read_json(c.rec_dir(slice_id) / f"tests-{tip}.json")
    if tests and tests.get("green"):
        c.set_state(slice_id, phase="verifying", tip=tip)
        board()
        print(f"{slice_id}: green at {tip[:10]}; ready for the verifier.")
        return 0
    board()
    print(f"{slice_id}: the builder ended without a green test record ({res.get('subtype') or res.get('is_error')}).")
    return 1


def verifier(slice_id: str) -> int:
    st, frozen = c.state(slice_id), c.read_json(c.rec_dir(slice_id) / "frozen.json")
    if not frozen or st.get("phase") != "verifying":
        raise SystemExit(f"{slice_id} is not waiting for the verifier ({st.get('phase')}).")
    tip = c.git(["rev-parse", frozen["branch"]], c.REPO)
    tests = c.read_json(c.rec_dir(slice_id) / f"tests-{tip}.json")
    if not (tests and tests.get("green")):
        raise SystemExit(f"{slice_id}: no green test record for the tip {tip[:10]}: the builder has not finished green.")
    account = st["verifier_account"]
    seat = c.seat_settings("verifier", st["setting"])
    vt = c.WT_ROOT / f"verify-{slice_id}"
    if vt.exists():
        c.git(["checkout", "-q", "--detach", tip], vt)
    else:
        c.git(["worktree", "add", "--detach", str(vt), tip], c.REPO)
    base = frozen["base"]
    rulings = rulings_note(vt)
    diffstat = c.git(["diff", "--stat", f"{base}...{tip}"], c.REPO)
    passes = []
    for focus in seat.get("passes", ["acceptance"]):
        prompt = (f"You are the verifier for slice {slice_id} (build {frozen['build']}). You did not write this code. "
                  f"The checkout in front of you is the branch's tip, commit {tip}; the slice's base is {base}.\n"
                  f"{PASS_FOCUS[focus]}\n\nThe brief:\n{brief_text(slice_id)}\n\nAcceptance files: "
                  f"{frozen['acceptance_files']}\nAcceptance: {frozen['acceptance']}\nChecks: {frozen['checks']}\n"
                  f"The builder's test record (green):\n{json.dumps(tests, indent=1)}\n\nWhat changed:\n{diffstat}\n\n"
                  f"Use git diff {base}...{tip} and Read. Return verdict 'pass', or 'findings' with evidence (file, "
                  f"line, what is wrong and how you know). Give each finding its kind: '{FAULT}' (a fault in behaviour) "
                  f"when the code does the wrong thing, '{GAP}' (a gap in a test) when the code may be right but no "
                  f"test would fail if it were wrong; a finding without a kind counts as a fault. Put "
                  f"the commit {tip} in your answer.{rulings}")
        try:
            res = launch_seat(
                slice_id, "verifier", focus, account, tip,
                lambda: launch("verifier", account, vt, prompt, seat["model"], seat["effort"],
                               {"OSPREY_SLICE": slice_id, "OSPREY_SLICE_WORKTREE": str(vt)},
                               c.rec_dir(slice_id) / f"verifier-{focus}-{uuid.uuid4().hex[:6]}.jsonl",
                               ["--json-schema", json.dumps(VERDICT_SCHEMA)]),
                lambda r: append_usage(slice_id, frozen["build"], f"verifier:{focus}", account, seat["model"],
                                       seat["effort"], r),
                wants_verdict=True)
        except SeatFailed as e:  # no verifier record: the passes so far are run again with the rest
            board()
            print(e)
            return 2
        out = verdict_of(res)
        sid = res.get("session_id", "")
        passes.append({"pass": focus, "verdict": out.get("verdict", "findings"), "commit": out.get("commit", ""),
                       "findings": out.get("findings") or ([] if out else [{"what": "no verdict returned",
                                                                              "evidence": str(res.get("subtype"))}]),
                       "session": sid, "account": account, "model": seat["model"],
                       "transcript": transcript_of(account, sid)})
    sess = c.read_json(c.rec_dir(slice_id) / "sessions.json") or {"builder": [], "verifier": []}
    sess["verifier"] += [p["session"] for p in passes]
    c.write_json(c.rec_dir(slice_id) / "sessions.json", sess)
    ok = all(p["verdict"] == "pass" and p["commit"] == tip for p in passes)
    record = {"slice": slice_id, "commit": tip, "verdict": "pass" if ok else "findings", "passes": passes,
              "findings": [f for p in passes for f in p["findings"]], "builder_sessions": sess["builder"], "at": c.now()}
    record["kinds"] = kinds_of(record["findings"])
    c.write_json(c.rec_dir(slice_id) / f"verify-{tip}.json", record)
    if ok:
        c.set_state(slice_id, phase="verified", tip=tip)
        board()
        print(f"{slice_id}: the verifier passed {tip[:10]}. The conductor runs merge_slice.py merge {slice_id}.")
        return 0
    if standing_accept(slice_id):
        return 0
    if st["round"] >= st["rounds_limit"]:
        first = record["findings"][0]["what"] if record["findings"] else "no verdict"
        stop_slice(slice_id, f"findings after {st['round']} round(s) ({kinds_said(record['kinds'])}; first: "
                             f"{first[:90]}): accept a narrower slice, or allow another round?")
        return 1
    c.set_state(slice_id, phase="building", round=st["round"] + 1)
    board()
    print(f"{slice_id}: findings; back to the builder for round {st['round'] + 1}.")
    return 1


def self_clear(slice_id: str) -> bool:
    """The line's own clearance of a stop (resume.py self-clear; LINE_FIXES_5_BRIEF.md, A), tried after a red stop; it
    says why when it does not clear, and the slice then stays stopped for the owner, as before."""
    import resume  # here, not at the top: resume.py imports this module
    try:
        said = resume.act(slice_id, "self-clear")
    except (resume.Refused, resume.ms.Refused) as e:
        print(f"{slice_id}: not cleared by the line: {e}")
        return False
    board()
    print("\n".join(said))
    return True


def standing_accept(slice_id: str) -> bool:
    """The owner's standing accept (standing.tsv; resume.py accept), tried after a verifier record with findings; it
    says why when it does not accept, and the slice then goes on as before (another round, or stopped at the limit)."""
    import resume  # here, not at the top: resume.py imports this module
    try:
        said = resume.act(slice_id, "accept", standing_only=True)
    except (resume.Refused, resume.ms.Refused) as e:
        print(f"{slice_id}: not accepted on the standing word: {e}")
        return False
    board()
    print("\n".join(said))
    return True


def conductor_usage(session: str, account: str) -> None:
    """The conductor's own row (one per session, its scouts' with it), when its SessionEnd hook wrote none: none had
    appeared by 18 November 2026. Never a second row for a session."""
    f = c.DATA / "usage.tsv"
    if f.exists() and any(ln.split("\t")[7:8] == [session] for ln in f.read_text().splitlines()[1:]):
        return
    tp = transcript_of(account, session)
    if not tp:
        return
    import usage_hook
    usage_hook.DATA = c.DATA
    usage_hook.conductor_row(Path(tp), session, account)


def conductor() -> int:
    seat = c.seat_settings("conductor")
    account = c.account_for("conductor")
    res = launch("conductor", account, c.REPO, "", seat["model"], seat["effort"], {},
                 c.DATA / "conductor" / f"{c.now()}.log", interactive=True)
    conductor_usage(res["session_id"], account)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("seat", choices=["builder", "verifier", "conductor"])
    ap.add_argument("slice", nargs="?")
    a = ap.parse_args()
    try:
        if a.seat == "conductor":
            return conductor()
        if not a.slice:
            raise SystemExit("name the slice")
        return builder(a.slice) if a.seat == "builder" else verifier(a.slice)
    except NotLoaded as e:
        print(e, file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
