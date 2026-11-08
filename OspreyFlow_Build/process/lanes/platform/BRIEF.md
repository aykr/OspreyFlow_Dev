# Platform lane · brief P2 · model usage and limits

Written by the orchestrator, 8 November 2026, after P1's merge (`b2fc5e2`), for a **fresh platform session**
on account `sol`. Read `process/lanes/platform/REPORT.md` (P1) and ADR-135 Amendment 2 first. Rebase onto
`main`. Opus, medium. Size M. After it comes P3 (maps administration, ADR-147).

**The lane, the stacks, the merge rule.** Platform's ownership map; a test stack by `stack_lease.sh acquire
platform "<purpose>" && …` only (never `;`, never docker or psql on a stack not held), pinning the ports it
prints; questions, requests and ready-to-merge to the orchestrator by message (Prompt L); before
ready-to-merge, your own lane-reviewer, then make -k ci and make test at a commit rebased onto main, saved
under `process/lanes/platform/gates/`. No real provider is called and no real key written anywhere.

**Binds.** `process/CLAUDE.md` rules 1–15 (3, 4, 7, 12, 13 and 15 above all); ADR-135 and Amendments 1 and
2; ADR-112 Amendment 7 (`manage_models`); `spec/00` §2.4 and `spec/04` §4, which promise per-team budgets,
rate limits and fallbacks through the gateway; ADR-136 (egress).

**Build** (the plan's row P2):
1. **Usage:** calls and tokens per engine and per job over a chosen period, from the gateway's own records
   (measure what the pinned LiteLLM records first, as P1 did, and make the stand-in record the same); in
   *Admin › Models*, behind `manage_models`.
2. **Limits:** the budgets and rate limits the spec promises, set in *Admin › Models*, applied by the
   gateway, audited; what a person sees when a limit stops a request, in words.
3. **Nothing identifying leaks:** usage shows no prompt, no completion, no key and no source-system id;
   per person only if the spec says so (if it is silent, ask the orchestrator first, as multiple choice).

**Tests first, each red by a plant at the real call site:** figures equal a planted gateway record; every
route refuses without `manage_models` (rule 4); a limit set stops the next request through the real routing
path; no prompt text or key appears in any usage response (planted recognisable values); keyboard cases
(rule 13) with registry ids as a diff; axe in dark, light and GOV.UK.

**Exit.** The row's exit; make ci and make test green offline; the live cases against the pinned gateway
under a named lease and stack; a friction fragment. Report in Prompt L's format, then stop.
