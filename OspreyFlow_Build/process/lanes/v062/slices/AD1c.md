# Slice AD1c · AD1 · A failed Add removes the engine's access token from the gateway (the fourth route AD1b names; lands before any release)

- **Build id:** AD1 (the Admin model form), ADR-135 Amendment 14. **The owner's ruling of 23 November 2026:** the fourth route that leaves an engine's access token on the gateway (an Add whose record cannot be saved) is **named in the specification text by AD1b, kept in AD1b's test as a named route, and fixed here. The fix does not go on the general backlog: it is this slice's, and this slice lands before any release.**
- **Dial setting:** balanced
- **Rounds limit:** the dial's (8)
- **After:** AD1a and AD1b merged (the Add path, `add_checked`, and AD1b's `test_stale_engine_keys_are_named.py`, which names the route). **No row in `slices.tsv` yet; the conductor adds it when AD1b has merged.**
- **Status of this brief:** written by the conductor on 23 November 2026 from AD1b's round-1 verifier finding (`OspreyFlow_Core/services/api/model_admin.py`, `add_checked`; re-read every line named).

## What the finding is

`add_checked` (in `OspreyFlow_Core/services/api/model_admin.py`) runs `_reconcile(proposed)`, which puts the engine's derived access token and its entries on the gateway, **before** `_save(proposed)`. If the save fails (an unwritable models file), the undo that follows puts the gateway back as the file says: it withdraws the entries and **not** the engine's token. The engine was never in the record, so no removal route clears that token. **The 15-minute sweep does not: it removes a passed check from the models file and the key of that check, and the engine's token is a different key.** The start-up reconcile withdraws entries the record does not hold, not keys. The token reaches no model (its entries are gone) unless an engine of the same name is added again; it stays until then or until someone removes it on the gateway by hand.

## What (red first; planted faults at the shape the code really sees: rule 15)

1. **The failing test first, on main:** a test that drives an Add whose `_save` is made to fail (the unwritable models file shape the route really meets) and asserts that afterwards **no token for that engine is held on the gateway** and the file still holds the check. Use AD1b's `token_left` helper and its planted fourth route: that plant becomes the proof. Red on main, green after the fix.
2. **The fix:** a failed save after `_reconcile` removes the engine's token (`delete_engine_key`, by derivation, no key read) as well as the entries, in the same undo. **A refusal of the removal itself leaves the engine's token and says so in words** (as an engine's removal does today); it never reveals a key. The check stays held (the administrator can still Cancel it) and its key is removed by Cancel or the sweep as before.
3. **AD1b's test:** the route moves from "named and planted" to "named and closed": it still names the route, and now asserts the token is **not** left. The specification text (06_DECISIONS.md) says the route was closed by this slice: that edit is an approved diff for the owner, drafted by the conductor.
3b. **Widened by the owner (23 November 2026): remove any orphaned engine tokens that already exist, and show none are left.** The gateway's own listing of keys cannot be used (the listing was removed from start-up and every reconcile because the measured responses cannot do that work without part of a key reaching the product; see the specification's passage on stale virtual keys). **So find a way that reads no key and lists nothing it may not:** for example, the engines the record has **ever** held or tried to Add (the audit rows for an Add and the checks), whose derived key names are known by derivation from the master key, minus the engines the record holds now; remove each such token by derivation (`delete_engine_key`) and have a test show, against a gateway fake that models the real one's refusals, that **none remains** for any engine not in the record. **If no way exists that reads no key and takes no listing, STOP and report; do not choose, and do not bring the listing back.** The removal is a one-off command or a start-up step (say which and why), audited once, and safe to run twice. The report says how many tokens it found on the owner's own deployment (read only: how it finds them is part of what you propose).
4. **Say in the report:** every other path through `add_checked` that can fail after the gateway has been written to, and whether each removes what it put (a table: failure point, what was written, what the undo removes).

**Not in this brief (the owner, 23 November 2026, about 14:00 UTC): "the models chosen from what the gateway found" (listing the models a key may use) is AD1d's, a part of its own after AD1c (`slices/AD1d.md`).**

## Acceptance test

A new pure test named for the fourth route (the builder names it), red first; **say which folders it walks** (a scan-map row is written from that; a builder cannot add it).

## Out of scope

The master-key rotation row (N6); the gateway's own behaviour; any change to the keys' derivation; the Models screen (AD1b's). **A finding that names a key, a credential or a security rule is stopped and reported, never accepted narrower.**
