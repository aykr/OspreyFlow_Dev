# Slice BL7 · BL7 · The owner's control panel (the part a slice can build)

- **Build id:** BL7
- **Dial setting:** balanced
- **Rounds limit:** 2
- **After:** nothing (unhooked by the owner, 19 November 2026: it ran after BL6 only for ordering)
- **Status of this brief:** APPROVED by the owner, 18 November 2026, with the split: a slice builds the panel under
  `tools/control_panel/`; balancing, the guard rule and the dashboard controls come to the owner as diffs.

## What

Decisions D24-D26 (`DECISIONS_2026-11-18.md`): a local program on the Mac that serves the dashboard and saves the
owner's changes to the accounts (with each account's usage beside it), the dial, the live step, and a switch for
automatic balancing (off by default); reachable only from the Mac; every change logged; agents refused.

**Scouted 18 Nov: BL7 cannot be one slice.** The guard and the merge script refuse a slice that edits
`scripts/slice_line/`, `.claude/`, the three yaml files, or anything under `Claude outputs/` (git-ignored, so in no
worktree). So this slice builds only the part that can live in the repository: `OspreyFlow_Build/tools/control_panel/`
(standard library, Python 3.12, tests beside it):

- an HTTP server bound to `127.0.0.1` only, refusing any other `Host` and any request without the panel's token;
- reads and writes the three yaml files in the schemas the scripts read (`common.py:87-116`, `merge_slice.py:180-191`),
  validating before it writes (an unknown `current`, a non-bool `live_step`, an account name outside `[a-z][a-z0-9-]*`
  are refused, where the scripts today silently fall back);
- shows each account's windows from `~/.ospreyflow/slice-line/accounts/<account>.json` (`five_hour`, `seven_day`
  utilisation; the key names are assumed from the stream, not checked against a captured event: the panel says "no
  figure" rather than guess) and `usage.tsv`;
- appends every change to an owner-changes log (old value, new value, time) in the data folder;
- the balancing switch is a stored setting only: it is off by default and nothing reads it yet.

The panel's token lives outside anything the repository or an agent's tools may read; "agents refused" is not
enforceable by the text-judging guard alone (an agent can run any code as the same macOS user), so the brief says what
it is: a second layer. The real refusal is a secret an agent has no reason to be given.

**Owner's diffs, not this slice** (written by the owner's route after, like `make-ci-wiring.diff`): D26's balancing in
`slice_start.py`/`common.py`; a guard rule refusing agents the panel's address and token path; the dashboard's controls
and the way the panel serves the dashboard folder.

## Acceptance test

New `OspreyFlow_Build/tests/test_control_panel.py` (pure; a server on an ephemeral port in the test): a request
from a non-loopback `Host`, with no token, or with a wrong token is refused and writes nothing; a valid change is
written and logged; an invalid value is refused and the file is byte-identical afterwards; the balancing switch defaults
off; the three files round-trip through the scripts' own loaders (`common.load_dial`, `load_accounts`,
`merge_slice.live_step_setting`) so the panel cannot write what they refuse. Rule 15: each refusal is planted in the
shape the server receives it, and the file shows red with the check removed.

## Checks

The acceptance file and `tools` lint; pure only. No port is opened on a non-loopback address; no store is reached.

## Out of scope

Anything under `scripts/slice_line/` or `.claude/`; the three yaml files themselves; the dashboard HTML; D26's wiring.
