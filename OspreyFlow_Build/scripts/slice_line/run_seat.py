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
import hashlib
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402

HOOKS = ("guard.py", "stop_check.py", "usage_hook.py")
TOOLS = {
    "builder": "Read,Grep,Glob,Edit,Write,Bash",
    "verifier": "Read,Grep,Glob,Bash(git diff *),Bash(git log *),Bash(git show *),Bash(git status *)",
}
VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"enum": ["pass", "findings"]},
        "commit": {"type": "string"},
        "findings": {"type": "array", "items": {"type": "object", "properties": {
            "what": {"type": "string"}, "evidence": {"type": "string"},
            "file": {"type": "string"}, "line": {"type": "integer"}}, "required": ["what", "evidence"]}},
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


def launch(seat: str, account: str, cwd: Path, prompt: str, model: str, effort: str, env_extra: dict,
           log: Path, extra: list[str] | None = None, interactive: bool = False) -> dict:
    manifest = preflight(account, cwd)
    token, session = uuid.uuid4().hex, str(uuid.uuid4())
    env = c.claude_env(account)
    env.update({"OSPREY_SEAT": seat, "OSPREY_SEAT_TOKEN": token, "OSPREY_ACCOUNT": account,
                "OSPREY_SLICE_HOME": str(c.DATA), **env_extra})
    args = [c.CLAUDE, "--agent", f"slice-{seat}", "--settings", str(c.BIN / "settings.json"),
            "--session-id", session, "--model", model, "--effort", effort]
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


def rulings_note(tree: Path) -> str:
    """Main's RULINGS.md, brought into the seat's checkout (a snapshot from the slice's start) as an ignored copy."""
    copy = c.deliver_rulings(tree)
    if not copy:
        return "\n\nThe owner's rulings as on main today could not be copied into your checkout: read RULINGS.md there."
    return (f"\n\nThe owner's rulings as on main today are in {copy} (your checkout's own RULINGS.md is from the "
            "slice's start and may be older): read them before you begin; they bind this slice.")


def stop_slice(slice_id: str, note: str) -> None:
    c.set_state(slice_id, phase="stopped", note=note)
    board()
    print(f"STOPPED {slice_id}: {note}")


def builder(slice_id: str) -> int:
    st, frozen = c.state(slice_id), c.read_json(c.rec_dir(slice_id) / "frozen.json")
    if not frozen or st.get("phase") != "building":
        raise SystemExit(f"{slice_id} is not in the building phase ({st.get('phase')}): slice_start.py first.")
    seat = c.seat_settings("builder", st["setting"])
    findings = ""
    last = sorted(c.rec_dir(slice_id).glob("verify-*.json"), key=lambda p: p.stat().st_mtime)
    if last:
        v = c.read_json(last[-1]) or {}
        if v.get("verdict") != "pass":
            findings = "\n\nThe verifier's findings from the last round, to fix:\n" + json.dumps(v.get("findings"), indent=1)
    prompt = (f"You are the builder for slice {slice_id} (build {frozen['build']}), round {st['round']} of "
              f"{st['rounds_limit']}. Your worktree is {frozen['worktree']}, on branch {frozen['branch']}.\n\n"
              f"The brief:\n{brief_text(slice_id)}\n\nFrozen for this slice (you cannot change them):\n"
              f"- acceptance files: {frozen['acceptance_files']}\n- acceptance: {frozen['acceptance']}\n"
              f"- checks: {frozen['checks']}{findings}")
    wt = Path(frozen["worktree"])
    prompt += rulings_note(wt)
    log = c.rec_dir(slice_id) / f"builder-r{st['round']}-{uuid.uuid4().hex[:6]}.jsonl"
    res = launch("builder", st["account"], wt, prompt, seat["model"], seat["effort"],
                 {"OSPREY_SLICE": slice_id, "OSPREY_SLICE_WORKTREE": str(wt)}, log)
    sess = c.read_json(c.rec_dir(slice_id) / "sessions.json") or {"builder": [], "verifier": []}
    sess["builder"].append(res.get("session_id"))
    c.write_json(c.rec_dir(slice_id) / "sessions.json", sess)
    append_usage(slice_id, frozen["build"], "builder", st["account"], seat["model"], seat["effort"], res)
    red = c.read_json(c.rec_dir(slice_id) / "red_stop.json")
    tip = c.git(["rev-parse", frozen["branch"]], c.REPO)
    if c.account_stop(st["account"]):
        stop_slice(slice_id, f"account {st['account']} stopped mid-slice ({c.account_stop(st['account'])['error']}): "
                             "wait for it, or tell the line to carry the slice on the same account later?")
        return 1
    if red:
        stop_slice(slice_id, f"the builder could not get the checks green in {red['red_stops']} tries: "
                             "narrow the slice, or change its checks (your word)?")
        return 1
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
                  f"line, what is wrong and how you know). Put the commit {tip} in your answer.{rulings}")
        log = c.rec_dir(slice_id) / f"verifier-{focus}-{uuid.uuid4().hex[:6]}.jsonl"
        res = launch("verifier", account, vt, prompt, seat["model"], seat["effort"],
                     {"OSPREY_SLICE": slice_id, "OSPREY_SLICE_WORKTREE": str(vt)}, log,
                     ["--json-schema", json.dumps(VERDICT_SCHEMA)])
        append_usage(slice_id, frozen["build"], f"verifier:{focus}", account, seat["model"], seat["effort"], res)
        out = res.get("structured_output")
        if not isinstance(out, dict):
            try:
                out = json.loads(res.get("result") or "{}")
            except ValueError:
                out = {}
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
    c.write_json(c.rec_dir(slice_id) / f"verify-{tip}.json", record)
    if ok:
        c.set_state(slice_id, phase="verified", tip=tip)
        board()
        print(f"{slice_id}: the verifier passed {tip[:10]}. The conductor runs merge_slice.py merge {slice_id}.")
        return 0
    if st["round"] >= st["rounds_limit"]:
        first = record["findings"][0]["what"] if record["findings"] else "no verdict"
        stop_slice(slice_id, f"findings after {st['round']} round(s) (first: {first[:90]}): accept a narrower slice, "
                             "or allow another round?")
        return 1
    c.set_state(slice_id, phase="building", round=st["round"] + 1)
    board()
    print(f"{slice_id}: findings; back to the builder for round {st['round'] + 1}.")
    return 1


def conductor() -> int:
    seat = c.seat_settings("conductor")
    launch("conductor", c.account_for("conductor"), c.REPO, "", seat["model"], seat["effort"], {},
           c.DATA / "conductor" / f"{c.now()}.log", interactive=True)
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
