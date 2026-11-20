# v0.6.2 · the backlog (kept by the orchestrator, 17 Nov 2026)

The next release's list, in one place. Not started: the owner opens v0.6.2. Sources: `v060/RULINGS.md` (the owner's
15 Nov list, which became v0.6.2's when the v0.6.1 patch went first; the 16 Nov findings) and the owner's word of 17 Nov.

## First, on the owner's word (17 Nov ~06:40Z): the default-themed demo, ospreyflow.app (was Part 3)

Stopped 16 Nov ~18:10Z (RULINGS "Part 3 moves"); lane `platform` closed at 63dde62 with its HANDOFF. Order:

1. **Named Small deployments get their own image tags** (`harness/render.py:601`): today every build-from-source
   deployment on a machine shares `osprey/<service>:local`, so building a second one moves the first one's tags (it
   happened to GOV.UK on 16 Nov; repaired with compose `build` only). Red first (rule 15): a test that renders two named
   Smalls and fails while their tags are equal.
2. **The install's sign-in step on a named Small reads `deployments/small`** (`cli/ospreyflow/main.py:1056`;
   `repair-sign-in` already uses `ctx.deployed().name`). Red first.
3. **DNS for ospreyflow.app**: the Porkbun API key has no "dns" scope. The owner's: give it the scope in Porkbun's API
   Access, or add the records by hand.
4. **Then the demo**, beside GOV.UK on the test server: a GOV.UK backup first, the one-line notice, and a check that
   GOV.UK's containers and tags are unchanged afterwards. The alternative (install from v0.6.1's published images, whose
   names are their own) avoids 1 but not 2.
5. ~~The certificates' automatic renewal (item 7's second half).~~ **Done 18 Nov, outside the line, on the owner's word:**
   `backlog/DEMO_CERTIFICATE_2026-11-18.md`. First automatic renewal due 18 Jan 2027, not yet seen.

## The owner's list (15 Nov), carried

- The two Admin forms: model engines and map providers, the key given in the screen (`admin-forms/`; the model form's
  first slice on `lane/platform-admin-forms` 9f6b2c6, not merged)
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
- ~~The production-shape work~~ (L12: dropped, D17, 18 Nov)
- ~~Item 23, the cloud-platform shape's memory sizes from measured use~~ (L14: dropped, D18, 18 Nov)
- Bedrock beyond London (AWS's EU profile, for current Claude models): to decide (ruling 17)
- (The websites ospreyflow.org and .net: published 16 Nov, done.)

## Findings from the GOV.UK rebuild and the v0.6.1 patch (16 Nov)

- The CLI follows the recorded home over the current folder on install (`home.py` `find_product`); every command needs
  `OSPREYFLOW_HOME` today.
- A fresh install from a git archive cannot seed demo packs (`seed_internal.py:611`, no `.git`).
- The places stage attaches the gazetteer to no case.
- `apply` says "nothing was started again" while a service is down, and names `start --name default` on Small.
- `demo add` does not feed the search index (the install built it before the packs loaded).
- Gemini's role is the bare id (`gemini-3.8-flash`; `ModelProviderConfig.route()` adds the prefix): the guide and the
  rebuild sheet say so.
- `apply` does not remake an engine's entry in the gateway's database.
- Test the connection reports the provider's own refusal (a 503's words) rather than "could not be reached".
- The worker_isolation SERIAL gap for `test_scheduler_lifespan`.
- The guides' screenshots, with v0.6.1's Ask drawer capture.
- The release steps' step 10 needs a Docker daemon for `harness.signatures`: run it on the test server (as for v0.6.1),
  and say so in `RELEASE_STEPS.md`.

## Findings from the owner's laptop reinstall (17 Nov)

- A fresh clone of the release refuses `ospreyflow install --mode lite --starter ospreyflow-crime --yes`: "osprey.yaml
  already exists and differs from what these answers make", though the file is the checkout's own committed one. A
  client's first install should not need `--force`: treat an unmodified committed `osprey.yaml` as replaceable.
  Red first: a test installing a starter over a clean checkout.
