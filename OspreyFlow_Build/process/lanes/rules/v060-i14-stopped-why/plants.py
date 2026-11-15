"""Red first (rule 15) for v0.6.0 #14, What raises alerts says why a hotlist or watch stopped: each
piece planted out alone at its call site, its test red, the file restored from its saved text (never
by git) and the test green again. Offline, closed ports. Run from the repository root:

    PYTHONPYCACHEPREFIX=$(mktemp -d) OspreyFlow_Core/.venv/bin/python \\
        OspreyFlow_Build/process/lanes/rules/v060-i14-stopped-why/plants.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
CORE = ROOT / "OspreyFlow_Core"
WS = CORE / "apps/workspace"
ROUTE = CORE / "services/api/alert_sources.py"
PANEL = WS / "src/alerts/AlertSourcesPanel.tsx"
GUIDE = CORE / "docs/user-guide.md"
API_TEST = "../OspreyFlow_Build/tests/services/api/test_alert_sources_stopped_why.py"
GUIDE_TEST = "../OspreyFlow_Build/tests/test_user_guide_alert_sources_stopped_why.py"
PANEL_TEST = "src/alerts/OneQueue.test.tsx"

#: (name, file, planted out, replacement, how to run its test: ("py", path::test) or ("js", -t))
PLANTS = [
    ("S1 a stopped hotlist's reason dropped at the route", ROUTE,
     '            stopped_why=hotlist.stopped_why if hotlist.status != "active" else None,\n', "",
     ("py", f"{API_TEST}::test_a_stopped_hotlist_and_watch_say_why_in_the_owner_s_words")),
    ("S2 a stopped watch's reason dropped at the route", ROUTE,
     '            stopped_why=monitor.stopped_why if monitor.status != "active" else None,\n', "",
     ("py", f"{API_TEST}::test_a_stopped_hotlist_and_watch_say_why_in_the_owner_s_words")),
    ("S3 the panel shows Stopped without its reason", PANEL,
     '                    {key === "state" && s.state === "stopped" && s.stopped_why && (\n',
     '                    {false && key === "state" && s.state === "stopped" && s.stopped_why && (\n',
     ("js", "shows a stopped hotlist's and watch's reason beside Stopped")),
    ("S4 the guide's sentence gone", GUIDE,
     "**What raises alerts** says the same words under *Stopped* beside each of your stopped hotlists and\n",
     "**What raises alerts** shows *Stopped* beside each of your stopped hotlists and\n",
     ("py", f"{GUIDE_TEST}::test_the_guide_says_what_raises_alerts_shows_why_and_a_rule_says_nothing_more")),
]

ENV = {**os.environ, "OSPREY_PORTS_SLOT": "9", "ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992",
       "POSTGRES_PASSWORD": "throwaway", "VALKEY_PORT": "59993", "CLICKHOUSE_HTTP_PORT": "59994"}  # fmt: skip
ENV.pop("OSPREY_LANE", None)


def run(how: tuple[str, str]) -> tuple[bool, str]:
    kind, target = how
    if kind == "py":
        done = subprocess.run([".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-p",
                               "no:cacheprovider", "-q", target], cwd=CORE, env=ENV,
                              capture_output=True, text=True)  # fmt: skip
    else:
        done = subprocess.run(["npx", "vitest", "run", PANEL_TEST, "-t", target], cwd=WS, env=ENV,
                              capture_output=True, text=True)  # fmt: skip
    lines = [x for x in done.stdout.splitlines() if x.strip()]
    tail = [x for x in lines if "passed" in x or "failed" in x or "Tests" in x][-1:] or lines[-1:]
    return done.returncode == 0, " ".join(tail).strip()


def main() -> int:
    bad = 0
    for name, path, old, new, how in PLANTS:
        text = path.read_text(encoding="utf-8")
        ok, summary = run(how)
        if not ok:
            print(f"{name}: BROKEN - its test is red before the plant: {summary}")
            bad += 1
            continue
        if text.count(old) != 1:
            print(f"{name}: NOT PLANTED - the text is not in the file once")
            bad += 1
            continue
        try:
            path.write_text(text.replace(old, new), encoding="utf-8")
            ok, summary = run(how)
            print(f"{name}: {'GREEN (a plant its test does not see)' if ok else 'RED'} - {summary}")
            bad += ok
        finally:
            path.write_text(text, encoding="utf-8")
        ok, summary = run(how)
        print(f"  restored: {'GREEN' if ok else 'RED'} - {summary}")
        bad += not ok
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
