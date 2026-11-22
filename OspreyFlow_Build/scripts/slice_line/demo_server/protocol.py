"""What the demo server's early-warning runner and the Mac's early_warning.py agree on, in one place.

The owner's ruling 4 (DEMO_SERVER_EARLY_WARNING_BRIEF.md, 21 November 2026): the forced command takes exactly
`run` and `result <id>`, the id a fixed pattern of lower-case hexadecimal characters of fixed length; anything else is
refused and logged by its reason class and the length of what was received, never the text itself. The runner
(install.sh copies this file beside it) and the Mac script both import this module; neither writes the pattern again.

Standard library only, Python 3.8 or later: the server runs it under its own python3.
"""
from __future__ import annotations

import re

#: The runner's version, written into every result and every note.
RUNNER_VERSION = "ew-1"

#: A job id: 16 lower-case hexadecimal characters (secrets.token_hex(8)).
ID_LENGTH = 16
ID_PATTERN = "[0-9a-f]{%d}" % ID_LENGTH
#: The only two commands the forced command accepts, whole: anchored, one space, nothing before or after.
COMMAND = re.compile(r"\A(?:(run)|(result) (%s))\Z" % ID_PATTERN)

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

#: The caps the job runs under (systemd-run): 6 of 16 processors, 16 of 62 GB; nice 10; I/O best-effort, lowest.
CPU_QUOTA = "600%"
MEMORY_MAX = "16G"
NICE = 10
TEST_WORKERS = 6  # make test's pytest-xdist workers, matched to the CPU quota (the Mac's `auto` is its CPU count)

#: The refusal reason classes, as the refusal log writes them (never the received text).
REASONS = ("empty", "newline", "shape", "busy", "bundle-empty", "bundle-too-large", "bundle-unreadable",
           "bundle-heads", "bundle-prerequisites", "unresolved-tip", "outside-work", "no-cap", "no-such-job",
           "disk-floor", "port-in-use")


def parse_command(received: str | None) -> tuple[str, str] | tuple[None, str]:
    """('run', '') or ('result', <id>), or (None, <reason class>). `received` is SSH_ORIGINAL_COMMAND, read once."""
    if not received:
        return None, "empty"
    if "\n" in received or "\r" in received:
        return None, "newline"
    m = COMMAND.match(received)
    if not m:
        return None, "shape"
    if m.group(1):
        return "run", ""
    return "result", m.group(3)


def refusal_line(at: str, reason: str, received: str | None) -> str:
    """The log line for a refusal: when, the reason class, how long the command was. Never the command itself."""
    if reason not in REASONS:
        reason = "shape"
    return "%s\trefused\t%s\tlength=%d\n" % (at, reason, len(received or ""))