- A Lite deployment from before v0.6.0 has no way forward but a fresh install, and `backup` needs it running; the owner's
  was archived cold (volume tarballs) before `uninstall`. The guides could say so for Lite.
- (17 Nov, the owner on the GOV.UK demo) **Invite a person** offers a clearance and handling codes above the inviter's
  own: the demo admin (OFFICIAL, P) picked OFFICIAL-SENSITIVE with P, C, R and got 403 `above_your_clearance`
  (`app.py` `_within_your_reach`, ADR-114 Am 5). The refusal shows only in the form's intro text, so the Invite button
  seemed to do nothing. Offer only what the admin can give, and put the refusal by the button (an error summary).
- (17 Nov, laptop) The first install's `compose up -d --wait` hit apply's 1,800 s limit (`harness/apply.py:378`) with
  no container created, though the three images still missing then pulled in 49 s by hand; the re-run went through.
  Pull before `up` as its own step with progress, so a stalled pull is named rather than timed out.

## 18 November 2026: the true backlog (BL2), recorded on the owner's rulings

Judged overnight against main at 528d475, read only (no test run):
`Claude outputs/ospreyflow_evidence_2026-11-18/BACKLOG_VERDICTS_2026-11-18.tsv` and `BACKLOG_SUMMARY.md` (git-ignored; the
closures are committed in `backlog/CLOSURES_2026-11-18.tsv`). 326 rows: 116 built, 138 open, 16 partly built, 19 cannot
tell, 37 not code.

