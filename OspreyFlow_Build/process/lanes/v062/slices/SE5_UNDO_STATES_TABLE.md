# SE5: every state the undo can leave (the table the owner asked for before round 6)

Made on the owner's word of 20 November 2026 ("scout first: the table of every state the undo can leave; no builder until it exists") by a read-only scout of SE5's branch at its round-5 tip `390f6a0` (the verifier's checkout), from reading, not running. No key appears in it.
**Round 6 is built from this table and the verifier checks the builder against it row by row** (the owner, item 3). **If a row is open after both rounds given, SE5 stops and comes to the owner with this table.** A key-handling fault is never accepted. The scout's findings are also used to check AD1a's table (the owner, item 5; see the end).

Notation: W0 = no gateway write sent. Wd / Wm = entries deleted / made. Wc = credential deleted or stored. UO = the undo ran and succeeded. UF = the undo ran and failed after writing. Marked = in the process's unavailable set. Line numbers are SE5's `OspreyFlow_Core/services/api/model_admin.py`; test names are from `OspreyFlow_Build/tests/services/api/test_model_address_change_failure.py` only.

**Bottom line: 24 rows, 13 faults.** Round 5's flaw is row 3. The same missing rule shows in six other places: the undo runs after every failure (`_change` lines 1213 and 1240), and no reconcile restores a deleted credential (`_reconcile`, lines 1056 to 1081, handles entries and engine keys only; `put_credential` is called only from `set_key`, line 1415). **On every path traced, no key reaches a wrong address** (entries are written only at the record's address, `set_key` withdraws disagreeing entries first, and a missing address fails closed): the faults are a broken engine still offered, untrue words and audits, and a failed undo that is only a log line.

| # | Row (kind, what was done, ending, undo) | Code | State left | Offered / works | Words and audit | Wrong-address key | Test | Fault |
|---|---|---|---|---|---|---|---|---|
| 1 | non-edit, W0, refused, UO | 1223, 1240-51 | unchanged | yes/yes | true | no | 541 (set_key, UF only) | no |
| 2 | edit, W0, refused, UO (`rebuilt={name}` deletes and remakes entries) | 1314, 1072 | entries remade | yes/yes | true; the undo wrote with nothing to undo | no | none | no (breaks "no undo without a write") |
| 3 | edit, W0, refused or OSError, UF after Wd | 1241-51 (touched false, no mark) | the name's entries missing; record set; not marked | yes/no | "not saved"; gateway altered and unsaid | no | none (541 uses set_key, nothing deleted) | **yes** |
| 4 | any, W0, cancelled, UO | 1210-22 | unchanged | yes/yes | "put back": true | no | 563 (checks no UNAVAILABLE only) | no |
| 5 | any, W0, cancelled, UF | 1214-20 (not touched chooses "put back") | edit: entries missing, unmarked; set_key: unchanged | edit yes/no; set yes/yes | audit "put back" is false | no | 563 (no words check) | **yes** |
| 6 | any, W0, unnamed exception, UF | 1229-36, 1244-48 | as 3 | edit yes/no; set yes/yes | answer and audit "was put back" are false | no | 461 (plants after entries made, so the untouched case is not run) | **yes** |
| 7 | any, wrote entries, refused/OSError/unnamed/cancel, UO | 1223-51 | entries restored | yes/yes | "put back": true | no | 341, 461 | no |
| 8 | edit not moved, wrote, any ending, UF | 1241-42 | marked | no | "unavailable" | no | 426, 499 | no |
| 9 | edit moved, Wc, refused in `_reconcile(proposed)`, UO | 1303-11 | file OLD, key record removed (saved at 1309); entries OLD; no credential | no | "not saved": the key removal was saved and unsaid; no key_removed audit | no | 272 (state only) | **yes** (words) |
| 10 | edit moved, Wc, first save (1309) OSError, UO | 1309 | file OLD, key SET; no credential; entries name a deleted credential (438) | yes/no | "not saved": the record says SET | no | none (341's save fault is the second save) | **yes** |
| 11 | edit moved, Wc, cancelled or unnamed before save 1, UO | 1210/1229, 1305-09 | as 10 | yes/no | cancel "put back" false; unnamed "was put back" false | no | none | **yes** |
| 12 | edit moved, save 1 ok, NEW entries made, save 2 OSError or refused, UO | 1311 | file OLD, no key; entries OLD | no | "not saved" (the key removal unsaid, as 9) | no | 341 | **yes** (words) |
| 13 | edit moved, save 1 ok, cancelled or unnamed after NEW entries, UO | 1210-36 | file OLD, no key; entries OLD | no | "put back": true | no | 341 | no |
| 14 | set_key rotation, Wd, DELETE, POST refused (KeyRemovedNotReplaced), UO | 1416-20, 386 | record lost (saved); no credential | no | "entered again; offered to no analyst": true | no | 801-814 | no |
| 15 | rotation, DELETE done, POST refused, then `_save(lost)` OSError, UO | 1418-19 | record SET; no credential | yes/no | "not saved": record SET | no | none | **yes** |
| 16 | rotation, DELETE done, POST raises a non-httpx exception or is cancelled, UO | 1415 (only httpx.HTTPError caught, 386) | record SET; no credential; entries restored | yes/no | "put back" false | no | none | **yes** |
| 17 | first key (no record), DELETE 404, POST refused, UO | 1416-20 | none | no | "after the old one was removed": none was there (wording only) | no | none | no |
| 18 | set_key, withdraw refused, UO | 1413, 1046-54 | at-odds entry left; key not stored | per marking | refusal: true | no (no key written) | 723 | no |
| 19 | remove_key, DELETE done, `_save` OSError or cancelled before save, UO | 1438-40 | file SET; no credential | yes/no | OSError "not saved"; cancel "put back" false | no | none | **yes** |
| 20 | remove_engine, first `_reconcile(proposed)` done, then the engine-key or credential DELETE refused, UO | 1331-56 | entries and engine key restored; credential intact | yes/yes | refusal: true | no | none | no |
| 21 | remove_engine, credential DELETE done, `_save(proposed)` OSError, UO | 1352-53 | file: engine SET; no credential; entries restored | yes/no | "not saved" | no | none | **yes** |
| 22 | add_engine, reconcile partly done, refused or `_save` OSError, UO (deletes new entries as at-odds) | 1257-75 | unchanged | no (no key) | refusal: true | no | none | no |
| 23 | set_defaults or set_limits, `_save` OSError, UO (always writes /key/update) | 1079, 1358-71, 1445-71 | unchanged | yes/yes | "not saved": true; the undo's writes uncounted | no | none | no (the undo wrote and failed unmarked: breaks the rule, no state fault) |
| 24 | check (`test()`), no write | 1473-1517 | none | per marking | UNAVAILABLE words if marked; for rows 10, 15, 19, 21 the gateway refusal reads as "token may be wrong" | no | 593, 619 | no (misreports the cause) |

No check-add or cancel-check endings exist in SE5's model_admin.py (those are AD1a's).

