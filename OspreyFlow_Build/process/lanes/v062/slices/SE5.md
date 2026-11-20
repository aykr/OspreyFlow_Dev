# Slice SE5 · SE5 · A failed change of a model's address never leaves gateway entries the record does not agree with, and start-up checks every entry (security, found on main)

- **Build id:** SE5 (in the plan: "Security: a failed change of a model's address never leaves gateway entries the record does not agree with, and start-up checks every entry's address against the record, so a model key cannot
  reach an address it was not given for").
- **Dial setting:** balanced
- **Rounds limit:** 4
- **After:** nothing. **It touches no workspace file, so it runs beside PL4.** The owner's order (20 November): merge ahead of everything except a PL4 slice. AD1a merges main in afterwards and keeps the stronger of the two behaviours.
- **Status of this brief:** written by the conductor on 20 November 2026 on the owner's word ("option 1: fix main now, as build SE5 in the security lane"), from a read-only scout of main the same day. **The scout's line numbers are unchecked: you re-read
  them, and you also read the gateway adapter and client files the scout did not** (`OspreyFlow_Core/packages/adapters/model_litellm/adapter.py`, `client.py`, `usage.py`, `stand_in.py`, `OspreyFlow_Core/services/api/model_routing.py`,
  `packages/schemas/model_admin.py`).
- **The owner's rules for keys bind this slice:** write-only; a key is never shown back; replace and remove never reveal; audited without the key; only the holder of the right; the server command is a second route; **synthetic keys, generated at run time in every
  test and plant, and no fixed key-shaped string in any file, message or commit.** No key, real or synthetic, appears in your report.

## What the scout found (reasoned, not run: this is what you test)

The code is `OspreyFlow_Core/services/api/model_admin.py` (the Admin model engine routes) and `cli/ospreyflow/model_keys.py`. When an engine's **address (`api_base`)** is edited, `edit_engine` (about lines 1138 to 1147) deletes the engine's
credential at the gateway, saves the record with the key dropped (the record still holds the old address), rebuilds the engine's gateway entries at the new address (`_reconcile(proposed, rebuilt={name})`), then saves the new record. If that
is refused, `_change` calls `_put_back` (about lines 1077 to 1084 and 977 to 983), which reconciles back to the old settings, best effort: **if `_put_back` itself fails, only a log line is written and nothing retries.** Nothing at start-up compares an
entry's address with the record (`_start_once`, about lines 925 to 934, reconciles with `rebuilt=` only the per-token-priced entries). `_reconcile` (about lines 965 to 972) **keeps an entry already held under the same id, whatever address it carries**. So after
such a leftover, the next `set_key` (or `ospreyflow models key`, `move_keys` about `model_keys.py:82`) stores a key under the engine's one credential name (`osprey-<provider>`; an entry carries its own `api_base` and names that credential) and **the key is sent to
the leftover entry's new address while the record says the old one.** The stand-in (`stand_in.py` about lines 773 to 786) resolves the credential by name at call time and sends it to the entry's address.

## What

1. **First, the reproduction: a failing test at the real call site, and if it cannot be reproduced, stop and say so in your report** (the owner: "then the scout's reading was wrong"). Plant **the two failures**: (a) the address change refused or interrupted
   (the gateway refuses to make the new entry, or the record cannot be saved, or the process stops between two steps), and then (b) the undo failing (the put-back is refused too) or the process dying. Then a later `set_key` with a synthetic key (made at run time).
   The test asserts, through the stand-in's own record of what it was sent (as `world.gateway.sent` is used by neighbouring tests), that **the key is sent only to the address the record holds, never to an address it was not given for.** It must be red on main
   for that reason. Use the gateway stand-in that models the real gateway's refusals (an entry naming a missing credential answers as a missing key; rotating a credential changes it for every entry that names it): a fake that only grants proves nothing (rule 15).
   `AD1a`'s branch (`git show lane/slice-AD1a:OspreyFlow_Build/tests/services/api/test_model_edit_failure_keeps_key_off_old_address.py`) has a test of the same shape for its rewritten edit path: you may read it as a model; copy no key-shaped string.
2. **The fix, in three parts, each with its own red-then-green test:**
   - **A failed address change never leaves gateway entries the record does not agree with:** withdraw the new-address entries on any failure (not only a refusal: an exception that is not a named one, a timeout after the gateway wrote, an interruption), **or** mark the
     engine unavailable and say so in words. Either way no later call can reach an address the record does not hold.
   - **The undo failing is loud, never a log line alone:** the person making the change is told in words (the route's answer says the engine is unavailable until it is repaired, and what to do); the engine is marked so; an audit record without the key says what happened.
   - **Start-up compares every entry's address with the record** and withdraws, or refuses and says in words, whatever disagrees (an engine's entries at another address, an entry for an engine the record does not hold). It must also cover the process having died mid-change.
3. **Do not widen it.** The fix keeps the existing routes, words and rights; it changes no weight and no setting; it adds no route. If the stronger design needs a new field in the record or a new route, say so in your report and stop for the conductor.
4. **Other paths in the same code.** The scout found these send no key anywhere (`remove_engine` reconciles then deletes the key then saves; `remove_key` deletes then saves; `set_key` with the key removed but not replaced records the key as lost): confirm by reading, and add a
   test only where one would fail if the path were wrong (rule 12). Say in your report which you confirmed.
5. **Spec.** If `spec/03_CONDUIT_MIDDLEWARE.md` or the administration guide states how an address change behaves, bring it to the fix (a sentence, and the guide's document-control row if it has one). Do **not** write an ADR amendment in this slice
   (AD1a is writing ADR-135 Amendment 14 on the same ledger tail); say in your report if an amendment is needed and what it would say.
6. **Release notes (the owner: v0.6.2 names the fix in plain words).** In your report, write the one or two plain sentences for the release notes, for the conductor to place; do not edit a release-notes file.

Binding: process/CLAUDE.md rules 3, 4, 11, 12, 15; ADR-135 and its amendments; ADR-050 where it touches the credential; the owner's key rules above; the 18 November ruling on the client's name; British English. You do not edit `OspreyFlow_Core/Makefile`, `.github/workflows/ci.yml`
or any `CLAUDE.md`; no file under `apps/workspace`.

## Acceptance test

One new pure file, red first on main against the real code: `OspreyFlow_Build/tests/services/api/test_model_address_change_failure.py` (the reproduction of item 1; the three parts of item 2, each with the planted fault it is meant to catch; the loud undo; the start-up check),
with the stand-in gateway and the models record both in memory (`ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9` in every command: nothing live). In its header, say which test fails if each behaviour is violated (rule 12).

## Checks

The **checks command** runs, pure only, the neighbours that must stay green: `tests/services/api/test_model_admin_routes.py`, `test_model_engine_keys.py`, `test_model_engine_kinds.py`, `test_model_usage_and_limits.py`, `test_admin_models_extraction_engine.py`, `tests/harness/test_deployment_schema.py`,
`tests/cli/test_models_verb.py`, then `ruff check .` in `OspreyFlow_Core`, the schemas check and the route-coverage check. The line adds every mapped pure test that scans a folder the slice changes. **Before your final report run by hand the cheap checks the conductor will run again before the
merge:** ruff on every file you changed, and the scan-map check for the test you add (it uses no folder walk, so it should need no row; say so). Never run `test_apply_env`. A merge attempt costs 25 minutes: a lint error or a missing row found there is your round.

## Out of scope

AD1a's rewrite of the edit path (it merges main in after this and keeps the stronger of the two); new routes, fields or rights; the live measured run against the real gateway (owed, the live step is off); the screen.