- **Closed, 153** (116 built + 37 not code), accepted by the owner 17 Nov: `backlog/CLOSURES_2026-11-18.tsv`. C023 stays
  closed if ADR-120 Amendment 18 was the owner's ruling (reopen if not; not yet confirmed). The closures include C194
  (the demo certificate's renewal), closed by `backlog/DEMO_CERTIFICATE_2026-11-18.md`.
- **Removed, 3** (D17, D18): L12 (the production-shape work), H06 (spec 08's seeded rows on the proof-of-concept shape),
  L14 (the cloud-platform shape's memory sizes). They were among the 19 that need a run.
- **Open, marked "needs a run or a definition", 16** (the 19 less the three removed): C022, C043, C068, C076, C080, C131,
  C150, C151, C153, C161, C167, C172, C178, C190, C235, L08. L08 (scheduled loads while the owner is away) is folded into the
  whole-dataset load, IS6 (D16).
- **Moved to PL5, demo fixes after the build** (D11, D15): C193 (demo accounts and resets for public demos) and L04 (a
  model allowance per visitor, VA1 on the dashboard). C023 and the PID pipelines are already closed or in PL5.
  Not moved, pending the owner's word: the defects found during the demo rebuild that are product faults (N05, N06, N07,
  N11, C013, C082, H01).
- **Not yet done:** placing the 154 open rows by part and theme (BL2's last clause).

### The security slices after SE1 (the owner's rulings, 18 Nov); on the dashboard's plan by the owner's hand

- **SE2 (C187), after SE1.** The governance edit
  (`PATCH /v1/datasets/{dataset_id}/sources/{source_id}/governance`, `app.py` `edit_dataset_source_governance`;
  `sources.py` `edit_governance`/`_governed`) gets the default-marking route's checks (`default_marking_problems`,
  `sources.py:99-150`): the editor's clearance, the deployment's ceiling, and never below the source's current marking.
  Failing access-control test first. The spec is silent on this route (`spec/03` line 684 gives only the gate); the
  wording and status code are a spec edit in the same slice (rule 11), following the default-marking route's.
- **SE3 (C186), after SE1; merged before the Studio's Model step (IS2) starts.** Only the draft's creator writes to a
  model draft: `TargetModelStore.save_draft`/`open_draft` (`target_models.py:169-176`, in-memory `:245-255`, Postgres
  `:418-434`) and their writers (`studio_release.py:525`, `target_models.py:286-287`, the PUT draft route
  `app.py:11753-11765`) check `draft.created_by == principal.id` (as `studio_release.py:241` does) and confirm the
  version as `replace_own_draft` does (`studio_release.py:228-237`). Keep the owner and version a store argument if that
  avoids changing `TargetModelDraftInput` (`packages/schemas/dataset_model.py:83`, which would regenerate the TypeScript
  types). Failing test first, including the second writer and the stale version.

### New row (18 Nov): the client-name check cannot read inside a PDF, an image or a video

`client_name_check.py` (BL6) reads a file that is not UTF-8 as printable runs of four or more characters
(`identifier_check._read`). Real text inside a PDF, an image or a video (compressed streams, a PDF's own text, an image's
pixels or a video's frames and captions) is therefore not covered: a client name in any of them would pass. The three
files the owner exempted (RULINGS.md, "three compressed files exempt") are the known chance hits; every other such file
is unchecked in the same way. Wanted when the owner opens it: an extractor for each kind (PDF text, image text by OCR,
video captions) behind the same hashed list, or a stated list of the files that matter for the published sites.

### Found by the merge gate on AD2's first merge attempt (18 Nov, ~14:00 UTC)

- **A new HIGH finding stops every merge on the Mac:** `trivy fs` (`core-check`) reports picomatch 4.0.7,
  CVE-2026-112366 (denial of service through repeated extglob patterns), no fixed version, reached through vite,
  vitest and tinyglobby/fdir, all dev tooling (`npm ls picomatch`). No slice touched `package-lock.json`: main fails
  it today. The repository's way is a dated entry in `OspreyFlow_Core/.trivyignore` on the owner's word, with the
  threat model stated and a revisit trigger (as for CVE-2026-85061 and the Pillow entry). Awaiting the owner.
- **AD2's change fails `make test`:** `tests/services/api/test_admin_sections.py` reads 69 more routes into the People
  section, and `schedule_preview_route` is now read by People as well as Operations. The new code in `People.tsx` imports
  something that pulls the workspace's other modules into the section's walk. The slice's checks did not include this
  server-side scan, so neither the builder's Stop hook nor the verifier saw it; the full gate did. Back to the builder
  with that file in its checks.

### New row (18 Nov): GitHub's two warnings on the CI workflow

Both show as annotations on the green run of 18 Nov (run 44257704285) and both need a change to the CI workflow file under
`.github/workflows/`, which is the owner's: it comes to him as a diff, never through a slice.

1. "Node.js 20 is deprecated": `actions/checkout@v4` and `astral-sh/setup-uv@v3` target Node 20 and are being forced onto
   Node 24. The fix is newer major versions of those actions (check what each publishes first).
2. "The `ubuntu-latest` label will migrate to Ubuntu 26 beginning 19 October 2026" (runner-images issue 14748): the
   workflow's `ubuntu-latest` jobs move to a newer Ubuntu without a change of ours. Either pin `ubuntu-24.04` or run the
   suite on `ubuntu-26.04` first; the choice is the owner's. `UV_PYTHON`, the Node major and the browsers the jobs
   install are the likeliest to move with it.

### New row (18 Nov, the owner's word): site plans need rotation and pitch; neither binding allows them

`OspreyFlow_Build/spec/00_ARCHITECTURE.md:70` says rotation and pitch are "Needed for site geospatial, where an aerial
photograph is rarely north-aligned". Neither binding that draws the graph over the map allows them: the workspace's own
`apps/workspace/src/map/sigmaMaplibreLayer.ts` (`@sigma/layer-maplibre` 3.0.0's code) sets `minPitch`/`maxPitch` to 0 and
turns sigma's camera rotation off, and `@sigma/layer-maplibre` 4.0.1 does the same and also makes the map
non-interactive. This was true before GG6 and stays true after it. **Decided when R8 (GG5 on the plan) is planned.**

### New row (18 Nov): the board shows "verifying" for a slice sent back while its old verifier pass is still on the tip

Found when AD2 and GG6 were refrozen by the owner's scripts on 18 November: the board's state logic checks a passing
verifier record on the branch tip before it looks at the phase, so a slice in the building phase with an unchanged tip
shows "verifying, verifier passed" until the builder commits. The dashboard then tells a reader the slice waits for the
merge script when it waits for its builder. The fix is in the line (a line-fixes slice): the phase "building" wins
over a verifier pass recorded for an earlier frozen command set or round, and a test plants it in that shape.

### New row (18 Nov): a finding does not say whether it is a fault in behaviour or a gap in a test

The owner asked on 18 November to see that split in the conductor's reports. The verifier's answer schema (in the seat
runner) has what, evidence, file and line only. For AD2, BL6 and GG6 in their extra rounds the split is asked for through
each brief, as a prefix on "what". The fix is a kind field (fault or test gap) in the schema and the record, and the
board's note counting each.

### New row (19 Nov, the owner's word, from GG6's last verifier): the production-build tile test is in no gate

GG6's production-bundle run (the map-build folder's own Playwright configuration, which builds the workspace as the deployed
image does and asserts that the MapLibre worker is emitted as a hashed .js file and served as JavaScript) is run only by the
slice's frozen acceptance command, once, at its merge. After the merge nothing in the make gate or GitHub's CI runs it: the
glass-keyboard target runs only the dev-server keyboard suite, and the CI workflow runs only the performance and keyboard
suites. Deleting the setWorkerUrl call from the map view would pass every gate. **The owner's ruling:** wire the
production-build test into the gate; the diff (a make target and a workflow step) comes to the owner, not to a slice. The
conductor writes it once GG6 is on main. **Updated 19 Nov (the owner's word):** GG6 is accepted narrower and merges without
the sentence; the ADR-014 Amendment 2 "Still not checked" sentence (this test sits outside every gate) is added later,
together with the gate wiring it describes, in the same change.

### New row (19 Nov, the owner's word, from BL6's last verifier): no test pins the printed line for a path that names the client

BL6 is accepted narrower. The client-name check now reads a file's path as well as its contents, and a hit line shows the
path with the matching word replaced. The tests check that no name and no hash is printed, and the counts, but none pins
the whole printed line (that only the matching word is replaced and the rest of the path is kept), so a change that blanked
the rest of the path would pass. The fix is a test that pins the exact line for a path naming the client and for a
published-site path naming Laurium, planted in the real call-site shape. Not yet assigned a slice.

### New row (19 Nov, the owner's rule): AD2 is set aside at round 5 of 5, with four findings open

AD2 (the invite form offers only what the inviter can give) stopped a fifth time, and the owner's rule of 19 November applies:
set aside, tell him, free GG1. Its branch and records are kept. Open at the last verifier (tip 5eb3791): **two faults in
behaviour.** (1) The form can be drawn before the roles catalogue has loaded, and when that load fails: the gate waits for
the inviter's details and the handling scheme only, but the form also reads the roles to decide which role boxes it offers.
(2) A handling scheme whose classification list is empty counts as loaded, and the form then says what the inviter can give
on the strength of nothing. **Two gaps in a test:** no test makes the roles catalogue late or failed (and the test double
refuses less than the real route's giver rule); no test gives an empty classification list. The pattern across five rounds
is that each round finds one more thing the form reads before it offers a choice; a restart would list every read first and
build one loader that waits for the whole list. GG1 no longer waits for AD2. AD2's merge also settles whether the invite
test in the keyboard walk stays.

### New build row (19 Nov, the owner's ruling): AD5, one loader that waits for everything the invite form reads

The owner's ruling of 19 November: AD2 is merged as it is, on his word (his accept line), with its two faults in behaviour
open. Those two faults become a new build, **AD5** (the id is the owner's; not started, to be started only on his word):
(1) the invite form is drawn before the roles list has loaded, and when that load fails; (2) a handling scheme whose
classification list is empty counts as loaded. The change: one loader that waits for everything the form reads, and the form
drawn only when every read has arrived (the loading or error message otherwise, never a choice and never a statement of what
the inviter can give), as the owner's general design rule for AD2 of 19 November says. **First a scout** (the read-only
slice-scout) lists every read the form makes before it offers a choice: the inviter's details, the handling scheme and its
classification list, the roles catalogue, and anything else it finds; the list goes into the brief, and the builder starts only
from it. The two gaps in a test AD2 left are in scope: a late and a failed load of each read (the roles catalogue first), a
classification list that is empty, and a test double that refuses what the real route's giver rule refuses (rule 15).
**After:** AD2 (merged) and PL4 (the shared package move; the form's code moves with it). **PL4 does not wait for AD5**: AD5
is queued behind PL4, never the other way. Until AD5 merges, AD2's form can be drawn before the roles list loads; the
release notes should say so if v0.6.2 cuts before AD5.

### New row (19 Nov, from SE3's first verifier): the draft's PUT route confirms no version until the Glass sends one

SE3 makes the model draft's creator check mandatory on every write (save, replace, discard) and confirms the version where
a version is passed (replace and discard, by the store; the import path passes the one it planned). The PUT draft route's body
carries no version, so that route confirms none: adding one means a schema change (the draft input type, which regenerates
the TypeScript types) and a Glass change, neither in SE3. ADR-152 decision 11, X5, says "save, replace and delete check the
draft's creator and an expected version", so this half of X5 is **owed**: the Glass sends the version it opened, the PUT route
requires it, and a stale save is refused in words. Owed with the Studio's Model step (IS2), which waits for SE3. Not yet
assigned.

### New row (19 Nov, GitHub run 44464391430 on 4ec3ea7): a line test depends on the dial's time of day

The slice line's own suite (the slice-line-check job) failed on GitHub at 05:21 UTC, our code, no network fault: the test
test_send_back_within_the_rounds_limit_needs_no_owner_line_and_advances_the_round asserts round < rounds_limit (got 1 < 1),
because its world reads the committed dial, and at night (before 07:00) the dial then said thrift, one round. It passes by
day on the Mac and fails at night on GitHub. The owner's dial commit (balanced four rounds by day and night) hides it; the
test should build its own dial in its world and plant one-round and four-round dials (rule 15). For the line-fixes
session. A second line fault the same run showed: after a red run on main, `records` still pushed (push_main defers for a
run in progress, not for a red one), so d376a14 went out right after the red run ended, against the owner's rule 3.

### New row (19 Nov, GG1's six red stops): a slice started before a main commit cannot pass its scans, and has no way to take it

GG1's six red stops on 19 November were all the citations scan (test_the_repository_itself_is_clean) naming the 35 paths of
ADR-152, whose allowlist the owner committed at 06:30 UTC, after GG1 (and SE2, SE4) had been cut from main. The builder cannot
fix main's state, and nothing in the line brings main into a started slice's branch unless the conflict is in the records
folder alone. Fix for the line-fixes session: when the scans are red for a file the slice did not touch and main has moved,
`resume.py` brings main into the branch (as it does for records) and counts the stops as not the builder's. Until then the
builder is told in the brief to merge main first. (From the owner's word on 19 November the conductor brings main into a
slice's branch itself, before the builder's last check, whenever main has moved; the line's code did not stop it. The row
stays for the line to do it.)

### New row (19 Nov, SE2, accepted on the standing line at round 4): the Postgres guard against two governance edits at once is run by no test

SE2's round-3 verifier found that two governance edits of one source at once could put back a lower marking; the round-4
builder made the Postgres store's update conditional on the classification the edit was judged against
(`PostgresSourceStore.edit_governance`, `if_marking`, `SourceMarkingChangedError`; OspreyFlow_Core/services/api/sources.py
about line 649; ADR-140 Amendment 19 decision 4a). Its two-edits tests subclass `InMemorySourceStore`, so only the in-memory
check (about line 390) is run. The SQL (`COALESCE(handling -> 'classification', 'null'::jsonb) = $8::jsonb`, and the branch
after no row comes back: not found versus changed) is exercised by nothing. Accepted on the standing line as a gap in a
test (rule 12, rule 15). Row: a live test against Postgres in the dev stack that races two edits and asserts the lower one
is refused, and the null-or-missing classification case; it is owed with the live step. The default-marking route reads then
writes in the same way (the verifier says so); whether it needs the same condition is a decision for the owner.

### New row (19 Nov, run 44473959795): a live proof is timing-sensitive on a loaded runner

`OspreyFlow_Build/tests/test_worker_isolation_live.py::test_without_the_plugin_each_worker_sees_both_in_every_store_the_red`
failed in CI's conformance job on a docs-only commit (d376a14): its inner run failed on a deadline ("the other worker never
reached objects-removed", over by 0.04 s) and on an object-store path not found (`ospreyflow-staging/t1probe-…`), not on the
red it expects. 1 failed, 3596 passed. The same job passed on dcb51ab. Not recorded as a known flake before this row. Row: the
proof's deadlines should scale with the runner, or the test should wait on the other worker's mark rather than a clock.

### New row (19 Nov): the board shows an accepted slice as "verifying"

After `resume.py <ID> accept` (GG6, BL6) the board reads the slice from its test record and shows "verifying" until the merge.
It should say "accepted, waiting to merge" (and, for a standing accept, the count of gaps in a test).

### New row (19 Nov, GG6; for the owner's next line-fix batch): a mechanical conflict with main costs a round and needs the owner's line

GG6 passed its verifier (496d7b92ce) and was then refused by the merge because its branch no longer merged cleanly onto
main: "lane/slice-GG6 does not merge cleanly onto main: the builder rebases it." The only conflict was in
OspreyFlow_Build/spec/ADR_RESERVATIONS.md, where GG6 and main each appended a row at the end of the table; the answer was
to keep both rows. Because GG6 was at its rounds limit, taking main in cost a sixth round and the owner's `add-round` line
(a builder, a fresh verifier pass, a second merge: about an hour of the owner's wait, for a change that is not the slice's
work). The owner's ruling of 19 November: a slice that only needs main merged in to resolve a mechanical conflict should not
cost a round or need his line. Fix for the line-fixes session: the merge (or `resume.py`, a new action) brings main into the
branch itself when the conflict is only in files a slice has no logic in (the records folder, which `resume.py` already
does, and append-only tables such as ADR_RESERVATIONS.md, resolved by keeping both sides' rows); the new tip gets its
verifier pass as before (the verifier's own cost, not a round, and not counted against the rounds limit); any conflict that
is not one of these named, mechanical kinds is the builder's, in a round as now. Rule 15: the tests plant a conflict in the
real shape (two appended rows at the table's end) and a conflict that is not mechanical (two edits of one row), and show
the second is not resolved by the line. Related: the board's "verifying" label for a slice that has a verified tip and a
new tip with no test record.

### Left stopped for the owner (night of 19 Nov): PL1, PL2 and BL2 each need a decision that is his

From a read-only scout of 19 November. The owner's standing word for the night (RULINGS.md) puts them in the order CO3, BL7, PL2,
PL1, BL2 "when ready", and rule 5 says a decision that is his is left stopped and listed. None was started.
- **PL1, "Laptop demo sound"** (plan row, account Default). No ruling, backlog row or note says what it is; the decision record
  places four demo and install faults under PL1 (N05, N06, N07, N11: OPEN_BACKLOG_PLACED.tsv), none about sound. Questions: what
  does "laptop demo sound" mean, and is PL1 the four D35 rows or a sound fix? Sound cannot be proved by a pure test (it needs a
  physical laptop and audio device). Recommendation: PL1 is the four D35 rows (pure-testable), and the sound item gets its own id.
- **PL2, "Connection limits, Java licence notice"**. Connection limits: the owner's word "Connection limits from settings"
  (15 Nov list) and L10 "partly built": Postgres max_connections is a computed constant (harness/profiles.py, harness/cloud_platform/
  connections.py); nothing reads it from a setting. Java notice: C020, the runtime's NOTICE and GPL-2.0 source offer before any
  image carrying it is published (ADR-147 Amendment 2), which the architecture text calls "a release step, not this register's
  to perform". Questions: what does "from settings" mean (a deployment-config field with the computed value as its default and a
  refusal below a floor?); does the Java notice go into the image in this slice or stay a release step? Recommendation: the
  setting with the computed default, and the notice file in the image with a test on the Dockerfile and the NOTICE.
- **BL2, "True backlog"**: not a code slice. The closures (153 rows) are on main; the placement is not: it lives only in the
  git-ignored decision-record folder (180 rows placed, against the plan's 154 open). Questions: which count the record uses; whether
  the placed table is committed into the backlog folder; the seven proposed ids N19-01 to N19-07 (the conductor renumbers them
  once the owner says); question 23 on C023; and the 16 rows that need a run on a test stack. Recommendation: commit the
  placed table verbatim with its counts note, say "180 placed, of which 154 were open on 18 November" only if the owner confirms it.
- **CO3 is ready only when PL3 merges** (the plan row: after PL3, no Conduit change, three tests through the page service's
  proxy). The conductor's earlier "nothing to build" reading was wrong; the id is kept from when it was thought a Conduit route.

### New rows (night of 19 Nov): gaps accepted on the standing line, and what the night's merges showed

- **PL3 (merged 9745a9f; two gaps in a test, accepted at round 3):** (1) the secret scan in OspreyFlow_Core/apps/pages/test/support/
  secretScan.ts matches only a line holding the setting's name directly followed by `=`, `ENV` or `:`; it misses `{ [NAME]: "…" }`,
  `sessionSecret: "…"`, `process.env["…"] = "…"` and `vi.stubEnv("…", "…")`, which are the shapes the tests use. Also
  secretFiles.test.ts (about line 46) commits a fixed 32-character secret-shaped string as a plant, which the owner's rule ("no value
  committed anywhere, including test fixtures") forbids: use the generator. (2) No test covers the one place the real Valkey client is
  built from `valkeyOptions` (start.ts about lines 64-70); `main` is always called with an injected store. Needs a client factory a test
  can inspect.
- **BL7 (merged 6318956; one gap in a test, accepted at round 3):** no test writes `dial.current = "auto"` back after another value; if
  `auto` were dropped from what the panel accepts, no test would fail (tools/control_panel/panel.py about line 321; one VALID case that
  changes `current` away and back).
- **CO3 (for the owner's decision, from the first verifier):** the Conduit refuses the stream before it accepts the socket, so uvicorn
  answers HTTP 403 with no close code or reason, and a client cannot tell a refused credential (1008) from a principal store that is
  down (1013, retry). The page service therefore maps a pre-accept refusal to 1008 (the same as the Glass gets through nginx today).
  Row: change the stream route to accept and then close with the code and reason, so both survive the handshake. That is a Conduit
  change, which ADR-152 X2 says is not made (an amendment to X2 if wanted), and it also changes what the Glass sees.
- **Line gap (found on PL3's merge):** the slice's checks command runs no linter, so a lint failure (ruff E501 on a PL3 inventory
  line) passed the builder and the verifier and was found only by the merge gate's `make -k ci`. The checks should include
  `ruff check` on the changed Python files and the linter for changed TypeScript.
- **Line gap (found on BL7's verifier):** a test that reads the owner's live yaml files goes red when the owner changes a setting;
  the same class of fault as the dial-dependent test of 18 November. The verifier caught it this time, the builders' briefs should say
  it, and the line's scan could flag a test that reads dial.yaml, accounts.yaml or live_step.yaml from the repository.
- **Line gap (night of 19 Nov):** a seat started with a plain shell `&` has its output discarded and no notification when it ends;
  the conductor now waits on its process. Not a line fault, a practice note: start seats only as background tasks.

### 20 November 2026: the owner's rulings on the three held slices, and what the scouts found

- **PL1 is the four demo and install faults (N05, N06, N07, N11); "sound" meant "in working order"** (the owner). **Not started:** a
  scout found that each of the four rests on a reading of the specification that the owner has not ruled, and process/CLAUDE.md says
  an accepted decision believed wrong is raised, not implemented. Findings, for his rulings:
  - **N05** (the CLI follows the recorded home over the current folder): the code does what ADR-114 Amendment 3 decision 3,
    `10_ADMINISTRATION_GUIDE.md` line 305 and ADR-132 Amendment 1 decision 4 say (env, then the recorded home, then the folder).
    Reading (a): the folder beats the recorded home (an amendment to three accepted texts); reading (b): the recorded home goes stale
    after a repoint or reinstall and is never re-recorded (fix at recording, `install.sh`/`install.ps1`, or a warning).
  - **N06** (a git archive cannot seed demo packs): the refusal is at `scripts/seed_internal.py` 620-626, for every dataset, synthetic
    packs included; the row's line 611 is stale. ADR-114 Amendment 2 decision 2 groups the attested checkout with the real-data
    checks. Reading (a): synthetic packs are exempt, real and internal ones keep the check (the existing test at
    `test_seed_internal.py` 790-793 flips); reading (b): the install must carry `.git`. `seed_paysim.py` 86-87 has the same fault
    in another shape.
  - **N07** (the places stage attaches the gazetteer to no case): by design under ADR-147 Amendments 1 and 2 (copies go in when a
    case's Author adds a gazetteer). Reading (a): a missing demo step (nothing adds the gazetteer to the demo case; depends on
    N06); reading (b): the build attaches to the demo case, which needs an ADR-147 amendment.
  - **N11** (apply does not remake an engine's entry in the gateway's database): `harness/apply.py` never calls the model admin; the
    entries are made again in the Conduit's start (`model_admin.py` 865-975), which returns early with no models file (911-915).
    Reading (a): apply triggers a reconcile; (b): the Conduit's start reconciles after a gateway database change. A wiped database
    probably drops the credential too (inference, not measured), so a remake needs the key again. The stand-in has no
    empty-database shape yet.
  - Cut if the rulings come in two goes: N05+N06 first, N07+N11 after.
- **PL2 is two slices: PL2a (the Java notice in the image, C020) and PL2b (connection limits from settings, L10).** The owner gave no
  floor, no profile scope and no word on the pools; the conductor settled them in the brief from numbers already in the code: the
  floor is 420 (the same sum with one Conduit instead of two), the setting is `resources.postgres_max_connections` on the owned
  Postgres only (a `cluster` or `cloud-platform` profile refuses it in words), the pools stay constants. New amendments: ADR-147
  Amendment 6 (PL2a), ADR-114 Amendment 49 (PL2b). The scout also found a stale "at least 750" sentence in the administration guide
  (corrected inside PL2b). The Java source offer's contact and URL are not in the repository: the notice carries the tag and the
  `jlink` line, and the owner supplies the rest.
- **BL2 (done):** the placed table, its counts note and a note giving both counts are committed under `backlog/`
  (`OPEN_BACKLOG_PLACED_NOTE.md`). 180 placed; 154 open on 18 November (138 open + 16 partly built); the difference of 26 is the 19
  "cannot tell — needs a run" rows plus the 7 proposed rows N19-01 to N19-07. N19 ids stay as proposed.
- **PL3's fixed secret-shaped string** (`secretFiles.test.ts` about line 46): the owner's word is to fix it in the next slice that
  touches `apps/pages`, with the generator, and tests generate one at run time. That slice's brief must carry it.
- **Line gap (BL6's first merge attempt, 20 Nov):** `tests/test_lanes_heartbeat.py::test_shows_run_at_once_do_not_mix_their_lines`
  failed once in `make test` (its `show` output cut off before the "NEEDS YOU" section while 16 copies ran at once under xdist),
  with `make -k ci` green; the retry with nothing else running is recorded in the merge records. A timing race in the test, like
  `test_stack_lease.py::…extra_arguments` on 19 November: worker-isolation timing, same batch row.
- **AD1 is released for scouting, not building:** the proposed cut is `slices/AD1_PROPOSAL.md`. PL4 and AD5 stay held.
