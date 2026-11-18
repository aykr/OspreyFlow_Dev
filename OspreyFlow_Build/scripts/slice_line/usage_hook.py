#!/usr/bin/env python3
"""Usage and account-limit records for the slice line (README.md, "Accounts and usage").

Runs from the fixed place (~/.ospreyflow/slice-line/bin/usage_hook.py). Standard library; Python 3.9.

    usage_hook.py stop-failure   StopFailure: a rate limit or a signed-out account stops the seat's track
    usage_hook.py session-end    SessionEnd: the conductor's own tokens (and its scouts') as one usage row
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

BIN = Path.home() / ".ospreyflow" / "slice-line"
DATA = Path(os.environ.get("OSPREY_SLICE_HOME") or str(BIN))
ACCOUNT_STOPS = {"rate_limit", "authentication_failed", "oauth_org_not_allowed", "account_on_hold", "billing_error"}
HEADER = "at\tslice\tbuild\tseat\taccount\tmodel\teffort\tsession\tinput\tcache_create\tcache_read\toutput\tcost_usd\tfive_hour\tseven_day\n"


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def append_usage(row: list) -> None:
    f = DATA / "usage.tsv"
    if not f.exists():
        f.write_text(HEADER)
    with f.open("a") as fh:
        fh.write("\t".join(str(x) for x in row) + "\n")


def transcript_usage(path: Path) -> dict:
    tot = {"input": 0, "cache_create": 0, "cache_read": 0, "output": 0, "model": ""}
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return tot
    for ln in lines:
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        msg = d.get("message") or {}
        u = msg.get("usage") if isinstance(msg, dict) else None
        if d.get("type") == "assistant" and isinstance(u, dict):
            tot["input"] += u.get("input_tokens", 0) or 0
            tot["cache_create"] += u.get("cache_creation_input_tokens", 0) or 0
            tot["cache_read"] += u.get("cache_read_input_tokens", 0) or 0
            tot["output"] += u.get("output_tokens", 0) or 0
            tot["model"] = msg.get("model") or tot["model"]
    return tot


def window(account: str, name: str):
    """The account's share of a window, as its seat sessions' streams last reported it ("" when never reported)."""
    try:
        st = json.loads((DATA / "accounts" / (account + ".json")).read_text())
        return ((st.get("windows") or {}).get(name) or {}).get("utilization", "")
    except (OSError, ValueError):
        return ""


def conductor_row(tp: Path, session: str, account: str) -> None:
    """The conductor's own session as one usage row, its scouts' (subagent) transcripts summed in."""
    tot = transcript_usage(tp)
    sub = tp.with_suffix("") / "subagents"
    if sub.is_dir():
        for f in sub.glob("*.jsonl"):
            t = transcript_usage(f)
            for k in ("input", "cache_create", "cache_read", "output"):
                tot[k] += t[k]
    append_usage([now(), "(all)", "", "conductor+scouts", account, tot["model"], "", session, tot["input"],
                  tot["cache_create"], tot["cache_read"], tot["output"], "", window(account, "five_hour"),
                  window(account, "seven_day")])


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    seat = os.environ.get("OSPREY_SEAT", "")
    if not seat:
        return 0
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        event = {}
    account = os.environ.get("OSPREY_ACCOUNT", "")
    DATA.mkdir(parents=True, exist_ok=True)
    if mode == "stop-failure" and event.get("error") in ACCOUNT_STOPS:
        d = DATA / "accounts"
        d.mkdir(exist_ok=True)
        (d / (account + ".stopped.json")).write_text(json.dumps({
            "account": account, "error": event.get("error"), "at": now(), "seat": seat,
            "slice": os.environ.get("OSPREY_SLICE", ""), "message": (event.get("last_assistant_message") or "")[:300],
        }, indent=1))
    if mode == "session-end" and seat == "conductor":
        conductor_row(Path(event.get("transcript_path") or ""), event.get("session_id", ""), account)
    return 0


if __name__ == "__main__":
    sys.exit(main())
