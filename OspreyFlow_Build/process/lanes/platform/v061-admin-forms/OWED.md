# v061-admin-forms: what is owed (carried from HANDOFF.md, retired 15 Nov 2026)

**Done:** the model form's first slice (ADR-135 Am 14 points 1-8), rulings 18-20 (no unchecked add; edit and new
key checked; point 9), the owner's key review and rulings 21-28 (point 10). Offline gates green at fc77f2a:
pytest 728 (fails only Postgres-live and the old rule-editor case), vitest 3615, plants 21/21 + 17/17 + P8 3/3,
keyboard 20/20 and axe 60/60 at slot 9. Records: `process/lanes/platform/v061-admin-forms/` (red-first.txt,
plants_*.py and *_run.txt, ACTION_REGISTRY.diff with 6 ids, EVERY_HARNESS.diff with 4 states).

**Owed, in order, once the orchestrator says the package test has ended** (ask it for the server queue first):
1. Q2, ruling 27: one measured run on the demo's real LiteLLM at its log level with a SYNTHETIC key; search its
   logs and the credentials row; if a credential body is logged, lower that logger in the rendered gateway
   settings, held by a test reading the rendered config.
2. `make test` and `make -k ci` on the server, including the live `test_route_rights.py` cases (Postgres).
3. A live LiteLLM run under a lease (`stack_lease.sh`): check, Add, edit with a moved address, a new key, the
   one-minute cooldown after a refusal, a duplicate credential name (the stand-in does not model its refusal).
4. Then ready-to-merge to the orchestrator; leave the branch as gated until it answers.
5. Then **Part 3, the second demo (ospreyflow.app)**, owner's ruling 16: about 28 h ±5, its own model beside Gemini,
   the shared Ollama kept. Read the brief the orchestrator gives; do not start before it says.

**For the orchestrator at merge:** apply the two diffs; regenerate placesByRole.json; move the deployment.py helper
out of 6bc6eae; the CARRIES row for route-coverage-check's reverse check.

**Do not redo:** the shapes, refusals and plants above; key_moved stays unchecked (ruling 21); the cluster Secret
keeps the key (ruling 28: do not touch cluster_install.py). osprey-small is never this lane's.

## Brought onto main by slice AD1a (20 November 2026): what the merge settled, and what is still owed

**Settled in AD1a (the server half, merge 6f4b918 and after):** the branch merged into `lane/slice-AD1a` with the screen's
files kept at main's; ADR-135 Amendment 14 kept as 14 (reservation row: lane `v062 AD1a`, written); the plants re-run on main's
code, 21 of 21 and 17 of 17 red (`plants_run_on_main.txt`, `plants_review_run_on_main.txt`). "Move the deployment.py helper out of
6bc6eae" needs nothing on main: main already holds `_a_key_in_the_path` identically and the merge added only
`model_looks_like_a_key` and `label_looks_like_a_key` beside it, once. The `CARRIES` row for the route-coverage reverse check
is not needed on main: the check reports 431 routes, none allowlisted, no new drift.

