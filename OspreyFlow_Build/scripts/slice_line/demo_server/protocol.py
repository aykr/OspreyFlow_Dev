"""What the demo server's early-warning runner and the Mac's early_warning.py agree on, in one place.

The owner's ruling 4 (DEMO_SERVER_EARLY_WARNING_BRIEF.md, 21 November 2026): the forced command takes exactly
`run` and `result <id>`, the id a fixed pattern of lower-case hexadecimal characters of fixed length, and (009) `stack
<slice> <slice> [<slice>]`, two or three slice ids in merge order; anything else is
refused and logged by its reason class and the length of what was received, never the text itself. The runner
(install.sh copies this file beside it) and the Mac script both import this module; neither writes the pattern again.

Standard library only, Python 3.8 or later: the server runs it under its own python3.
"""
from __future__ import annotations

import re

#: The runner's version, written into every result and every note.
RUNNER_VERSION = "ew-2"  # ew-2 (009): stack runs, and one check per target in the result

#: A job id: 16 lower-case hexadecimal characters (secrets.token_hex(8)).
ID_LENGTH = 16
ID_PATTERN = "[0-9a-f]{%d}" % ID_LENGTH
#: A slice id as the line writes them (PL4d3e, IS5a0, DC1c): letters and digits, at most 16.
SLICE_PATTERN = "[A-Za-z0-9]{1,16}"
#: How many slices one stack run tests (009: three to begin with), and so how many jobs run at once.
MAX_STACK = 3
MAX_JOBS = 3
#: The only three commands the forced command accepts, whole: anchored, one space, nothing before or after.
COMMAND = re.compile(r"\A(?:(run)|(result) (%s)|(stack)((?: %s){2,%d}))\Z" % (ID_PATTERN, SLICE_PATTERN, MAX_STACK))

#: Every container, network and volume the runner would start carries this prefix and these labels; the clean-up
#: command removes only what carries both. (Under the owner's ruling 1 the runner starts none: it has no Docker.)
PREFIX = "osprey-early-"
LABEL = "osprey.early=1"
#: The marker comment that ends the runner's one authorized_keys line; the clean-up command removes the line by it.
KEY_MARKER = "osprey-early-warning-key"

#: The limits the forced command cannot carry by itself (the brief's "what cannot be done as written").
MAX_BUNDLE_BYTES = 1024 * 1024 * 1024  # 1 GiB: a full bundle of main's history, with room
MAX_RUN_SECONDS = 3 * 60 * 60  # 3 hours: the Mac's full run is about one
MIN_FREE_BYTES = 40 * 1024 ** 3  # 40 GB free before a run starts (372 GB free on 21 November 2026)

#: The caps each job runs under (systemd-run), with up to three at once (009): 4 of 16 processors and 12 of 62 GB
#: each, so three take at most 12 processors and 36 GB and the demo's containers keep 4 processors and 26 GB whatever
#: the jobs do; nice 10; I/O best-effort, lowest. (One job alone had 6 and 16G before 009.)
CPU_QUOTA = "400%"
MEMORY_MAX = "12G"
NICE = 10
TEST_WORKERS = 4  # make test's pytest-xdist workers, matched to the CPU quota (the Mac's `auto` is its CPU count)

#: The refusal reason classes, as the refusal log writes them (never the received text).
REASONS = ("empty", "newline", "shape", "busy", "bundle-empty", "bundle-too-large", "bundle-unreadable",
           "bundle-heads", "bundle-prerequisites", "unresolved-tip", "outside-work", "no-cap", "no-such-job",
           "disk-floor", "port-in-use")


def parse_command(received: str | None) -> tuple[str, str] | tuple[None, str]:
    """('run', ''), ('result', <id>) or ('stack', '<slice> <slice> ...'), or (None, <reason class>). `received` is
    SSH_ORIGINAL_COMMAND, read once."""
    if not received:
        return None, "empty"
    if "\n" in received or "\r" in received:
        return None, "newline"
    m = COMMAND.match(received)
    if not m:
        return None, "shape"
    if m.group(1):
        return "run", ""
    if m.group(4):
        order = m.group(5).split()
        if len(set(order)) != len(order):
            return None, "shape"  # one slice twice is no merge order
        return "stack", " ".join(order)
    return "result", m.group(3)


def refusal_line(at: str, reason: str, received: str | None) -> str:
    """The log line for a refusal: when, the reason class, how long the command was. Never the command itself."""
    if reason not in REASONS:
        reason = "shape"
    return "%s\trefused\t%s\tlength=%d\n" % (at, reason, len(received or ""))
