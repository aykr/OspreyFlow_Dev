# Slice GR1e · GR1 · A case's history, read-only, as a part of its GOV.UK page (round 1 merges `away/GR1e`; the owner, 26 November 2026)

- **Build id:** GR1 (the `cases-and-views` row of `apps/pages/FUNCTIONS.yaml`)
- **Dial setting:** balanced · **Rounds limit:** the dial's (8) · **After:** GR1a (the away branch is built on `away/GR1a`'s tip, `005dcbfca`)
- **The owner's rulings:** every proposal (a) of `slices/drafts_2026-11-26/GR1e.md` (26 November, about 10:35 UTC,
  `RULINGS.md`: "every non-owner question in the 26 November drafts"): read-only, restore waits for GG2e; the route's order;
  a "History" part of the case page linked from its contents; every step shown, no page-side cut (rule 2). The away round
  came in on the owner's word of about 13:40 UTC: "bring into the line like GR1a, round 1 merges the branch". "Who made it"
  is left out for 0.7.0 (backlog row 39).

## Round 1 (D247; the conductor, 26 November 2026): merge `away/GR1e` first

**Your first step: merge the local branch `away/GR1e` into your branch** (the owner fetched it to the Mac). It carries
`away/GR1a`'s commits beneath its own; **GR1a merges to main first**, so by the time you start, main holds GR1a and the
merge brings only GR1e's commits. Keep both sides where main has moved (GR4a, GR1a's merge, any later GOV.UK page: take
every page's entry in each list; drop none). Its report, `process/lanes/v062/away/GR1e_AWAY_REPORT.md` on that branch, is
the record: read it whole. **Every figure in it was taken on the server under its namespace; none is a measurement here.**

Then:

1. **Show the report's table green here:** `cases.test.ts` (35, with CS16 to CS26), `test_govuk_cases_scenario.py`
   (with CS16 to CS26 and the sixth model's census), the GOV.UK keyboard and scripts-off specs
   (`npm run test:keyboard:govuk --workspace apps/pages`: CK4 and CO3), and the route-list pins. Run three of the
   report's planted faults again at the real call site (rule 15): a brief edit said as restorable (CS16), a step skipped
   in the real loop (CS16), the history read twice (CS22). Restore each from a saved copy, never by `git checkout`.
2. **The report's five questions are not ruled.** Each is built in its conservative reading and none blocks the merge:
   leave each as built, list them at the top of your report, and change nothing for them. (1, "Branched" sent as
   "Changed", and 2, a long history with no paging, are later Conduit parts if the owner says (b).)
3. Say whether `assetsTraversal.test.ts` and `foundation.test.ts` pass here (the away report put their failures down to
   the namespace's dot-named `TMPDIR`).

## Acceptance test

`OspreyFlow_Core/apps/pages/test/govuk/cases.test.ts` and `OspreyFlow_Build/tests/glass_trees/test_govuk_cases_scenario.py`
as GR1e extends them (CS16 to CS26): red against main's page with GR1a alone, green after round 1's merge.

## Checks (pure; store ports pinned to 9)

As GR1a's: `npm test --workspace apps/pages`; `npm run lint`; `npm run typecheck`; `node scripts/no_react_check.mjs`; the
GOV.UK scenario tests (cases, help, admin people), `test_functions_yaml.py`, `test_tree_parity.py`,
`test_no_react_check.py`, `test_pages_foundation.py`, `test_design_gates_reach.py`, `test_ui_words_check.py`,
`test_copy_says_no_client.py`, `tests/harness/test_pages_setting.py`; `ruff check .`.

## Out of scope

Restore (GG2e); the history's own page (GR1c); any Conduit change (the report's questions 1 and 2); the GOV.UK tree's axe gap.