**Still owed, and not AD1a's:**
1. **Q2 (the owner's key review, question 2, ruling 27): one measured run on the demo's real LiteLLM at its log level with a
   synthetic key**, searching its logs and the credentials row. The live step is off (`process/lanes/v062/live_step.yaml`), so
   this is owed, not run; a release is refused until it has run.
2. The live cases of `tests/services/api/test_route_rights.py` (Postgres): three need a store and were not run in AD1a (the two
   pure cases pass, among them `test_every_route_names_the_right_the_table_gives_it` for the three check routes).
3. A live LiteLLM run under a lease (check, Add, edit with a moved address, a new key, the one-minute cooldown, a duplicate
   credential name).
4. **AD1b** (the screen): the two `.diff` files here (`ACTION_REGISTRY.diff`, `EVERY_HARNESS.diff`), the screen
   files, **the removal of the `models/checks` entry in `NOT_A_SECTION_S` (`test_admin_sections.py`)** (AD1a added it for the three
   check routes because no screen calls them yet; once `Models.tsx` does, the test's last loop goes red until the entry is removed), and P8's browser run (`plants_p8_run.txt`). Main's screen still calls the removed `POST /v1/admin/models/engines`: it
   compiles against the new generated types and its tests pass, but its Add fails at run time until AD1b lands, so AD1a and AD1b
   merge back to back.
5. **AD1c:** Fix D, the defaults and limits routes' words, `redacted()`, P1 for Edit and P9 for a query string.

**Round 2 (20 November 2026):** `placesByRole.json` was generated on AD1a's branch by `OSPREY_WRITE_PLACES_BY_ROLE=1` on
`test_place_routes.py::test_the_record_of_places_by_role_is_the_routes`, never by hand; it is regenerated from main's state, never merged,
when main is brought in. AD1b does not regenerate it unless its screen changes a route.

**Round 3 (20 November 2026): fixed key-shaped strings brought in, said here (the brief's rule: not carried silently).** The
branch's new acceptance tests hold fixed strings in the shape of a provider key (the prefix `s`, `k`, hyphen), all synthetic
and none a real key, and the owner's rule for keys is that tests make theirs at run time. They are in files frozen for AD1a
(the acceptance files cannot be changed, so AD1a did not change them): `test_model_engine_checks.py` (`PLANTED` at line 42, the
literals at lines 148, 168 and 190, `WRONG` at 445, `second` at 551), `test_model_key_review.py` (`QUOTED` at 67, `PLANTED` at
216) and `test_model_keys_commands.py` (`MASTER`, `KEY` and `REFUSED`, lines 28 to 30). The files AD1a does not freeze that hold
the same shape were on main already (`test_model_admin_routes.py`'s `GOOD` and its neighbours). **Owed, for the owner or a slice
that unfreezes them:** replace each by a key made with `secrets.token_hex` in a fixture, and re-run the plants. The
two tests AD1a adds in this round (`test_model_edit_failure_keeps_key_off_old_address.py`, `test_engine_kind_description.py`) make theirs
at run time or hold none.

**Round 3 fixes:** (1) an edit that moves the address and fails after its new key is in the gateway now removes the credential and
records the engine's key lost (`_drop_the_moved_key`), so the old address is never sent a key typed for the new one; the old key
was replaced and cannot be restored (write-only). Red first, both failure ways, in
`test_model_edit_failure_keeps_key_off_old_address.py`. (2) the `kind` description, the generated types, both administration guides' reference rows and
the `ospreyflow models` row say what Amendment 14 decided.

**Round 3, second pass (20 November 2026):** (3) a *successful* moved edit no longer sends the new key to the old address
for the moment between the key becoming the credential and the entries being rebuilt: the engine's entries are deleted
first (`_withdraw_entries`), so the engine is briefly unavailable, never served by the wrong key. Red first in
`test_a_moved_edit_never_sends_the_new_key_to_the_old_address_even_while_it_is_made` (a call made between the key and the
rebuild, by wrapping `_reconcile`). ADR-135 Amendment 14 point 9 says so. (4) `test_admin_models_extraction_engine.py`'s
body scan now reads FastAPI's typed body parameters too, so a write route with `body: SomeInput` and no `request` is read,
never passed over; shown red on planted scratch routes (the typed one, one wrapping a model, one reading by hand).

**Round 6 (20 November 2026): main taken in, and the 38-row key-path table held by one design.** Merge `1427b57` (main, with SE5, taken
in; `placesByRole.json` regenerated from main's state by `OSPREY_WRITE_PLACES_BY_ROLE=1`, never merged; the administration guide's
rows are 2.29 and 2.30 above main's 2.28, its PDF and manifest reprinted for that guide alone). The design is in
`services/api/model_admin.py` (`_reconcile`, `_change`, `_put_key`, `_delete_credential_with_intent`) and is held by
`tests/services/api/test_model_key_paths.py`, one case per row, red first on 1427b57 (`plants_key_paths_run.txt`). SE5's
`test_model_address_change_failure.py` is kept, every case, brought onto this edit path (an engine added by a check and Add; a moved
address given with its key; the fault planted at the live call, not the check's probe; "the process stops" a real stop).
**Owed from this round:** start-up reads no credential (`GET /credentials` answers with part of the key), so an engine whose
record says a key is set and whose credential is gone for a reason **no code of the Conduit wrote** (the gateway's own database
lost it) is still found only when its entries are also gone (the old start-up rule); every removal the Conduit makes now writes
its intent first, so the states the Conduit itself can leave are all "lost". An unpriced rebuild killed by a process stop is marked
lost at the next start (the key to be entered again), not held "rebuilding": a record of that intent is not kept.

**Round 7 (20 November 2026): the owner's ruling on the round-6 table.** One mechanism replaces the "lost mark as intent" of round 6: **a
note of intent** (`ModelSettings.intents`, in the models file) is saved before any credential is deleted or stored and cleared when the
change is complete; start-up marks unavailable every engine with a note outstanding, and every change and every undo settles it first
(`ModelAdmin._resolve`: the credential removed, the key recorded lost, a check made for a credential that is gone removed, the note
cleared; a removal the gateway refuses leaves the note and the engine withheld). Places: an edit moved or not, a rotation, *Remove key*,
*Remove engine*, a cancelled check, a check's own credential and a check's probe. A moved edit withdraws the engine's old entries
**before** it records or removes anything (row 40); an edit that carries a key, a key set and a check for a new engine each withdraw every
disagreeing entry before a key is stored (row 28 on the edit path and on the check). "Put back" is said only when the entries and the
credential were. Specification corrected: ADR-135 Amendment 14 point 9 now gives the owner's ruling and why no credential is listed.
Held by `tests/services/api/test_model_key_paths.py`, red first on `c66961a` (`plants_key_paths_run.txt`, "Round 7").
**Owed from this round:**
- A credential that vanishes for a reason **no code of the Conduit wrote** (the gateway's own database lost it) leaves no note, so start
  does not find it while the entries stand (the owner's ruling: no credential is listed, because the listing returns part of each key).
  The next key set, or an entry made again, repairs it.
- The sweep's removal of a lapsed check (`_expired`) has no note: the record it leaves is itself lapsed, so it can never be added and
  nothing is offered on a missing credential; the next sweep removes both again.
- With **no models file** a check's probe credential has no note (writing one would take `osprey.yaml`'s place); start removes every
  probe credential, file or none (row 21).
- The live, measured run on the real gateway (the key review's question 2) is still **owed**: the live step is off.
