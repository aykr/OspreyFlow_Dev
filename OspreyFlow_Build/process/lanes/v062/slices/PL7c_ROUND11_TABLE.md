# PL7c: round 11, a merge of main after GR2a (24 November 2026, 17:05 UTC; the conductor)

**The owner's rule: no round from 5 on starts without a table of every open case.** One case is open; **every case of rounds 1 to 10 is closed** (the last verifier passed `57a6590472`, with the allowlist count at 71 on the owner's word).

| # | Case | Status |
| --- | --- | --- |
| 1 | **GR2a (the GOV.UK tree and its Help page) has merged, and PL7c's branch conflicts with it in four files** (the server's run of the stack GR2a then PL7c, `57a65904-after-GR2a`, said so: "it does not merge onto main + GR2a: a conflict in …"): `OspreyFlow_Core/apps/pages/package.json`, `OspreyFlow_Core/apps/pages/test/govuk/RUN_RECORD.md`, `OspreyFlow_Core/apps/pages/test/govuk/ci-wiring.patch` and `OspreyFlow_Core/apps/pages/test/govuk/playwright.config.ts`. Both slices created the GOV.UK tree's test folder (GR2a for the Help page's keyboard and scripts-off proofs; PL7c for its identity-switch proofs). | **OPEN: this round.** |

## What you do (and nothing else)

1. **Take main in** (a merge, not a rebase) **and settle the four files keeping both sides' meaning:** `package.json` keeps the scripts and dependencies of both (the `test:keyboard` script runs both slices' configs, GR2a's `test/govuk/playwright.config.ts` and PL7c's, as one config or two named configs: **your design, said in the report; neither slice's spec is lost or skipped**); `playwright.config.ts` is **one** config whose projects cover both slices' specs (the Help page's keyboard and scripts-off walks and the identity switch's proofs); `RUN_RECORD.md` **records both slices' red-then-green runs** (GR2a's table as it stands, PL7c's added under its own heading); `ci-wiring.patch` is **one diff for the owner** that makes `ci.yml` (or the Makefile) run `npm run test:keyboard --workspace apps/pages` for both, and **it passes `git apply --check` against main**.
2. **No other change:** no code, no test body, no fixture, no word of the sign-in chrome; the allowlist stays at 71 on the owner's word.
3. **Run, and say the results of:** the whole GOV.UK keyboard run (both slices' specs red-then-green as the record says: **re-run both and write the real results**), `npm test --workspace apps/pages`, `PYTHONPATH=../OspreyFlow_Build uv run --frozen python -m tools.design_check` and `tools.colour_drift_check`, the sign-in theme's node tests, PL12b's theme-rules test and your slice's checks. **If a conflict cannot keep both meanings, STOP and tell the conductor.**

**A finding that names a key, a credential, a certificate or a security rule is stopped and reported, never accepted narrower.**