**Start-up (`_start_once` 955-990, `start` 910-925):**
- Killed after Wc, before the save (rows 10, 15, 19, 21): on restart the entries are present, so the engine is not "lost" (975). It is offered as SET with no credential. Nothing marks it and nothing reads credentials. **Fault, no test.**
- Killed after NEW entries, before save 2: start marks the engine (992-1015), withdraws (1046-54) and reconciles. Test 646. No fault.
- Killed mid-undo, gateway answering: missing entries are re-made by reconcile. The marks are memory-only, so a restart finds only wrong-address entries, not missing ones. The docstring at 802-804 ("another process finds the same") holds only for wrong-address entries.
- Unpriced rebuild (971-986), delete then add refused: `_start_once` returns False (988-990); only at-odds engines were marked (992-1003); the engine is offered during the retry window with entries missing; the only trace is a log line. **Fault, test none.**
- Gateway unreachable: offered per the record, calls refused. Accepted in the docstring (914-916); not counted.
- Any successful `_reconcile` clears every mark (1081), including an engine whose credential is gone from rows 10, 15, 19 or 21. **Fault, test none.**

## The design rules a fix must satisfy together (the scout's, adopted as round 6's brief)

1. **No undo unless the change sent a write** (writes differ from where they began). Row 2 breaks this.
2. **Any write the undo sends counts as altering; a failed undo that wrote marks the engine.** Rows 3, 5, 6 and 23 break this; `touched` is read before the undo (1239).
3. **Deleting a credential must mark the engine before any later await, or write an intent record first and clear it on success.** No reconcile restores a credential, so rows 10 to 21 stay broken otherwise.
4. **"Put back" is said only when the undo succeeded and restored entries and credential.** Today the cancel and unnamed branches use `touched` (1219, 1244-48).
5. **Cancel, unnamed, OSError and refusal share one words-and-mark decision.**
6. **A successful reconcile clears only the engines it actually made whole** (1081).
7. **Start marks every engine whose reconcile did not finish**, not only wrong-address ones (992-1003, 971-990), **and every engine whose credential is gone while the record says SET** (rows 10, 15, 19, 21).
8. **A "not saved" answer must say when the key removal (row 9's first save) was saved.**

## What it means for main and for AD1a (read by inference; AD1a was not read)

- **Main today:** main's `edit_engine` has the same delete-credential-then-save ordering (main's `model_admin.py` about 1138 to 1147), so **rows 9 to 13 exist on main now.** Main's `_change` (about 1077 to 1091) catches only a refusal and OSError, has no cancel or unnamed branch, and its `_put_back` (about 977 to 983) logs an undo failure as a bare log line. Main's `_reconcile` (about 951 to 975) has no address comparison, no write counter and no `_withdraw_disagreeing`, so `set_key` has no withdraw step. SE5 is the fix for these; it merges before AD1a.
- **AD1a:** rows 1 to 8, 9 to 13 and the start-up rows apply to AD1a if its `edit_engine` keeps main's ordering or its `_change` keeps SE5's undo logic. **AD1a's key-path table (`slices/AD1a_KEY_PATHS_TABLE.md`) gains these rows as row 29 onward when AD1a restarts** (the owner's item 5); AD1a takes main in after SE5 merges and keeps the stronger behaviour.

Not settled by reading: whether a non-httpx exception can come out of the request call in practice (rows 6 and 16 depend on it); whether a write that was sent but never answered was executed (the counter treats it as a write: the conservative choice); whether any test outside `test_model_address_change_failure.py` covers the unpriced rebuild or a start with the credential missing.
