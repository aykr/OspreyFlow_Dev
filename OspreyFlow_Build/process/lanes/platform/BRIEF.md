# Platform lane · brief P4 · the analyst's map

Written by the orchestrator, 9 November 2026, after P3's merge (`246b51d`), for a **fresh platform session** on
the orchestrator's account. Read `process/lanes/platform/REPORT.md` (P3) and ADR-147 first. Rebase onto `main`.
Opus, medium. Size M. This is platform's last planned step.

**The lane, the stacks, the merge rule.** Platform's map (`map/**`, `site/**`, the map modules); a test stack by
`stack_lease.sh acquire platform "<purpose>" && …` only; Prompt L's rules (never stop on a question; schemas ride
with the step; every live test removes what it writes; your own lane-reviewer, then make -k ci and make test at
a commit rebased onto main, saved under gates/, with a leased live run including `test_route_rights.py`). Map
data in the demo and CI is tier 1 only (rule 9); no real tiles fetched in tests.

**Binds.** `process/CLAUDE.md` rules 1–15 (3, 7, 9, 12, 13 and 15 above all); ADR-014–017, ADR-147;
`spec/02_GLASS_FRONTEND.md` §3.5 (basemap switching, gazetteer search, the "Basemap not built" message).

**Build** (the plan's row P4):
1. **A basemap switch** among the providers the deployment holds and the reader may use; never a provider's key
   or key-bearing URL in the Glass.
2. **Place search** over the loaded gazetteer, the results limited to what the gazetteer holds (no hosted
   geocoder call unless the deployment names one, and then under ADR-136's egress rule).
3. **The light and GOV.UK themes' contrast check** beside the dark one (`map-verify/contrast.spec.ts`).

**Tests first, each red by a plant at the real call site:** `keyboard/map-view.spec.ts` cases for the switch and
the search (rule 13), registry ids as a diff; no key in any map response the Glass reads; contrast in the three
themes; axe in dark, light and GOV.UK.

**Exit.** The row's exit; make ci and make test green offline; a friction fragment. Report in Prompt L's format,
then stop.
