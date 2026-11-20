# The owner's control panel

What a slice can build of decisions D24-D26 (18 November 2026). Standard library and PyYAML, run with OspreyFlow_Core's
python, from `OspreyFlow_Build`:

    python -m tools.control_panel                # http://127.0.0.1:8765/, the token made on first start

It saves the owner's changes to `dial.yaml` (`current`, `day`, `night`), `accounts.yaml` (a seat's or a track's
account) and `live_step.yaml` (`live_step`), and a stored switch for automatic balancing, **off by default and read by
nothing yet**. It shows each account's `five_hour` and `seven_day` windows (from `<data>/accounts/<account>.json`; the
key names are assumed from the stream, so a figure that is missing or not a share between nought and one reads "no
figure") and its usage totals from `<data>/usage.tsv`.

## The two calls

Both need `Authorization: Bearer <token>` and the panel's own `Host` (`127.0.0.1:<port>` or `localhost:<port>`).

* `GET /api/state`: the dial, the accounts, each account's windows and totals, the live step, the balancing switch and
  the last twenty changes.
* `POST /api/change` with `{"key": ..., "value": ...}`. Keys: `dial.current` (`auto` or a setting), `dial.day` and
  `dial.night` (a setting), `accounts.seats.<seat>` and `accounts.tracks.<n>` (an account name,
  `[a-z][a-z0-9-]*`), `live_step` and `balancing` (a JSON `true` or `false`). Anything else is refused with 400 and
  nothing is written. A value the scripts would silently fall back from is refused here.

Each change is one line of the file edited in place (the owner's comments stay), read back with the loader the scripts use
before it is saved, appended to `<data>/control-panel-changes.tsv` (time, key, old, new) and taken back if it could not be
logged. That log is not `owner-changes.tsv`: the merge script trusts that file for the owner's acceptances.

## What "agents refused" means here

It is a second layer. An agent runs as the same macOS user and can run any code, so the guard, which judges text,
cannot stop one reaching a port or a file. The refusal that holds is the token: it is made at
`~/.ospreyflow/control-panel/token` (mode 600, in a folder of mode 700), refused a place inside the repository, and never
printed, logged or sent back; an agent has no reason to be given it. The server will not start on a token that is
missing, under 32 characters or readable by others.

## Left to the owner's diffs

D26's balancing in `slice_start.py` and `common.py`; a guard rule refusing agents the panel's address and the token's
path; the dashboard's controls and the way the panel serves the dashboard folder.

The test is `tests/test_control_panel.py`. Each refusal in it is planted in the shape the server receives it, and a
second case removes the check and shows the same request writing (rule 15).
