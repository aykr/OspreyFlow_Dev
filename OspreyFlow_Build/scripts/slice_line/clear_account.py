#!/usr/bin/env python3
"""Clear a stopped account (LINE_FIXES_3_BRIEF.md, 1f, "Clearing the account's stop"; the owner's order of 19 November
2026, evening). The owner's, and refused to every agent by the guard (OWNER_SCRIPTS), as refreeze.py is.

    clear_account.py <account>      authority: the owner's line `clear-account <account> <YYYY-MM-DD>` in resume.tsv

An account is stopped by the marker `<account>.stopped.json` in the data folder's accounts/ (written by usage_hook.py at
a refused session, or by run_seat.py when a seat's tries are used); while it is there, run_seat.py's preflight refuses
every seat on the account. Until now the only way back was deleting the file by hand. This probes the account with one
cheap call (one turn, the smallest model, no tools needed) and removes the marker only if the call is accepted (not a
seat failure as run_seat.py reads one); the use is logged in owner-changes.tsv. Nothing changes on any refusal.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402
import run_seat as rs  # noqa: E402
from resume import Refused, resume_lines, today  # noqa: E402

PROBE = ["-p", "Reply with the one word: ok.", "--max-turns", "1", "--output-format", "json", "--model", "haiku"]
PROBE_SECONDS = 180


def clear(account: str) -> list[str]:
    known = c.known_accounts()
    if account not in known:
        raise Refused(f"{account!r} is not an account the owner's accounts.yaml names ({', '.join(sorted(known))}). "
                      "Nothing changed.")
    want = ["clear-account", account, today()]
    tag = f"resume.tsv {today()} clear-account {account}"
    have = sum(1 for parts in resume_lines() if parts == want)
    used = sum(1 for r in c.owner_changes() if r["action"] == "clear-account" and r["detail"].startswith(tag + ":"))
    if not have:
        raise Refused(f"no line '{chr(9).join(want)}' in {c.RESUME_FILE} (the owner's word, today, UTC): nothing "
                      "changed, and no call made.")
    if used >= have:
        raise Refused(f"the owner's line '{chr(9).join(want)}' in resume.tsv is already used ({used} use(s) logged in "
                      "owner-changes.tsv): one line, one use. Nothing changed.")
    stop = c.account_stop(account)
    if not stop:
        raise Refused(f"account {account} is not stopped: nothing to clear.")
    with tempfile.TemporaryDirectory() as d:
        try:
            p = subprocess.run([c.CLAUDE, *PROBE], cwd=d, env=c.claude_env(account), capture_output=True, text=True,
                               timeout=PROBE_SECONDS)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise Refused(f"the probe of account {account} did not answer ({e}). The stop is kept.")
    try:
        res = json.loads(p.stdout)
    except ValueError:
        res = None
    if p.returncode != 0 or not isinstance(res, dict):
        raise Refused(f"the probe of account {account} did not answer as a session does (exit {p.returncode}): "
                      f"{(p.stdout + p.stderr).strip()[:300]}. The stop is kept.")
    why = rs.seat_failure(res, wants_verdict=False)
    if why:
        raise Refused(f"the probe of account {account} was refused: {why}. The stop is kept.")
    (c.DATA / "accounts" / f"{account}.stopped.json").unlink()
    c.log_owner_change("-", "clear-account", f"{tag}: account {account} cleared; it was stopped ({stop.get('error')} "
                                             f"at {stop.get('at')}); the probe was accepted (session "
                                             f"{str(res.get('session_id', ''))[:8]})")
    return [f"account {account} is cleared: seats may start on it again."]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("account")
    a = ap.parse_args()
    try:
        said = clear(a.account)
    except Refused as e:
        print(f"Refused: {e}", file=sys.stderr)
        return 1
    print("\n".join(said))
    subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "board.py"), "--quiet"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
