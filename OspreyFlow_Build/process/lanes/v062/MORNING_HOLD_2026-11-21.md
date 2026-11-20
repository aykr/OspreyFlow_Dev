# Held for the owner (the standing word of 20 November, night, item 3)

Things the line carried on without, because each needs a ruling, a security ruling, a protected-file diff or an exception to the design rule. Newest last.

## 1. PL7a2: the renderer half of PL7a (from the scout of the night; read, not measured)

PL7a as the plan words it is not documentation-only. Pages is rendered nowhere today, so rendering it in the four shapes (local-lite, small, cluster, cloud-platform) adds a container to each and needs path routing the front proxy does not have (ADR-152 decision 7: `/studio`, `/session`, `/assets/pages`; `harness/site.py` routes by host only). **No test pins a whole render** (compose, Caddyfile, values, `deployment.json`), so "unchanged when off" is not guaranteed by a test: a golden render of the four shapes must come first, red first.

Cut proposed: **PL7a1** (running tonight: the derived tree state with its test, the guide passages 4.1, 6a and the README, the allowlist clean-up; no render change) and **PL7a2** (golden render first, then pages in the four renderers, the path route table, the `OSPREY_PAGES_*` settings, I18, the re-pinned tests; two to three rounds).

Owner questions before PL7a2 can start:
1. **May pages render in every deployment now,** given that the GOV.UK demo and your own deployment would gain a pages container, route and secret at their next re-render? Or a default-off setting (the ADR names none, so it needs a ruling)?
2. **Cloud-platform wording in the guide's section 6a:** cloud-platform is not an install mode (`ospreyflow install` takes lite, small, enterprise) and the ADR does not place it. PL7a1 says only what is true today and lists the rest.
3. **Who owns the identity switch (`appearance.govuk_identity`) and the I9 proofs:** it brings `apps/workspace` in (`GovukHeader.tsx`, `tokens.css`, `brand.test.tsx`). PL7a2, PL7b, or its own slice after PL4 E?
4. **I14 (the refusal of Superset under GOV.UK):** your ruling puts the test in PL7b; does the render change that omits Superset under GOV.UK belong in PL7a2? (`harness/site.py` adds the bi route on `reporting.superset` alone today, with no brand check.)
5. **I16 (session lifetime) has no test and no slice.**
6. **Protected-file diffs owed** (owner's hand): a pages gate in the Core Makefile `check` and the Build Makefile `ci`; I23's scan wiring; the release signing list (`harness/signatures.py`) when pages is released; the `process/CLAUDE.md` changes the ADR names; the 05_DEPLOYMENT and 02_GLASS_FRONTEND amendments PL7 owes.

## 3. AD1a stopped after round 9: the premise of your N4 ruling is false (a ruling on keys)

**Closed in round 9:** rows 42 and 43 (the verifier raised nothing on either). **Open:** (a) a fault in the specification text and (b) a gap in the N4 test.

- **(a) The fact behind your N4 ruling does not hold.** You ruled yes because the gateway's virtual-key listing "holds hashed tokens and no key material", and round 9 wrote that into `spec/06_DECISIONS.md` as fact. The code asks for it with `return_full_object=true` (`model_admin.py` about line 649), and that listing also returns **`key_name`: `sk-...` plus the last four characters of every virtual key, including keys that are not OspreyFlow's** (measured, recorded in `tests/adapters/model_litellm/test_stand_in_gateway_usage.py` about lines 276 to 277 and 291; the stand-in at `stand_in.py` about line 727). So the product **receives part of each key** — the same kind of exposure that ruled out `GET /credentials` (first and last two characters). **No key is at risk today:** the code reads only `token` and `metadata` and drops `key_name` (`model_admin.py` about lines 655 to 659). But the specification states a false fact, so it is not left standing, and the premise comes back to you.
- **(b) Gap:** the N4 test searches for the token and the full synthetic key only, never for `key_name`; a plant that logs `key_name` would leave it green.
- **Options (for your ruling; I recommend 1 if the measurement allows, otherwise 2):** (1) keep the listing but request it without the full object, if the gateway then returns hashed tokens only (the builder measures this on the stand-in and in the recorded real-gateway measurement, and the specification says what was measured); (2) drop the virtual-key listing from start-up as well and rely on the note of intent alone (a stale virtual key is then removed by another route: the builder says which); (3) keep it as it is, say in the specification that the product receives each key's last four characters and drops them at once, and test that `key_name` reaches no log, answer or audit (the same class as the credential listing you ruled out, so I do not recommend it).
- **State:** AD1a is stopped at 9 rounds; it stays unmerged until AD1b is verified in any case, so it holds nothing up. After your ruling: one `add-round` line (the stop is cleared by it) and one more round.

## 4. BL1b (the ledger union merge) is refused by today's gate, at round 4 of 4: one line needed

BL1b passed its verifier at e7c13da and its merge ran the full gate on the merge result: **one test failed in 15,704: `tests/test_layout.py::test_no_product_folder_is_left_at_the_root`**, because BL1b's new `.gitattributes` sits at the repository root and that test's list of allowed root files (`stayed`) does not name it. The fix is one entry in that test's list, in BL1b's own branch (a test, not product code). **The slice is at its rounds limit, so `send-back` needs your line: `BL1b	add-round	2026-11-21`** (or the date you add it). I recommend yes: it is a one-line fix, and until BL1b lands every slice that appends to `ADR_RESERVATIONS.md` can still bounce on a conflict (PL2b did twice). The builder is also told to run every test that lists the repository root's files (the verifier's checks did not include `test_layout.py`).

## 2. SE7: if the store records no deletions (a security ruling)

SE7's round-1 verifier found that the creator of a shared view is told "chosen minus shown", which counts nodes hidden by a marking, against your boards' rule. Round 2 is told: use a recorded deletion if the store has one; **if it has none, `missing` goes away for everyone and the options come to you** (record deletions when a node is deleted; or keep `missing` off). An existence lookup is an oracle and is not used. The builder's report will say which case it was.
