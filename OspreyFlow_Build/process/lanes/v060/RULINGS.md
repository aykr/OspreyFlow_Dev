# v0.6.0: the owner's rulings, 15 November 2026

On the plan of record (`OWNER_PLAN_2026-11-15.md`), after the orchestrator's estimates (~10:10Z).

1. **The list without item 7.** v0.6.0 is the whole list less item 7 (two demos on one server, Part 3), released as soon
   as it is done; the second demo (ospreyflow.app) moves to later.
2. **Fresh install only, held by a refusal (`rf`).** `ospreyflow update`, and an install over an existing deployment,
   refuse an earlier one in words: v0.6.0 is installed fresh. Red first (rule 12), so the release notes' sentence states
   a rule something holds.
3. **Item 23 is out of v0.6.0.** The cloud-platform shape's sizes are not changed; the package test records the memory
   it measures (platform-b's sampler, in item 11), and those figures are what the owner uses.
4. **The basemap (item 10): settlements only**, OSM's `place=*` points, not every named point (~900,000 for Great
   Britain); or the map tiles alone if that is simpler.
6. **The cached-upgrade trap is fixed in v0.6.0** (the owner, ~11:30Z): every image's upgrade layer is cache-busted in
   the Makefile, both workflows (an owner's diff) and a deployment's own build; rules, with the Superset CVE fix.
7. **`ospreyflow run` on Entra joins v0.6.0** (the owner, ~11:45Z): the CLI's service token sends the scope Entra
   requires; admin, beside #18.
8. **The release workflows (the owner, ~13:40Z):** the dev repo's root release.yml is retired, and tools/release_local
   follows the product's workflow (OspreyFlow_Core/.github/workflows/release.yml); the tag-against-VERSION check moves to
   the head of the product workflow (platform-b's product_release_version.diff, an owner's apply). `ospreyflow images
   push` gets the upgrade stamp, under ruling 6 (the client's own cloud-platform build path).
5. **Item 8 is done**: the profile's fixed cost was `edges_among`, fixed by ADR-124 Amendment 20 on 14 Nov.

The orchestrator's rulings under the standing rule, reported to the owner: item 3, a new question closes the earlier
ones and a closed answer's line shows "n proposals to decide"; item 4, the results page and Ask & Chat's full page
replace each other, Explore and History stay drawers; item 5, a link whose two ends the reader cannot both see is left
out and counted, never named; item 10 moves from platform to rules-b; the demo's Gemini model is set explicitly
(the code's `gemini-2.5-flash` is deprecated), checked against the gateway's LiteLLM before use.

## v0.6.1 (the owner's list, 15 Nov, one list)

- The two Admin forms: model engines and map providers, the key given in the screen (`admin-forms/`, rulings 1-11 kept)
- Suppression taking effect (R7 step 2)
- People shown by name
- A model allowance per visitor
- Laurium's document reading from a screen
- The dead batch job's status
- Entra groups to roles
- Scheduled loads while the owner is away
- A disabled engine's way out closed
- Connection limits from settings
- Fine-grained access control on search
- The production-shape work
- Item 7, two demos on one server (ospreyflow.app, Part 3), and the certificates' automatic renewal
- Item 23, the cloud-platform shape's memory sizes from measured use
- The websites ospreyflow.org and ospreyflow.net published (finish.tsv p3)
- Bedrock beyond London (AWS's EU profile, for current Claude models): to decide (ruling 17)

The orchestrator's rulings on #6's confirming pass (standing rule): headings and form controls on the token scale in both
looks (DESIGN.md's one scale); GOV.UK Frontend's own classes kept; the Studio's em sizes, the mono glyphs and D2's values in scope.

## The GOV.UK demo's Gemini (the owner, 15 Nov ~12:45Z)

- The key on the demo server is on Google's **free tier**: 15 requests a minute, 250,000 input tokens a minute, 500
  requests a day (the owner's figures from Google). Google may use free-tier prompts to improve its products; the demo
  holds synthetic data, and visitors' typed questions go with them.
- Model: **`gemini-3.8-flash`** (Google's newest stable Flash, checked 15 Nov); the gateway's LiteLLM must route it,
  checked at the rebuild.
- The demo's own budget: **1,000,000 tokens a day** (Admin › Models), inside the free tier's daily limit.
- Set at stage 5's rebuild (Wed 18 07:00 UK), then proved from a browser: the engine choice appears and one question is
  answered by Gemini. The visitor sign-in proposal still comes to the owner.

## The owner's word in advance (15 Nov ~18:10Z)

Stages 3, 4 and 5 and the demo rebuild are approved in advance under the conditions in
`OWNER_WORD_IN_ADVANCE_2026-11-15.md`, each to start as soon as the one before finishes, at any hour. The demo's
window is now "as soon as the release is made" (it replaces Wed 18 07:00 UK). Anything in its section 2 stops the run
and comes back to the owner at the top of MORNING.md. Gemini's key: the rebuild runs to the end without it; the Gemini
checks wait for the owner's key, unless 4.3's carry is shown safe by a rehearsal first.

## The GOV.UK demo is protected (the owner, 15 Nov ~22:15Z)

Once the v0.6.0 rebuild is complete and the owner has entered the Gemini key, **nothing disrupts the GOV.UK demo
(govuk.ospreyflow.app, osprey-small at /opt/ospreyflow-v0.6.0) without telling the owner first**: no apply, restart,
rebuild, update, settings change, restore, port or certificate change, and no step of Part 3's cutover. A change is
proposed to the owner in one line (what changes, the expected downtime, the way back) and waits for their word.
Reading it (checks, health, the gate) is not a disruption.
- 16 Nov ~06:50Z: stage 4 may start before CI completes on the candidate, in parallel; the release still needs CI fully green on that exact commit (the owner, amending the word in advance for this run).

## Standing rule: long checks in parallel (the owner, 16 Nov ~07:00Z)

Long checks run alongside each other: the package test beside CI on a candidate; trial builds and server rehearsals beside
CI before a demo update; local merge suites beside the previous push's CI. **The final or public step (a release, a tag,
a publish, a demo rebuild) waits until every check has passed on the same exact commit.** A real failure in any check stops
and discards the others; nothing is released on a partial pass. Pushes still go one CI run at a time (the concurrency group
cancels a run in progress).
- CI speed: split the long jobs (test, conformance, glass-perf-a11y-keyboard) across parallel runners and cache dependencies (uv, npm, docker layers), which also guards against PyPI timeouts like 16 Nov's; a ci.yml change, to the owner as a diff
- **First item of v0.6.1: the Glass, fewer rows above the canvas and a toolbar that can be hidden** (the owner, 16 Nov; brief at `v061/glass-rows/OWNER_BRIEF_2026-11-16.md`, sketch in Claude outputs/ospreyflow_glass_rows_2026-11-16/). The case lane; estimate, proposals, the draft ADR amendment and the measured gain before any building; nothing merges before v0.6.0 is released
- The report sync tested against a real Valkey that requires TLS and a password (rule 15; the stand-in accepted plaintext)
- The report sync's loop survives a Valkey error (logs and retries rather than exiting into a crash loop)
- The report sync survives an unreachable Conduit too: `_pull_dashboard`'s case-list and feed GETs catch httpx.HTTPError as a recorded failure, as the token path does (the package test's row 6 on b6d33ce, 16 Nov: an httpx.ConnectTimeout while step 9 had the api at 0 exited the process; one restart, self-healing, no figures lost; case as deputy: v0.6.1, low); red first with a stand-in Conduit that refuses connections
- The drawn-merge sheet moves focus only when first drawn and when sent, not after each choice (WCAG 3.2.2 On Input; rules-b's audit, 16 Nov), then the spec's waits removed
- **Scope dashboard builders** (the owner, 16 Nov): manage_dashboards limited to the dashboard identities its holder is cleared for, in their own Superset session, not only the guest token; its own ADR (rule 3)
- T on the Map's container hides and shows the toolbar, as on the graph canvas (Glass rows ruling 13; map/MapView.tsx is platform's)
- The guide says a new dashboard is offered in the Glass only once it holds a chart (Superset's own visibility rule; the package test, 16 Nov)
- The guide says a search just after a load or a drawn grid may not find it for some seconds on poc and cloud-platform (ADR-150's asynchronous index; the package test, 16 Nov)
- Spec 08's seeded rows also run on poc, after INSTALL's optional seed block (the package test, 16 Nov)
- Amendment 18's words for an application (app-only) token at v1.0 too: today the run API refuses it with the plain "the sign-in could not be verified" (platform-b's row 9b on ea5fc61, 16 Nov; case as deputy: the operator's own token, not a client user's sign-in, so v0.6.1)
- A backup and DECOMMISSION step 2's last backup in the same minute collide by Job name ("already exists"); step 2 reuses or waits instead (the package test's row 10 on ea5fc61, 16 Nov; low)

## Stage 4 on b6d33ce stands for 529f0f4 (the owner, 16 Nov, through the orchestrator)
The package test passed every row on b6d33ce (platform-b's RECORD_b6d33ce.md, 46a9353). CI on b6d33ce (run 43869826530)
was red on a records row (fixed in 6a99cb0) and two keyboard cases whose harness measured in the runner's fallback face
(fixed test-only in 4fefa51). The owner accepts stage 4 on b6d33ce for 529f0f4 on this evidence:
- `git diff b6d33ce 529f0f4` touches only OspreyFlow_Core/apps/workspace/keyboard/{case-line-type.spec.ts,places-harness.tsx}
  and 8 files under OspreyFlow_Build/process. VERSION, the CHANGELOG, the guides and PDFs, the chart, every Dockerfile,
  .dockerignore, the lock inputs, services/, packages/, harness/ and cli/ are unchanged;
- the workspace's `vite build` from each, on the server, gives a byte-identical dist (59 files; tree hash afd0a61e71b4ff28),
  the only thing the workspace image takes from apps/workspace (platform-b, ~/osprey-runs/platform-b.c8/dist-compare/).
CI on 529f0f4 must still be fully green before "release-ready".
