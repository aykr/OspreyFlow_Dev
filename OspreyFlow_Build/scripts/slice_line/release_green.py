#!/usr/bin/env python3
"""A release needs GitHub green on the commit released (the owner, 20 November 2026; LINE_FIXES_4_BRIEF.md, 1d). GitHub
is no gate for a merge any more (merges go on the Mac's full gate alone); it still is for a release.

    release_green.py check <commit>    exit 0 when the latest completed run of ci on exactly that commit concluded
                                       success; exit 1, in words naming the commit, otherwise. The release paths call
                                       it: OspreyFlow_Build/tools/release_local.py and
                                       OspreyFlow_Build/scripts/publish_user_repo_update.sh

It asks gh `gh run list --commit <sha> --status completed --json conclusion,databaseId,attempt,...`. gh gives each
run with its latest attempt, so a red run that passed on its rerun counts as green. Only the `ci` workflow counts
(exit-tests is started by hand and tests something else); a green run on another commit, the parent included, does
not; none, a red one, or gh unreadable refuses. The standard library only, so the system's python3 runs it.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKFLOW = "ci"
FIELDS = "conclusion,databaseId,attempt,headSha,workflowName,url"


def refusal(commit: str) -> tuple[str | None, str]:
    """(why the release is refused, or None) and what GitHub said."""
    if not re.fullmatch(r"[0-9a-f]{40}", commit or ""):
        return f"{commit!r} is not a whole commit (40 hex characters): the release names exactly what it releases.", ""
    try:
        p = subprocess.run(["gh", "run", "list", "--commit", commit, "--status", "completed", "--limit", "50",
                            "--json", FIELDS], cwd=str(HERE), capture_output=True, text=True, timeout=120)
        if p.returncode != 0:
            raise ValueError(f"gh exit {p.returncode}: {(p.stderr or p.stdout).strip()[:200]}")
        runs = json.loads(p.stdout)
        if not isinstance(runs, list):
            raise ValueError("gh's answer is not a list of runs")
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        return (f"GitHub cannot be read ({e}), so commit {commit} is not shown green on GitHub: no release until it "
                "can be read and is green."), ""
    ours = [r for r in runs if isinstance(r, dict) and r.get("workflowName") == WORKFLOW and r.get("headSha") == commit]
    if not ours:
        return (f"no completed run of {WORKFLOW} on commit {commit} on GitHub: a release needs GitHub green on "
                "exactly the commit released (a green run on another commit, its parent included, does not count)."), ""
    last = max(ours, key=lambda r: int(r.get("databaseId") or 0))
    said = (f"GitHub's {WORKFLOW} run {last.get('databaseId')} (attempt {last.get('attempt')}) on commit {commit[:10]}: "
            f"{last.get('conclusion')} {last.get('url', '')}".rstrip())
    if last.get("conclusion") != "success":
        return (f"the latest completed run of {WORKFLOW} on commit {commit} is run {last.get('databaseId')} (attempt "
                f"{last.get('attempt')}): {last.get('conclusion')}, not success. Rerun it, or release a commit "
                f"GitHub passed. {last.get('url', '')}").rstrip(), said
    return None, said


def main(argv: list[str]) -> int:
    if argv[1:2] != ["check"] or len(argv) != 3:
        print("usage: release_green.py check <commit>", file=sys.stderr)
        return 2
    why, said = refusal(argv[2])
    if why:
        print(f"Refused: {why}", file=sys.stderr)
        return 1
    print(said)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
