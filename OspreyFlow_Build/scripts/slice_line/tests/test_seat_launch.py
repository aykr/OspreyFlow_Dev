"""F1: a seat can start a Claude session the guard does not see (LINE_FAULTS_2026-11-18.md). Layer 1, the floor: the
guard's text match refuses each of the 24 variants measured on 18 November, planted in the shape check_bash receives,
in the conductor's seat (so no other rule can be the one refusing). Nine were refused then, fifteen were not.
"""
from __future__ import annotations

import pytest

from test_gates import bash, refused, world  # noqa: F401  (world is a fixture)

REFUSED_ON_18_NOVEMBER = ["claude -p x", "env claude -p x", "command claude -p x", "nohup claude -p x &",
                          "time claude -p x", "sudo claude -p x", "exec claude -p x", "echo x | xargs claude -p",
                          "claude\t-p x"]
#: The table's eleven shapes that were let through (a quoted name counted once per quote), and four more of the same
#: kinds (a name split by empty quotes, a backslash, Python concatenation spaced out), to make the 24.
ALLOWED_ON_18_NOVEMBER = ["/usr/local/bin/claude -p x", '"claude" -p x', "'claude' -p x", "$(which claude) -p x",
                          "claude;ls", "bash -c 'claude -p x'", "npx @anthropic-ai/claude-code -p x",
                          "node /opt/homebrew/lib/node_modules/@anthropic-ai/claude-code/cli.js -p x",
                          "~/.claude/local/claude -p x", "C=cl; ${C}aude -p x",
                          "python3 -c \"import os; os.execvp('cl'+'aude', ['x', '-p', 'y'])\"",
                          "python3 -c \"import subprocess; subprocess.run(['cl' + 'aude', '-p', 'y'])\"",
                          'c""laude -p x', "cl''aude -p x", "\\claude -p x"]
STILL_ALLOWED = ["cat .claude/agents/slice-builder.md", "ls ~/.claude-sol/projects", "git log --oneline -- .claude/settings.json",
                 "cat ~/.claude-sol/settings.json"]


def test_the_twenty_four_variants_of_18_november_number_twenty_four():
    assert len(REFUSED_ON_18_NOVEMBER) == 9 and len(ALLOWED_ON_18_NOVEMBER) == 15


@pytest.mark.parametrize("cmd", REFUSED_ON_18_NOVEMBER + ALLOWED_ON_18_NOVEMBER)
def test_seat_launch_every_variant_is_refused(world, cmd):
    p = bash(world, cmd, seat="conductor")
    assert refused(p) and "started only by run_seat.py" in p.stderr, (cmd, p.stderr)


@pytest.mark.parametrize("cmd", STILL_ALLOWED)
def test_seat_launch_reading_the_config_folders_is_not_a_launch(world, cmd):
    assert bash(world, cmd, seat="conductor").returncode == 0, cmd
