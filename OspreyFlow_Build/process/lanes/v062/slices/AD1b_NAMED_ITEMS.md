# AD1b: items it owes that are not in its own brief yet (kept by the conductor; AD1b has no row or brief in `slices.tsv` at 21 November 2026; **fold these into its brief when it is written, as named acceptance items, each with its own check**)

## 1. Correct the false sentence "no key outlives its record" (the owner, 21 November 2026, AD1a option c)

AD1a is accepted at its round-10 tip (`3dd9ec2`) and stays unmerged until AD1b is verified. **AD1a and AD1b merge back to back, so main never holds the false sentence.** AD1a's tip says, in `OspreyFlow_Build/spec/06_DECISIONS.md` (ADR-135 Amendment 14 point 9, about line 41610) and in a test docstring in `OspreyFlow_Build/tests/services/api/test_model_key_paths.py` (about line 1679), that no key outlives its record. That is untrue, and **AD1b corrects both** to the true statement, which names the same three cases:

- when the deployment is switched to local-only,
- when a models file is restored,
- when a re-render drops an engine,

that engine's access token on the gateway (the virtual key derived under the current master key, tagged with the engine's name) is **not removed**; it reaches no model unless an engine of the same name is added again. The one case already named as having no clearing route, a changed master key (N6), stays named beside them.

**Its own check (rule 12 and 15):** a test that fails if the specification, the test docstring or the administration guide (if it says it) states that no key, or no access token, outlives its record without naming the three cases; and a test that shows the three cases really leave a token (a stand-in gateway holding an engine's virtual key; the engine leaves the record by each of the three routes; assert the token is still there and that the specification's list names exactly those routes), so the sentence cannot be made true by words alone and the words cannot go stale if a route is added. Planted: the false sentence put back (red); a fourth route that leaves a token and is not named (red). **No clearing route is built (the owner's ruling: none); no key is shown back, logged, audited or sent anywhere.**

## 2. The v0.6.2 release notes name the three cases in plain words

"When the deployment is switched to local-only, when a models file is restored, or when a re-render drops an engine, that engine's access token on the gateway is not removed. It reaches no model unless an engine of the same name is added again." Recorded in `BACKLOG.md` with the other v0.6.2 release-note items (the conductor), and the release's notes test (if one exists for notes) names them.

## 3. The record

The row is in `slices/AD1a_ROUND6_TABLE.md` (row 7) as accepted by the owner on 21 November 2026, so it is not rediscovered.
