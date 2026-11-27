"""A run of the suite that crosses midnight (UTC) changes no result (65; CO3b's merge gate of 27 November 2026).

CO3b's gate ran the line's suite from 00:00 to 00:32 UTC, and three tests failed that pass by day:
- test_owner_line_waiting.py's two cases built "yesterday" from the clock (day(-1)), not from the run's one date
  (test_gates.TODAY): after midnight "yesterday" was the run's own day;
- test_round_after_refusal.py's budget case logged a standing use on the run's day, and the line counted a standing
  permission's uses by the clock's day (common.py, now()[:10]), not by resume.today(), the one the test world dates.

The run's one date (LINE_FIXES_5_BRIEF.md, 9) is taken once; the scripts in a test world read it too (TEST_TODAY), and
every date the line counts by comes from one function. Here the suite's date is set to yesterday's
(SLICE_LINE_TEST_TODAY), as for a run collected before midnight and run after it, and the modules that read a day run
again under it.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DAYS = ["test_owner_line_waiting.py", "test_round_after_refusal.py", "test_clear_line_stops.py", "test_standing.py", "test_resume.py"]


def yesterday() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(time.time() - 86400))


def test_the_modules_that_read_a_day_pass_when_the_run_started_before_midnight():
    files = [f for f in DAYS if (HERE / f).exists()]
    assert "test_owner_line_waiting.py" in files and "test_round_after_refusal.py" in files, files
    env = {**os.environ, "SLICE_LINE_TEST_TODAY": yesterday(), "PYTHONDONTWRITEBYTECODE": "1"}
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *files], cwd=HERE, env=env,
                       capture_output=True, text=True, timeout=1500)
    tail = "\n".join(l for l in p.stdout.splitlines() if l.startswith(("FAILED", "ERROR")) or " passed" in l or " failed" in l)
    assert p.returncode == 0, tail


def test_no_test_takes_a_day_from_the_clock_but_the_runs_one_date():
    """Every test takes its dates from test_gates.TODAY (a day before it or after it is counted from that date)."""
    found = []
    for f in sorted(HERE.glob("test_*.py")):
        if f.name in ("test_gates.py", "test_midnight.py"):
            continue
        for n, line in enumerate(f.read_text().splitlines(), 1):
            if re.search(r'strftime\("%Y-%m-%d",\s*time\.gmtime\((?!\d)', line) or "date.today()" in line:
                found.append(f"{f.name}:{n}: {line.strip()}")
    assert found == []
