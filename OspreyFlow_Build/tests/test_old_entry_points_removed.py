"""The old ways in are gone (`06_DECISIONS.md` ADR-114 decision 3, the owner's ruling "Remove them
outright", and Amendment 3 decision 7): one command, `ospreyflow`, replaces `make launch`, `make
refresh`, the launcher page and the Set-up console's permanent server.

What a mistake would do, and the case that catches it:
- a second way in left beside the command — `test_the_launcher_and_its_targets_are_gone`;
- the Set-up console still listening for good — `test_the_bare_harness_command_points_to_the_install_page`;
- a screen still telling people to run what no longer exists —
  `test_nothing_a_person_reads_names_make_launch_or_make_refresh`;
- the build's own rules still saying there is no command — `test_the_convention_names_the_command`.
"""

from __future__ import annotations

import re
import subprocess
import sys

from tools.layout import BUILD, CORE, ROOT


def test_the_launcher_and_its_targets_are_gone() -> None:
    assert not (CORE / "scripts" / "launch.py").exists()
    makefile = (CORE / "Makefile").read_text(encoding="utf-8")
    targets = set(re.findall(r"^([A-Za-z0-9_-]+):", makefile, re.MULTILINE))
    assert not {"launch", "refresh"} & targets
    assert (CORE / "scripts" / "refresh.py").exists(), "kept: `ospreyflow start --build` runs it"


def test_the_bare_harness_command_points_to_the_install_page() -> None:
    ran = subprocess.run([sys.executable, "-m", "harness"], cwd=CORE, capture_output=True, text=True,
                         check=False, timeout=60, env={"PYTHONPATH": f"{CORE}:{CORE / 'packages'}", "PATH": ""})  # fmt: skip
    assert ran.returncode == 2
    assert "ospreyflow install --gui" in ran.stdout + ran.stderr


def test_nothing_a_person_reads_names_make_launch_or_make_refresh() -> None:
    """The places a person is told what to run: the console's sign-in page, the command, the
    README and the demo guide. Code comments recording history are not instructions."""
    for path in (CORE / "harness" / "webapp_signin.py", CORE / "harness" / "webapp.py",
                 CORE / "README.md", CORE / "DEMO_GUIDE.md"):  # fmt: skip
        text = path.read_text(encoding="utf-8")
        for stale in ("make launch", "make refresh"):
            assert stale not in text, f"{path.name} still says {stale!r}"


def test_the_convention_names_the_command() -> None:
    rules = (BUILD / "process" / "CLAUDE.md").read_text(encoding="utf-8")
    assert "No `osprey` CLI yet" not in rules
    assert "ospreyflow" in rules
    assert (ROOT / "Makefile").exists()
