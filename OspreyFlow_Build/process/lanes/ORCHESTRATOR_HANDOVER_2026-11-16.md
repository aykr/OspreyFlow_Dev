# The orchestrator's handover · 16 November 2026, ~15:30Z (after v0.6.0's release)

For a new orchestrator session on the **sol** account. Read this whole, then `process/CLAUDE.md` (rules 1-15, rule
14 above all), the top of `process/lanes/MORNING.md`, `v060/RULINGS.md` (the v0.6.1 list and the standing rules)
and `v060/DEPUTY_HANDOVER_2026-11-16.md`.

## Where things are
- **v0.6.0 is released**: product commit 2d96da7 (from dev 529f0f4) on aykr/OspreyFlow, tag v0.6.0 in both
  repositories, release workflow 43892824809 green, https://github.com/aykr/OspreyFlow/releases/tag/v0.6.0. It
  includes the Glass rows (built as v0.6.1's first item, joined v0.6.0 by the owner's word). Package test: stage 4
  passed on b6d33ce, which stands for 529f0f4 by the owner's ruling (the diff limited to keyboard tests and records;
  the built dist byte-identical). Known issue: the report sync restarts once if the Conduit is unreachable, recovers.
- **Step 10 (the client's view)**: platform-b is running it on the server (Docker is off on the Mac): anonymous
  pulls, `harness.signatures`, `ospreyflow update --check`. Its one line comes to case and the orchestrator.
- **The GOV.UK rebuild**: case (deputy) is resuming the demo lane on sol on `demo/REBUILD_2026-11-18.md`. When its
  checks pass: the Gemini key command at the top of MORNING.md, the item back in owner_due.tsv, the owner told.
  **From the moment the owner enters the key the GOV.UK demo is protected**: nothing changes or restarts it (apply,
  restart, rebuild, update, settings, restore, port, certificate, Part 3 cutover step) without telling the owner
  first in one line (what, downtime, the way back) and their word. Reading it is fine.
- **Part 3 (ospreyflow.app)**: platform, parked at lane/platform-part3. O2 to O5 given (O4's email is never written
  in the repository; O5 = everyone may reach 443). The owner has added ospreyflow.app's A records (@, id, bi to
  185.154.146.242); the old ALIAS and wildcard CNAME to pixie.porkbun.com were suggested for deletion. Next: stage P
  (the proof on the test server, ~3 h, under a lease), then the owner's cutover window and word on each step that
  touches GOV.UK, then O8 (visitors).
- **Websites** ospreyflow.org/.net: the owner is taking them down to internal Google Sites; leave the GitHub side
  alone and publish nothing to them until the owner says.

## Merge after the release (case was asked to do these)
- platform-b's tooling branch `lane/platform-b-v060-chart-before-listing` (dashboards check fixes, ADR-150 Am 3,
  the scenario test's search waits, the media write);
- rules-b's `lane/rules-b-v060-focus-move-audit` (74cc258, test-only).

## v0.6.1 (the list is in v060/RULINGS.md)
Includes: the report sync surviving a Valkey/Conduit error; a real TLS+auth Valkey test; scoping dashboard builders
(own ADR, rule 3); the drawn-merge focus move (WCAG 3.2.2); T on the Map's container; spec 08's seeded rows on poc;
the guide sentences (index lag, a board offered once it holds a chart); app-only v1.0 token refusal words; the
map-view keyboard flake (CARRIES); the Admin forms, R7 step 2, people by name, Bedrock EU profile, CI speed-ups.

## Lanes (sockets change when sessions restart: map pid to lane with the loop in MORNING/CLAUDE notes)
case (deputy, sol), case-b (sol, ready/idle), platform (sol, Part 3 parked), platform-b (sol, step 10), rules-b
(sol, idle). Each lane's account is in ~/.ospreyflow/lanes/<lane>.account.

## Standing rules from the owner (16 Nov)
- Take the recommended option and report it after; the owner's own: GOV.UK disruption, secrets they type, permission
  refusals, dropping or deferring what an ADR or client page requires.
- Long checks run in parallel; the final or public step waits for every check on the same commit.
- One push at a time (a push cancels the running CI). Never commit OspreyFlow_Core/osprey.yaml. .github/Makefile
  changes need the owner (a `git apply` diff). Never pkill by pattern. Pure test lines carry
  `ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9`. Keep the heartbeat true (route.tsv, progress.tsv, owner_due.tsv, stages).
- A lane's "landed" is reported only after the hash exists; confirm a lane ACKed (and beat) before relying on it.
