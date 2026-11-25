# AD3a, round 6: every open case (the conductor, 25 November 2026, 06:38 UTC)

From the round-5 verifier's record. **This round is the two rows below and nothing else.** Row 1 touches who may sign
in, so it is reported to the owner; it is decided already by his rule of 20 November 2026 (a GOV.UK page keeps the
Default screen's behaviour wherever it can be rebuilt; an exception only where impossible, and only with his word).

| # | Open case | Where | Done when |
| --- | --- | --- | --- |
| 1 | **A guest (B2B) account is shown simply as "Enabled".** The React section this page is read from marks that a guest signs in only while guest accounts are admitted; spec/08 does not list that mark as left out. | the people page's State column and its words | The State column says what the React section says for a guest, in the same meaning (read the React section's own words and conditions: find it under `apps/workspace/src/admin/`), for every state the route can send; red first with a guest in the world. No other state's words change. |
| 2 | **The fixture Conduit's `Account` / `account()` model only part of `PersonAccount`** (no `guest`, `signed_in`, `email`, `receivable_handling_codes`, `access_read_at`), so no test can send a guest or a person from the organisation's directory who has never signed in (rule 15: the fake narrower than the real route). | `apps/pages/test/support/fakeConduit.ts` | The fixture's account carries every field of the generated `PersonAccount` type, required ones always (a test compares its field list with the generated type's, so a field added later cannot be missed); the world has a guest and a never-signed-in directory person; and a case fails if either's state is dropped or misstated on the page. |
