# Platform lane · brief P3 · maps administration (ADR-147)

Written by the orchestrator, 8 November 2026, after P2's merge (`66009ab`), for a **fresh platform session**
on account `sol`. Read `process/lanes/platform/REPORT.md` (P2), ADR-135 Amendments 2 and 3, and the maps
survey summarised below first. Rebase onto `main`. Opus, medium. Size L. **P3 is one of the docs lane's
gating steps.** After it comes P4 (the analyst's map).

**The lane, the stacks, the merge rule.** Platform's ownership map (the Maps section, `map/**`, `site/**`, the
tile proxy and cache, prefetch, tier-4 registration, the map config loader, the geocoder, the set-up console's
Geospatial screen, the map scripts); a test stack by `stack_lease.sh acquire platform "<purpose>" && …` only;
Prompt L's rules: never stop on a question (log it under "Decisions taken"; only loosening access, real data
or contradicting an accepted ADR stops a piece); schemas changes ride with the step; before ready-to-merge,
your own lane-reviewer, then make -k ci and make test at a commit rebased onto main, saved under
`process/lanes/platform/gates/`. Map provider keys are credentials, so P3 gets the orchestrator's
independent review too. Map data in the demo and CI is tier 1 only (rule 9): no real tiles fetched in tests.

**First, carried from P2's independent review (credentials):**
1. Reconcile revokes every gateway key tagged `metadata.osprey_engine` that the current master key would not
   derive (old keys stay valid after a master-key rotation today), red with a rotation.
2. Each engine's gateway key is limited to its own engine's models (`/key/generate` with `models`), red with
   one engine's key calling another's.
3. The live backup check also searches for the engine key's SHA-256, after a call made with the key; or the
   spend tables' hash columns are left out. Say which in Amendment 3.
4. A garbled answer at start never stops the Conduit starting (guard the first `start()`), red with a
   non-JSON 200 first.
5. ADR-135 Amendment 3 says why usage counts are not an unfiltered count under rule 7 (counts of calls, no
   case, no content), or narrows them.
6. The Glass shows `model_limit_reached` where it shows `engine_refused` (`patterns/api.ts`, Ask to search; no
   lane owns it, ratified at merge). Minors from that review if quick: refuse an empty master key and a hosted
   engine named `local`; tag *Test the connection*'s calls; `model_keys.py` closes its admin.

**Build** (the plan's row P3, ADR-147, written by you under its reserved heading):
- ***Admin › Maps***: each provider (tiers 1–4) with its state, added and edited, its key under ADR-135
  Amendment 2's rule (the owner: map keys follow the same rule as model keys: managed in Admin, write-only,
  never returned, logged or echoed, every change audited, behind `manage_geospatial`); where a map key is
  stored is yours to decide and record (the tile proxy reads it; never `osprey.yaml`, never a backup).
- **The local basemap**: its state; Build and Verify really run (the set-up console's 501s replaced, the
  `/v1/admin/geospatial/*` routes called); the glyph fonts.
- **Prefetch areas** set and run on a schedule; attribution shown.
- **`ospreyflow map` verbs** (list, build, verify, prefetch) for headless use.
- **The WMTS `endpoint` conflict** (`07_BUILD_PLAN.md`, phase 5's known gaps) settled.

**Tests first, each red by a plant at the real call site:** access tests (`MANAGE_GEOSPATIAL`) on every route;
a map key in no response, log, audit row or backup (planted values through the real route and logger); demo
and CI map data tier 1 only (`test_demo_osprey_config_is_tier_1_only.py`); build and verify on a small
synthetic region; keyboard cases (rule 13), registry ids as a diff; axe in dark, light and GOV.UK.

**Exit.** The row's exit; make ci and make test green offline; live cases under a named lease and stack; a
friction fragment. Report in Prompt L's format, then stop.
