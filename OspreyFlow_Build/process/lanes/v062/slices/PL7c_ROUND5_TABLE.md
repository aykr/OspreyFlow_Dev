# PL7c: every open case before round 5 (23 November 2026, 12:20 UTC; the conductor, from the four verifier records)

**The owner's rule (21 November 2026): no round from 5 on starts without a table of every open case.** Rounds 5 to 8 are judged against it. **Two cases are open; the other eight raised in rounds 1 to 4 are shown closed, with the round that closed them.** Round 5 closes the two open cases and **adds nothing else**.

| # | Case | Raised in | Kind | Status at `039e5aed50` |
| --- | --- | --- | --- | --- |
| 1 | Both conditions on GDS Transport (`only_when: appearance.govuk_identity`, `only_on: gov.uk`) are enforced as behaviour, not only as fields in `fonts.json`: with the switch on the typeface was still drawn on any host. | Round 1 | Fault in behaviour | **Closed** (not raised again after round 1). |
| 2 | The renderer passed `OSPREY_GOVUK_IDENTITY=1` to the workspace build whatever the brand, so `brand: ospreyflow` with the switch on built an image serving GDS Transport. | Round 1 | Fault in behaviour | **Closed** (not raised again). |
| 3 | The build-argument mechanism reaches only deployments built from source; a deployment that pulls the release images gets no typeface with the switch on, and nothing said so. | Round 1 | Fault in behaviour | **Closed** in round 2 by a refusal, and the refusal's over-reach (case 4) closed in round 3. |
| 4 | The new validator refused `appearance.govuk_identity: true` unless `components.source_path` was written, so it refused configurations that are built from the checkout (`--build`, a cloud-platform build). | Round 2 | Fault in behaviour | **Closed** in round 3. |
| 5 | With the switch off the header showed one name (`organisation ?? serviceName`) where decision 14 says the department's name with the service name; the sign-in page's chrome copied it. | Round 2 | Fault in behaviour | **Closed** in round 3. |
| 6 | The I9 browser proof (`apps/pages/test/govuk/identity.spec.ts`) was not written, then ran in no gate. | Round 1, round 2 | Gap in a test | **Closed** in round 3. |
| 7 | The pages default tree's plants were put in a copy of the output, none in the build step that keeps the GOV.UK identity out (the pages build's assets script, its `withoutGovukBrand`). | Round 2 | Gap in a test | **Closed** in round 3. |
| 8 | The switch is per deployment but the image it builds is not: every deployment built from source tagged its workspace image `osprey/workspace:local`, so the switch-on image and the default image shared one tag. | Round 3 | Fault in behaviour | **Closed** in round 4. |
| 9 | With the switch off the sign-in page's footer draws no crown, Crown copyright or Open Government Licence line, even on a gov.uk address (the `identity &&` added to `onGovUk` in `harness/govuk_chrome.js` about line 84); no test ran it on a gov.uk address. | Round 3 | Gap in a test | **Closed** in round 4. |
| **A** | **The Playwright harnesses turn the GOV.UK identity on but never give a gov.uk address, so they never draw GDS Transport. The GOV.UK-look specs that were tuned to the face's measurements now measure Arial, and at least one of them will fail. The harness file's own comment (its first lines) says the opposite.** | Round 4 | Fault in behaviour | **OPEN: fix this round.** Give the harnesses a gov.uk address (or the identity-and-host pair the product uses), so the face is drawn and the specs measure it again; **or** re-tune the specs and say why; **show the specs that were measured against the face pass again, and say which you ran.** Red first: a case that fails when the harness turns the identity on without a gov.uk address. |
| **B** | **No test covers the entry point's wiring of the switch: `deployment.json`, then `appearance.govukIdentity`, then `applyBrand` and `BrandFrame`. A planted `const govukIdentity = true;` (the identity shown on every GOV.UK deployment whatever its setting) would fail no test: the I9 failure the decision record names.** | Round 4 | Gap in a test | **OPEN: fix this round.** A test that reads the entry point's real wiring (the shape `main` meets), planted with the constant `true`, a missing `deployment.json` key and a value that is not a boolean, each red then green. |

## ROUND 7 (the owner's `send-back`, 23 November, about 14:15 UTC): READ THIS FIRST

**Why you are back:** the Mac's `make design-check` is red on your tip `b4c485829b`: four of the 31 node tests in `OspreyFlow_Build/tests/keycloak_theme/` fail ("the GOV.UK header, skip link and footer are added in reading order"; "on gov.uk the footer is as it was, Crown and all"; "off gov.uk the header draws no crown, the word mark kept"; "on gov.uk the header draws the crown"). Your round-3 change to the sign-in chrome script (`identity &&` in `onGovUk`, `harness/govuk_chrome.js`) broke them. **None of your checks ran `make design-check`.**

1. **Fix the chrome script, not the tests.** **The four failing tests stand as written.** Three of them hold the owner's rule that **no crown is drawn off gov.uk addresses**. **A change to any of the four comes to the owner first, with the reason: do not edit them, do not skip them, do not loosen an assertion. If you believe a test is wrong, STOP and say which and why.**
2. **Run `make -C OspreyFlow_Build design-check` yourself, and put its full result in your report** (it runs `tools.design_check`, `tools.colour_drift_check` and `node --test` over `OspreyFlow_Build/tests/keycloak_theme/*.test.mjs`). It is green before you finish. **The verifier is told to run it too.** (It was missing from your frozen checks: the conductor asks the owner for a refreeze that adds it after the merges now running; run it by hand until then.)
3. **Your I9 tests stay** (the switch off draws no crown, Crown copyright or Open Government Licence line, even on a gov.uk address): the fix must make both sets of tests pass together. Red first for any new case.
4. Nothing else: no new checks of your own beyond what the fix needs.

## What you do in round 5

1. Close **A and B**, red first, planted faults at the shape the code really sees (rule 15). **Nothing else:** no new checks, no new files beyond what A and B need.
2. Re-run your own checks and the scan-map check by hand (`unmapped` and `stale`).
3. **A finding that names a key, a credential or a security rule is stopped and reported, never accepted narrower.**

**A verifier's new finding in round 5 that is not one of these two is judged on its merits: a fault in behaviour is fixed in round 6; a gap in a test goes to the owner's standing accept (from round 3 on) when it is only a gap.**
