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
**After:** AD2 (merged) and PL4 (the shared package move; **only the form's plain parts**, `givableCodes`, `givableLevels` and the
like, move to `packages/glass-shared`: `People.tsx`, the loader AD5 builds and every other React component stay in the workspace,
as I1 requires; the owner, 20 November). **PL4 does not wait for AD5**: AD5
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
  **Updated by the owner's word of 21 November (file 008):** the seven rows are accepted and renumbered **N16 to N22**
  (`backlog/N16_N22_RENUMBERED_2026-11-21.md`; N19-04 becomes N18, ahead of the other new ones, with the security builds);
  the 16 "needs a run" rows are one run-sheet row, RS1, plus seven that need the client's environment or his definition
  (`backlog/BL2_RUN_SHEET_2026-11-21.md`); C023 stays set aside with the demo items, to be settled with PL5, and holds neither
  BL2 nor CO1.
  **BL2 is marked done (the owner, file 009, 21 November), with these papers on main; CO1's row and brief are written
  (`slices/CO1.md`).** The seven parked rows and the move of C150 and C131 to Later are in `RULINGS.md` (21 November). The
  plan page's mark is the adviser's.
- **PL3's fixed secret-shaped string** (`secretFiles.test.ts` about line 46): the owner's word is to fix it in the next slice that
  touches `apps/pages`, with the generator, and tests generate one at run time. That slice's brief must carry it.
- **Line gap (BL6's first merge attempt, 20 Nov):** `tests/test_lanes_heartbeat.py::test_shows_run_at_once_do_not_mix_their_lines`
  failed once in `make test` (its `show` output cut off before the "NEEDS YOU" section while 16 copies ran at once under xdist),
  with `make -k ci` green; the retry with nothing else running is recorded in the merge records. A timing race in the test, like
  `test_stack_lease.py::…extra_arguments` on 19 November: worker-isolation timing, same batch row.
- **Line gap (20 Nov, the second day running): a builder that stops red only on a check that passes once main is merged in should
  be recovered by the line itself, with no line from the owner.** PL6's builder red-stopped (six tries) on one check,
  `test_doc_citations_check`, which failed on a citation in a brief the conductor had committed to main after the slice was cut and
  fixed the next minute; the check was green as soon as main was merged into the branch. It cost the owner a `clear-stop` line.
  (The day before: GG1, SE2 and SE4, the same kind of stop, three lines.) Row: when a slice reaches its red limit, the line
  merges main into the branch itself (the same merge the builder is told to do; a conflict stops it as today), reruns the checks,
  and if they are all green clears the stop and records it (the red stop, the main commit merged, the rerun's result); if any check is
  still red, or the merge conflicts, the stop stands for the owner as now. Never counts a round. Tests, red first: a stop whose only
  red is a check fixed on main (cleared, recorded), one still red after the merge (stands), one whose merge conflicts (stands). Related:
  the earlier row on a slice that only needs main merged in to resolve a mechanical conflict.
- **Rows from the stage 4 scouts (20 Nov):** (1) add the "who can" tip to the React Connect screen and the rights check to the React drawn-merge screen (the
  pages carry both; the React screens have neither, the owner's ruling); (2) PL10 leaves the Conduit's one multipart route, `POST /v1/investigations/{id}/sites`, to
  a later slice: recommendation, pass the multipart bytes through unchanged (a Conduit change to raw is ruled out by ADR-152 F1), the owner rules; (3) PL9a leaves
  `kc_idp_hint` (organisation sign-in, which the Glass takes) to a later slice; (4) the nginx default body size (the template sets no `client_max_body_size`) may
  refuse uploads above 1 MB through the Glass today, unverified: a live check; (5) `oidc-client-ts` has no named entry in `00_ARCHITECTURE.md` section 7 although
  the Glass's `userManager.ts` says section 7 is its allowlist; (6) the stale fixed text "move-between-the-four-places" in the Studio keyboard registry (five
  tabs); (7) keyboard specs are missing for the Releases tab, Connect, Profile, Deduplicate, the source page and the Runs grid (rule 13); (8) CO2 is still not on
  main, and the Entra half of PL9b waits for it.
- **Small slice after PL10 merges (the owner's ruling, 20 Nov): decouple the page service's public origin from the Conduit address.** Today
  `config.ts` ties them (`streamSettings` throws when `OSPREY_PAGES_CONDUIT_URL` is set and `OSPREY_PAGES_PUBLIC_ORIGIN` is not: CO3's start refusal), so the HTTP
  forwarder (PL10) needs a setting it does not use. Change: the forwarder needs only the Conduit address; the stream proxy needs the public origin and is **absent**
  without it (every upgrade 404, in a log line in words); CO3's refusal test changes with it (`apps/pages/test/server/stream.test.ts`: "the service refuses to start in words
  with the Conduit address set and no public origin" becomes "with no public origin the stream is absent and the forwarder still serves"). Red first on both halves. After PL10; not
  in its round 2.
- **AD1 is released for scouting, not building:** the proposed cut is `slices/AD1_PROPOSAL.md`. PL4 and AD5 stay held.
- **Line gap (20 Nov, PL9a's verifier start):** `common.write_json` writes through a fixed temp name (`<file>.tmp`) then `os.replace`. `run_seat.py`'s `record_limits` writes the
  account file (`accounts/sol.json`) from every seat of that account, so two or more seats of one account that report their limits at the same moment race on `sol.json.tmp`:
  one replaces it, the other finds it gone and the seat's launcher dies with `FileNotFoundError` seconds after starting (PL9a's verifier, started with PL4a's, PL2a's and PL10's seats).
  No child process was left behind; the seat was restarted by hand and ran. Fix for the line's own session: a temp name unique per writer (pid and a counter) in `write_json`,
  or a lock around the account file; test: two threads writing the same file, red on the fixed name. Until then the conductor starts same-account seats a few seconds apart.
- **Line gap (the owner, 20 Nov, 10(a)): the builder's Stop check always runs lint and the scan-map check, whatever the brief's checks say.** PL1a went through a builder, a verifier and
  a pass, then its full gate went red in the first minute on one docstring line of 101 characters (`ruff` E501 in `cli/ospreyflow/home.py` under `OspreyFlow_Core`), because its checks command never ran
  ruff; CO2, PL2a, PL2b and PL4a would each have been refused at merge for a test with no scan-map row. The Stop check should run, on the files the branch changes: `ruff check` (the repository's
  settings, `OspreyFlow_Core` only: nothing in `OspreyFlow_Build` is linted by ruff), `npm run lint` on the changed script files, and `scan_select.unmapped` for every test the branch adds
  (with the slice's waiting row applied in memory). Until then the conductor runs the same three before a slice joins the merge queue (the conductor's helper, in its scratchpad).
- **Line gap (the owner, 20 Nov, 10(b)): a slice whose only open finding is a test gap is offered to the standing accept before it is sent to another round.** PL9a's round-3 verifier found one
  gap in a test (the success path never asserts the login cookie is cleared); `run_seat.py` tried the standing accept while PL1a's merge held the lock ("another merge is running"), the
  slice went to round 4, and `resume.py PL9a accept` then refused ("not waiting on its verifier's findings"). Fix: when the accept is refused only for the lock, the slice stays in `verifying`
  and the accept is retried when the lock is free, before any round is spent.
- **New small slice, to be cut in the Ground lane (the owner, 20 Nov): a gate check that no secret-named setting has a literal value in any tracked file.** The check fails if any setting whose
  name ends in `_SECRET`, `_KEY`, `_TOKEN` or `_PASSWORD` has a literal value in any tracked file (examples, compose files, fixtures, tests), with a planted fault (the shape the check really sees at its own
  call site, rule 15; red first, then green on the real tree). Tests that need a value generate it at run time. **It closes two open items for good:** PL9a's gap in a test (brief item 5: no value of the
  new `OSPREY_PAGES_CLIENT_SECRET` committed anywhere; accepted narrower on the standing word) and PL3's fixed secret-shaped string in a test plant (the 20 November ruling had it fixed in the next slice that touches
  `apps/pages`; this check makes that ruling a gate). To settle when it is cut: which existing literal values are legitimate (empty values, placeholders and `${...}` references are not literals) and how they
  are listed; whether the check joins `make ci` (rule 15: only after it has been shown red).
- **ADR-152 I9 has no proof on main (found 20 Nov while writing PL4b3's brief).** The four proof pieces the ADR names for "the default tree never shows the crown, the GOV.UK logotype or the GOV.UK typeface" do not exist:
  `tests/glass_trees/test_default_tree_carries_no_govuk_assets.py`, `apps/pages/test/govuk/identity.spec.ts`, `test_govuk_identity_is_off_by_default` in `tests/harness/`, and a `govuk_identity` case in `apps/workspace/src/brand/brand.test.tsx`
  (the first two are in the citation allowlist as deliberately absent). Owner: the build that adds the default tree's assets (the first page build that loads a stylesheet or font, PL7) owns all four, named as a prerequisite in its brief. PL4b3 carries
  only the font half (no `GDS Transport` in anything `apps/pages` serves) and says so.
- **Release notes for v0.6.2 (the owner, 20 Nov): name SE5's fix in plain words.** Draft for the notes, to be checked against the builder's report: "A change of an AI model's address that failed part-way could leave the model's entries at the new address while the
  record still said the old one, so a key entered afterwards could be sent to an address it was not entered for. A failed change now removes what it made or marks the model unavailable and says so, and start-up checks every entry's address against the record." (SE5; found on main by a scout on 20 November.)
- **Line gap (PL9a's first two merge attempts, 20 Nov): two flaky tests in the Mac's `make test` step, each unrelated to the slice.** First attempt: `tests/test_measure_search.py::test_m10_is_measured_only_when_90_percent_of_the_controls_reach_their_record[2-unmeasured]`
  (verdict "not met" where "unmeasured" is expected; the fake Conduit sets class state `_Conduit.leak_world = True` and several parametrised cases share it, so an order or worker dependence is likely). Second attempt: `apps/workspace/src/App.chrome.test.tsx`
  "24 controls stand before the canvas, in this order": the label "Rules and Monitoring 3 open" was received without its "3 open" (a count that arrives asynchronously; the test does not wait for it). Each cost a 25-minute attempt. Both want a fix of their own (the first in its fixture, the second by waiting for the count), as one small slice, and the line should say in its refusal
  when a failing test is not in the files the slice changed (so the conductor can retry without reading the log).
- **Line gap (the owner, 20 Nov): when `gh run view --log-failed` shows only the command, read the job's full log and search it for the summary lines.** The two red GitHub runs (44730215386 and 44739376824) failed `tests/services/api/test_auth_entra_pages.py::test_a_token_from_a_realm_client_without_the_audience_mapper_is_refused`
  ("Signature has expired": a token minted at collection, 300 seconds of life, a 40 to 49 minute suite), and the conductor could not read the names because `--log-failed` and `--log` returned only the command line or nothing; the owner found them in the job's full log. `watch-github` should fall back to the job's full log (the REST logs endpoint or the web log) and search for `FAILED ` and the pytest summary lines, and say in its record when it could not read the names, instead of recording "2 failing tests" with no names. Fixed for this case by CO2b.
- **SECURITY ROW, first in the workspace queue after PL4's slice E (the owner, 20 Nov): the Glass writes a shared view's default name "Selection of N nodes" from the creator's selection, and that name reaches every reader.** **Can it reveal a count to someone who may not see every item? Yes.** `apps/workspace/src/views/ViewsPanel.tsx` (about line 42) builds the default name from the number of nodes the creator selected; the server stores and returns the name as given; a reader with a lower clearance who opens or lists the shared view sees the creator's unfiltered count in its name, even after SE7 makes the `chosen` and `missing` counts the reader's own. The count is the same one C045 closes on the wire, carried in text. The fix is in the Glass (stop writing a count into a default name: a name that does not count, or a name only the creator sees), with a test that fails when a default name carries a number the reader cannot reproduce; it touches `apps/workspace`, so it waits for PL4's slice E and runs first of the workspace slices after it. Until then SE7's report says it is open; a server-side rewrite of default-pattern names for readers is the interim, if the owner wants one.
- **Release notes for v0.6.2 (the owner, 20 Nov, replaces the draft above): SE5, and what is still open until AD1 lands.** In plain words: "A change of an AI model's address that failed part-way could leave the model's entries at the new address while the record still said the old one, so a key entered afterwards could be sent to an address it was not entered for. This is fixed: a failed change removes what it made or marks the model unavailable and says so, and start-up checks every entry's address against the record. **Still open until the Admin model form is rebuilt (AD1):** after a rare double failure during a change to a model's address or key, a model may be offered with no key behind it, or the audit may say the change was put back when it was not. No key is exposed." (SE5 merged on the owner's accept, 20 November; the open rows are AD1a's rows 29 to 38.)
- **PL4b2's one gap (the owner, 20 Nov): the proof that the re-stamped install-page files hold the same bytes before and after the move.** PL4b2 merged on the standing rule with this gap; the case that lists the stamped files' contents by byte hash before and after and shows only the paths differ (the owner's addition to B and B2) is not held by a test that fails if the bytes differ. A small test, red first with a changed byte, in the next PL4 slice that touches the stamp lists or on its own.
- **For PL7's brief (the owner, 20 Nov, not for slice C): the pages image will need `packages/glass-shared` copied in when the first page imports from it.** `OspreyFlow_Core/apps/pages/Dockerfile` copies only `apps/pages` and the shared package's `package.json` for `npm ci`; the first page that imports from `@ospreyflow/glass-shared` needs `COPY packages/glass-shared/src` in both its install stages and its runtime stage as the image's layout requires, and PL6's scan (the pages image carries no React) must stay green. The same applies to `packages/design` if a page serves its CSS (fonts rule: PL4b3).
- **Slice C's open points, all settled by the owner (20 Nov):** `conduitRequest.ts` moves only if it imports nothing from the map library (it imports nothing: it moves); `graphology` and `zustand/vanilla` become real dependencies of the shared package, entered in the licence register before the install, with the no-React check and PL6's scan shown green after; the four files the scout did not read were read by the conductor before the brief (it changed the brief: tests stay in the workspace; `registryCoverage.test.ts` in both the workspace and the harness is repointed; `undefinedTokens.test.ts` is extended to the shared package).
- **OWED, SE6a merged without it (the conductor's miss, 20 Nov): the administration-guide sentence that a Superset chart needing Mapbox tiles will not load, and why** (the owner's addition to SE6a's point 2: no outside address is allowed in Superset's content policy and no map key is set; an administrator wanting such a map would need a setting added by its own build). The round-1 verifier did not flag it, the round-2 and round-3 builders left it, and the conductor did not check the merged guide before saying SE6a was done; `OspreyFlow_Core/docs/administration-guide.md` on main has no such sentence. **Carried by DC1c** (it edits the same guide, so one version row and one PDF remake); until then the guide is silent on it. Recommended to the owner as the cheapest place; the alternative is its own tiny docs slice.
- **Line gap (20 Nov, three times in one afternoon): `merge_slice.py records` and every `resume.py` action take the merge lock, so each waits out a whole 25-minute merge.** The conductor could not commit NET1's row (so NW1 could not start), could not apply SE5's add-round, and could not commit the rename of the owner's two-letter ids, each for the length of a merge, while the work they free was the priority. Records mode changes only files under the v062 folder and `resume` changes only a slice's state file: neither touches main's tree or the merge's scratch worktree, so they could take a short second lock (or none) instead of the merge's. The conductor's workaround is to commit records and apply resumes **before** starting a merge; this row asks for the line to do it.
- **Plan ids (20 Nov): the line reads only two-letter plan ids (`common.py` line 84, `[A-Z]{2}\d+`); the owner renamed NET1 to NW1 and DOC1 to DC1.** `slice-line/proposals/PLAN_ID_PATTERN.diff` (`[A-Z]{2,4}\d+`) stays a proposal for the next line-fix batch, under the once-a-day rule; not applied today.
- **AD1a's key-path table must include the SE5 case (the owner, 20 Nov, item 6):** a failed or interrupted address change followed by a failed undo and a later key set (the main-code fault SE5 fixes). AD1a merges main in after SE5 and keeps the stronger behaviour of the two.

## 21 November 2026: test gaps accepted narrower (each a backlog row; the owner's order, the licence gate's own refusal first)

Accepted on the owner's standing line (gaps in a test only, from round 3) or his `accept` lines of 21 November. No fault in behaviour is open in any of them. **Rule 12: each is an invariant stated and exercised by nothing; each row names the planted fault that shows it red.**

**First of the open ones (the owner, 21 November, on accepting PL4d3d at round 8):** **PL4d3d, no test runs the part of `rebaseline` that builds the workspace itself.** `OspreyFlow_Core/scripts/dist_compare.mjs` lines about 796 to 800 (the branch without `--dist`: `spawnSync("npm", ["run","build","--workspace","apps/workspace","--","--outDir", scratch, "--emptyOutDir"])` into `<baseline>.new-<stamp>`, deleted in `finally`) is exactly what the conductor's merge-time command runs, and every `run_rebaseline` call in `OspreyFlow_Build/tests/glass_trees/test_pl4d3d_declared_units.py` passes `--dist`. Round 8 had changed the one test that ran it (it now builds first, then passes `--dist`). Low impact: if the build fails the step throws and leaves the baseline untouched; if it builds the wrong output the declared-units check refuses; either way it fails loudly at the conductor's merge. Test: run the in-tree branch on a scratch copy of the tree (the script's `CORE` pointed at the copy), plant a build that writes the wrong output and assert the step refuses and the baseline is untouched. Until it exists, the conductor checks the step by hand at each merge that runs it (the owner asked for it at PL4d3d's; the result is in the report of that merge).

1. **PL11, a conditional register row whose licence fails its stated test is never shown flagged (first: it guards the licence gate's own refusal).** `OspreyFlow_Build/tools/licence_register.py` lines about 582 to 585: remove them and no test fails. Test: plant it on the real GDS Transport row (F3) with `test: osi-software`, its restricted licence text and `status: conditional`; assert the "does not pass the test osi-software" message names F3.
2. **PL11, the register pin the code no longer names, when the code still names the thing under another pin.** `licence_register.py` lines about 652 to 653: no test drops one pin of a name the code still names. Test: change `services/laurium/Dockerfile`'s FROM in the sources dict to another image, register that image, and assert the pin message for the second Python row (B13b).
3. **IS5a0, the people-section words test does not read the pages roots.** `OspreyFlow_Build/tests/test_people_section_words.py` line about 95 (`GLASS_ROOTS`): add `apps/pages/tree-default`, `apps/pages/modules`, `apps/pages/server/views` and the `.njk` suffix; plant a template saying "Admin › People" without "and roles".
4. **IS5a0, the guide-navigation words test does not read the pages roots.** `OspreyFlow_Build/tests/test_guide_navigation_words.py` line about 125: the same extension and a planted old view word in a template.
5. **SE8a, nothing shows the `asyncio.shield` carries weight.** `OspreyFlow_Core/services/api/model_calls.py` line about 129: replacing `await asyncio.shield(writing)` with a plain `await` fails no test. Test: a pool whose `execute` awaits an event, a second cancel while the write waits, and the `model_call` row still lands.
6. **SE8a, a folder the scans claim to walk (`connectors`) does not exist at the top of Core.** `OspreyFlow_Build/tests/services/api/test_model_call_attribution.py` line about 1063: drop `connectors` from the list and from the scan row, or assert every walked folder exists.
7. **DC1b, the export-scope check misses the sites' own verb.** `OspreyFlow_Build/tests/test_site_intent.py` line about 305: `RECORD_WORDS` has no "recorded" or "logged"; plant "Case reads, changes and exports are recorded against a person." on a page outside `LEDGER_PAGES` and show it flagged.
8. **DC1c, nothing stops "everything crosses a port" coming back.** `OspreyFlow_Build/tests/test_intent_in_the_guides.py` line about 274 (`PORT_CLAIM`, `_QUANT`): "Everything" never matches; add "everything ... crosses/passes ... port" and "every read through the ports", and plant each of the four sentences round 7 removed.

9. **SE8a, a test that waits for ever when the code under test is absent (found by the merge's red-before run, 21 November; a follow-up slice, not a round: SE8a is verified).** One of the 24th-onward tests of `OspreyFlow_Build/tests/services/api/test_model_call_attribution.py` awaits an event only `model_calls.py` sets; at the base it hangs instead of failing. Bound every such wait (`asyncio.wait_for`) so the file fails in seconds when the code is wrong; show the file red against the base commit in under two minutes. Slice name proposed: SE8e. (The merge of SE8a was carried past this by ending the hung red-before run, as `LINE_FAULTS_2026-11-21.md` item 6 says.)

10. **PL13b, no pure test checks that the gateway build's licence gate reads the folder the install writes to (accepted narrower at round 4 on the standing line, 21 November).** `OspreyFlow_Build/tests/harness/test_own_gateway_image.py` line about 443: `test_the_dockerfile_runs_the_gate_over_the_installed_venv_and_the_app_root` says in its name that it checks the installed venv but never reads the gate's path argument, and the gate also passes when it reads no distributions at all. Test: plant a Dockerfile whose gate argument names a folder the install does not write to (and one whose folder is empty) and show the build's gate refuses both; rule 12 invariant: "a proprietary distribution fails the build" depends on that argument.

11. **CO1, no test covers the job ids kept on the published-pipeline path (accepted narrower at round 3 on the standing line, 22 November).** `OspreyFlow_Core/services/api/recipe_run.py` line about 445: in the published-pipeline branch of `_execute_recipe_run`, `report.resolution_jobs.extend(...)` runs once per branch and no test runs that branch; put the old discard back and every test stays green. Test: run a published-pipeline recipe against a stand-in job source and assert the job ids reach the report; plant the discard, red.
12. **CO1, no test shows the job ids reaching the person (same acceptance).** `OspreyFlow_Core/services/api/load_records.py` line about 212: a reader learns the ids only from the run route's answer through `report_view` and `_load_view`; no test checks that the answer carries `resolution_jobs` when the reader may see the counts, nor the schema's own stated rule (`packages/schemas/ingest.py` about lines 1188-1190). Test: a reader who may see the counts gets the ids and one who may not gets none; plant a view that drops them, red (rule 4: a read path gets its access-control test).

13. **IS5a, no test exercises the rule that a held release folder is bound to the case and dataset it was read for (stopped at round 8 on gaps only, accepted narrower on the standing line, 22 November).** `OspreyFlow_Core/apps/pages/server/studio.ts` line about 614: the route refuses a token whose folder was staged for another case or dataset (`folder.caseId !== caseId || folder.datasetId !== datasetId`, answered 410); delete that clause and every test stays green, and a folder read for dataset A could be checked and imported into dataset B by posting the same token with a different case the person also holds. **A security-adjacent row: first among IS5a's.** Test: stage a folder for case A and dataset X, post its token for dataset Y and for case B, and assert 410 and nothing written; plant the deleted clause, red.
14. **IS5a, no keyboard case drives the Studio frame's dataset switch end to end (rule 13), nor its self-submitting enhancement.** `OspreyFlow_Core/apps/pages/modules/studio-frame.ts` line about 27: scenario SF2 in `spec/08` says "A GET form with a button; the select submits itself as an enhancement"; a wrong selector `#studio-switch select[name='dataset']` or a switch that cannot be reached by keyboard would fail nothing; the other two `submitOnChange` enhancements are covered (SK2, SK3). Test: a keyboard case that reaches the select, changes it and ends on the other dataset, with scripts and without; plant a wrong selector, red.

15. **SE6b, the new function that answers "is this identity current?" can be called by the reader login, so the stated property "the record of removals is not readable by Superset's role" is only partly true (accepted narrower at round 6, 22 November; the owner's call, see the morning report).** `OspreyFlow_Build/tests/services/api/test_removed_identity_mart_rows.py` line about 1666 (`test_the_reader_role_is_never_given_the_record_of_removals`) checks only that `ensure_reader` grants nothing on the control schema; the SECURITY DEFINER function `osprey_reports.dashboard_is_current(text)` sits in the schema the reader may use and Postgres lets PUBLIC execute functions by default, so the reader login can ask it, for any client id (the ids are guessable: `osprey-dashboard-<slug>`), whether a removal stamp exists. The verifier's reading: it reveals that a removal happened and none of the identity's rows; only Admin and Alpha (the accepted whole-mart readers) can run SQL, through SQL Lab; the guest role (N18) cannot; so the brief's rule is not broken, and whether the yes/no answer is acceptable is the owner's call. **Fix if the owner says no:** `REVOKE EXECUTE ... FROM PUBLIC` and grant only the row-security path that needs it, with a test that the reader login cannot call it (against the fake and the real database).
16. **SE6b, the row-security claim is tested only against a hand-written fake, never a real Postgres (rule 15).** Same test file, line about 210 (`FakeMartPool.reader_sees` and `_allows`): the real database must let the reader EXECUTE `dashboard_is_current`, the function body must be valid under `SET search_path = pg_catalog`, row-level security must not bypass the reader login role, and `ReportFreshness.stamp/purge/reopen` (`to_regclass`, `pg_advisory_xact_lock(hashtext($1))`) must run. **Owed to the evidence seat RS1 (a leased Postgres):** one run that does each against the real mart, with the reader login, and records what the real database refuses.

17. **Slice E leaves five files to split and three structural types unmoved, to be cut when a page build needs one (the owner, 22 November, file 013; so the later split is not forgotten).** In `OspreyFlow_Core/apps/workspace/src/canvas/`: `iconImage.ts` (browser `Image` and `URL.createObjectURL`; imports `color/nodeVisual`), `linkMenu.ts` (imports `RadialMenuItem` from `design/primitives/RadialMenu.tsx`), `selectionActions.ts` (imports from `design/primitives` and `SelectionBar.tsx`), `toolbarCompact.ts` (React `createContext` and hooks, with plain parts) and `toolbarVisibility.ts` (React hooks, `localStorage` and `window`, with plain parts). **The three structural types:** `RadialMenuItem` (declared in `design/primitives/RadialMenu.tsx` lines 3-22), `SelectionBarProps` (`canvas/SelectionBar.tsx` lines 21-48) and `degreeShown` with `ROUTE_NODES` (`canvas/SelectionBar.tsx` lines 13-19); their only plain consumers are `linkMenu.ts` and `selectionActions.ts`, which stay. **When a page build needs one of the five, it says so and the split is cut then as its own slice with declared units** (the types move with it, as two small edits to `RadialMenu.tsx` and `SelectionBar.tsx`, each a declared unit: the D3e precedent). Also left in the workspace by the same ruling: the three community files (`communities`, `communityAssigner`, `communityWorker`), `labelChoices` and `iconChoices`, and the three files that import them (`linkCollapse`, `nodeLabel`, `nodeAttributes`).

18. **The Matrix view's first frame sits at its budget on the owner's Mac (22 November, taken before slice E; not slice E's fault, the owner's word).** `OspreyFlow_Core/apps/workspace/src/matrix/MatrixView.budget.test.tsx` (`BUDGET_MS` 2,500 ms, §5's first-frame budget at 50,000 nodes and 250,000 links): vitest's own duration for the test was 2,553, 2,481 and 2,532 ms on three runs (`OspreyFlow_Build/process/lanes/v062/PL4_BUDGET_FIGURES_2026-11-22.md`), within a few percent of the limit; the test asserts its inner `elapsed`, which passed each time. It is a margin problem, not a failure: a slower Mac or a loaded runner will turn it red (the load-sensitive list already names this file). Row: say what the test's inner elapsed is (print it), find what the first frame spends (the matrix draws one page of each table), and either speed it or set the budget from §5's own number with the owner's word.

19. **RL1's manifest: no test checks the summary's "not determined" figures (22 November, RL1 accepted narrower at round 3 on the standing line).** The count line ("Files whose `release_images` has `not determined`: N", `OspreyFlow_Core/scripts/maintainer_manifest.py` about line 1250) and the per-image "Files not determined" and "Why" columns of the Released images table (about lines 1370 to 1383) have no test; the only check asserts the words "not determined" appear in the summary, which `render_summary` always writes in its explanation of the columns, so it cannot fail. Brief items 5 and 6 require the figures. **Not release-blocking: the figures are a report, not a gate.**
20. **RL1's manifest: three Dockerfile cases that must read "not determined, never a guess" have no test (22 November, same acceptance).** A `RUN` that bind-mounts files from the build context (about lines 755 to 761, which mark the stage unresolved), an `ADD` of a local archive that Docker unpacks (about lines 804 to 806), and an `ADD` or `COPY` of a URL, which should be skipped as fetched content (about lines 802 to 803). Removing the bind-mount branch would leave files mounted into a build step as `none` when they may reach the image, and no test would go red. **A planted removal of each branch shows the test is owed.**

21. **A test that depends on chance sits in the gate: `test_pl4d3d_declared_units.py::test_two_builds_in_one_tree_collide_and_two_builds_of_build_to_do_not` (22 November, the owner's word: it should not).** It plants two `npm run build`s at once in one tree and asserts that one of them collides within five tries ("a race is not certain": its own docstring). On the demo server slice E's tip `e94369945c` was **red once** on it (run `f138232dfb76da27`, 2,033 s) and **green on the same tip** the second time (1,930 s); it passed in 3 to 4 s on the Mac when I ran it by hand twice. A gate that depends on a race happening is red or green by chance. **A fix keeps the proof that the collision exists without relying on it: plant the collision deterministically (run the second build after the first has begun its sync step, or point two builds at one folder by a lock the test holds), or move the race-dependent half out of the gate and keep the half that proves two private builds do not collide.**

## 21 November 2026: v0.6.2 release-note item (the owner, AD1a option c)

- **Three cases leave an engine's access token on the gateway.** In plain words: "When the deployment is switched to local-only, when a models file is restored, or when a re-render drops an engine, that engine's access token on the gateway is not removed. It reaches no model unless an engine of the same name is added again." Row N6 (a changed master key) stays named beside them. AD1b corrects the specification's false sentence ("no key outlives its record") with its own check (`slices/AD1b.md`, items 3 and 4); the notes carry it until AD1c or a later slice closes it.

## 23 November 2026: flakes and a fourth route (the owner, in chat)

- **Row 22: `tests/test_worker_isolation_live.py::test_without_the_plugin_each_worker_sees_both_in_every_store_the_red` is a live timing race.** GitHub's `conformance` job failed it once, on `4e2086c` (run `45135813072`, 23 November): "the other worker never reached objects-removed", a clock check `2922.475 < 2922.4395`, missed by 0.036 s. **A flake: it stops no merge. If it fails a third time it comes to the owner as a part** (the count is one so far; the second and third failures are to be recorded here with their run ids).
- **Row 23: `tests/services/api/test_alert_address_live.py::test_the_address_answers_through_the_real_stores_and_refuses_alike_on_one_quantum` is a live timing race.** GitHub's `conformance` job failed it once, on `98dfe9a` (run `45114981928`, 23 November). **A flake: it stops no merge. If it fails a third time it comes to the owner as a part** (one so far).
- **Row 24: `tests/harness/test_image_references.py::test_every_third_party_image_reference_resolves[ghcr.io/speaches-ai/speaches@sha256:21e3df06…]` fails when a registry answers 503.** GitHub's `test` job failed it once, on `900792c` (run 406, 23 November): `docker manifest inspect` got "received unexpected http status: 503 service unavailable" from ghcr.io, and the test's list of "the registry refused to answer" markers (`_REFUSED_TO_ANSWER`) does not hold a 503, so it fails as if the image did not exist instead of skipping with the reason. **A fault in the test (rule 15: a fixture that models the registry's refusals, not only its grants), not in the image or in the commit it ran on (a docs commit).** One failure so far; **if it fails a second time it comes to the owner**; a small part (add 503 and 502 and 504 to the markers, with a planted case for each) is proposed, no row yet.
- **Row 25 (IS2a, accepted narrower on the owner's standing line, 23 November 11:22): the store's matching-rule check leaves retired records out on purpose, and no test covers either case.** `_refuse_a_rule_a_reference_cannot_use` in `OspreyFlow_Core/services/api/target_models.py` (about lines 204 and 208): a retired indexed property is not counted as something a rule may match on (`extension.retired_in is None`), and a retired entity type's rule is not judged (`extension.retired_in is not None`). Delete either condition and every test still passes. A test for each, planted at the shape the store reads, red first.
- **The release note's three cases are four (the owner, AD1b fault 1, option A):** the fourth is an Add whose record cannot be saved (the token is put on the gateway before the save and the undo withdraws the entries, not the token). AD1b names it in the specification and its test; **AD1c** closes it, removes any tokens already orphaned and shows none are left, and **lands before any release.**
- **D216 (the owner, 23 November): refresh adds a missing plain line of the render's `deployment.env`; it never changes an existing line's value.** Build id **PL14**, after AD1. The brief and row follow from the owner's three answers (`slices/PL14a.md`).
## RELEASE BLOCKERS (the owner, 23 November 2026; read this section before any release is cut)

- **BLOCKER 1: the port-8080 case of the page service (PL7a2b round 9) and the family it belongs to.** With `pages.enabled: true`, a Small with its own certificate (`network.tls` with a `ca`) whose `public_origin` is `https://<host>:8080` renders a Caddyfile that Caddy refuses to load, so **the front proxy, the deployment's only door, does not start.** **Until PL7f has merged (`slices/PL7f.md`): no release ships; `pages.enabled` is not turned on for the demo or any deployment of the owner's; no guide or release note describes the setting as available** (PL7a2b's own release-note paragraph and guide sentence are reworded by PL7f to say it exists, is off, and is not for use). **No automatic check reads this section today:** `release_green.py` reads GitHub's run and `owed.py` reads the live tests owed; neither reads a list of blockers. **Proposed for the line-fix session: `release_blockers.tsv` beside `resume.tsv`, one line per blocker (id, what, who lifts it), and a `release_blockers.py check` of `owed.py`'s shape that the two release paths (`tools/release_local.py` and `OspreyFlow_Build/scripts/publish_user_repo_update.sh`) call and that refuses while a line stands.** Until it exists the owner reads this section.
- **BLOCKER 2 (already stated, 21 and 23 November): AD1c lands before any release** (the fourth route that leaves an engine's access token, the tokens already orphaned shown none left).
- **The live tests owed** (`owed.py`) refuse a release until each has run: 325 at the last count.

- **PL7e (proposed by the conductor, the owner's ruling of 23 November on PL7a2b case C): the page service's sign-in on the cloud-platform shape.** The chart's egress to the identity provider (`cloud_platform/profile.yaml`: the page service is not in `sign_in`) and the page service's own Entra app registration (`apps/pages/server/config.ts` has only the OIDC names, no Entra path), which ADR-148 Amendment 23 item 1 requires. **Place: after PL7a2b and PL7d, and before the page service is offered on cloud-platform (before any release that offers it; until then PL7a2b's render refuses it in plain words).** A part of its own under the existing build PL7; failing test first; **it names a sign-in rule, so every finding is the owner's.** No row yet.

### New row 26 (24 November 2026, AD5's accepted gap: the owner's standing accept, round 4)

**AD5's fetch double does not model the invite route's email length limit.** `InviteInput` in `OspreyFlow_Core/packages/schemas/admin.py` (about line 94) declares `email` with `max_length=254`; the double in AD5's invite-loads test (`invalid()`, about lines 153 and 154; not on main until AD5 merges) checks only the pattern, so an address of 255 characters or more gets a 201 from the double where the real route answers 422 `string_too_long`. The form's email box has no `maxLength`, so such an invite can be sent. The form code is not wrong (it shows any 422 in words); only the double refuses less than the real route (rule 15). **A fix:** model `string_too_long` for the email in the double and add a case that sends 250 `a` characters plus `@b.co`; or give the email box a `maxLength` of 254 (a form change: the owner's word). Accepted narrower at `a320b8ef07` on the standing line; not security (nothing is offered or given beyond rights).

### New row 27 (24 November 2026, GR2a's accepted gap: the owner's standing accept, round 4)

**`OspreyFlow_Build/tests/glass_trees/test_design_gates_reach.py` now reads `OspreyFlow_Core/apps/pages/tree-govuk` (its new `govuk_core` fixture copies the real tree and four cases assert it is clean before planting), but the installed scan-map row for it (`scan_map.tsv` line 168) still lists only `OspreyFlow_Core/apps/workspace/src/,OspreyFlow_Core/packages/design/`.** A later GOV.UK page slice (GR3a, AD3a, RM1a) that changes only `tree-govuk` would not pick this test in its pre-merge scans and would first see it fail in the merge's full gate. **A fix, the owner's (the installed map is his file): extend row 168's prefixes with `OspreyFlow_Core/apps/pages/tree-govuk/` and run `install.sh`.** The test's own docstring (lines 33 and 34, "it reads `OspreyFlow_Core/packages/design/` only") is to say the same; the builder was told, the verifier accepted the rest. Accepted narrower at `193c9a8d67` on the standing line.

### New row 28 (24 November 2026, PL8a's open fault: the owner's ruling of 24 November, "accept narrower"; the line refused the accept on a word, see below)

**A sash whose `data-max` is below the default (340 for the column, 130 for the timeline) is not held to it: on the attach's first draw with no action by the analyst, `holdToBounds` (`OspreyFlow_Core/packages/glass-shared/src/layout/panelFrameAttach.ts` about lines 213 to 233) calls the writing setter with the page's bound, and `apply` (`panelFrameStore.ts` about lines 349 to 355) compares only against the window's limits (`shownSizes(kept, limits)`), never against the page's `maxPx`, so the bound (320 or 100) is written to `ospreyflow.layout-sizes`.** The spec sentence PL8a added says "only a size the analyst chose is stored"; the React workspace reads the same key, so one load of such a page would make the workspace's column open at 320 from then on. No page mounts the frame yet, so nothing is harmed today. **The owner's ruling: PL8b, the slice that mounts the frame on a page, closes it first, red first, on a real page's markup** (a roomy viewport and empty storage; a sash with `data-max="320"` on the column and `data-max="100"` on the timeline; after the first draw storage stays empty; Home, an analyst's own key press, still stores the bound: the test at about line 1661 of `panelFrameStore.test.ts` stays intact). **Found by the round-8 verifier (record `650c976c41`).** **(Row 29, RL1b's accepted gap, 24 November, round 3 on the standing line: no case in `OspreyFlow_Core/apps/workspace/src/admin/updateNotice.test.ts` (and none in the Python twin `tests/harness/test_update_check.py`) has a `-dev` deployment while a release at or above its number is published, for example `v0.7.0-dev` with `latest: "v0.7.0"` or `"v0.8.0"` and `update_available: true`: the case of a deployment left on an old main after the cut. The code looks right (`updateNotice.ts` checks `buildsFromCheckout` before `update_available`); it is a gap against a case the brief asked for by name. A fix: add the two cases, red against a reordering of the branches.)** **The line's `resume.py PL8a accept` refused the owner's accept: "a finding names a key, a credential or a security rule ('key')": the word matched is `key` in "an analyst's key press" (a keyboard key, not a secret).**

### New rows 30 to 32 (25 November 2026, GR2a's three accepted gaps in a test: round 4 on the standing line, tip `2bcbff28db`)

**Row 30. No test holds ADR-152 invariant I9 for the GOV.UK tree before its identity switch.** GR2a's section 2.0e (and register row P1, and the comment at `tree-govuk/layout.njk` line 4) says the tree draws none of the crown, the GOV.UK logotype and GDS Transport until the switch exists; a crown image or a `govuk-header__logotype` element added to `tree-govuk/layout.njk` or `help.njk` passes every test. A fix: a test over the tree's templates and rendered pages that fails on any of the three, red with one planted. GR3a, AD3a and RM1a add pages to that tree.

**Row 31. The render's `VALUES` table says `config.ts` makes no check on `OSPREY_PAGES_TREE`, which GR2a made false.** The row stays `"OSPREY_PAGES_TREE": None` (the comment at about lines 2662 to 2664: `None` means no check), but `config.ts` now refuses anything but `default` or `govuk`. So `test_each_check_config_ts_makes_on_a_value_the_render_passes_is_real` never runs that refusal through the harness's real start-up check. A fix: give the row its refused value, red against a `config.ts` that accepts it.

**Row 32 (the owner's or the line's: `scan_map.tsv` changes by neither the conductor nor a part). Two existing scan-map rows miss `OspreyFlow_Core/apps/pages/tree-govuk/`, which their tests now read.** `tests/glass_trees/test_design_gates_reach.py` (its row lists only `OspreyFlow_Core/apps/workspace/src/` and `OspreyFlow_Core/packages/design/`) copies the real tree and runs the words, colour and design gates over it. `tests/test_copy_says_no_client.py` walks it through `PAGES_COPY_ROOTS`, and its row lists no `apps/pages` prefix for it. **A part that touches only that tree does not have either selected at Stop unless its own checks name them.** GR3a's, AD3a's and RM1a's checks already name both (checked 25 November, 01:40); the full gate runs both at every merge. A fix: add the prefix to both rows.

### New row 33 (25 November 2026, RL1b's accepted gap in a test: round 3 on the standing line, tip `05b8b474e4`)

**The scan row for `tests/test_version_is_0_7_0.py` lists only `OspreyFlow_Core/,OspreyFlow_Build/`, but the test walks every git-tracked file, root-level paths included.** Its own allow-list names four root-level agent files (the slice builder's, conductor's, scout's and verifier's definitions), and `test_every_allowance_still_matches_something` depends on them. So a change to those files alone (or a new root-level file) does not select the test at Stop. Low risk today: those files change only by the owner's hand, and the full gate runs the test at every merge. A fix (the owner's or the line's: `scan_map.tsv` is the line's once the row is applied): add the root-level prefixes to the row.

### New row 34 (25 November 2026, GR3a's accepted gap in a test: round 7 on the standing line, tip `d9fc405dd8`; GR3b closes it)

**The fixture Conduit sends `as_of` as a datetime (`"2026-11-23T09:00:00Z"`); the real report route's `ReportFigures.as_of` is a `date`, serialised `"2026-11-23"`.** The page draws it as the "Counted on …" sentence (`alertMonitoringWords.ts` `monitoringView`, about line 645) and drops the sentence without a word when it does not parse, so every page test, the field census's `as_of` case included, runs on a shape the real route never sends. The same kind of drift GR3a was stopped for (D225 item 3). **GR3b (the fixture answering from the real route, the owner's (B)) closes it**; until then a fix is the fixture sending a `date`, and a case that the page says "Counted on" for the real shape.

### New row 35 (25 November 2026, AD3a's accepted gap in a test: round 6 on the standing line, tip `907d548bdc`; for the people page's write slice, and GR3b)

**The fixture Conduit refuses a `POST /v1/admin/people` body in a different order and shape from the real route.** (1) It checks the bearer and the right (`fakeConduit.ts` about lines 162 and 163) before it parses the body (about line 168); the real route parses a JSON-typed body first, so a malformed `application/json` body gets 422 `json_invalid` even with no bearer or right, where the fixture answers 401 or 403. (2) It reads any body as JSON whatever the `Content-Type`; the real route reads only `application/json` as JSON, so the fixture's own case (`admin-people.test.ts` about lines 823 to 827: `"{}"` sent as `text/plain`) expects three "missing" errors where FastAPI gives one type error at `["body"]`. The page never posts today, so no behaviour depends on it; the write slice must start from a fixture that refuses as the real route does (rule 15), which GR3b's goldens give.

### New row 36 (25 November 2026, GR3a's accepted gap in a test: on the standing line, tip `63c2d5689c`; it names an access rule, so the owner was told)

**ADR-152 invariant I15 names `test_the_dashboard_page_answers_a_reader_without_read_reports_as_a_missing_report` (the owner's approved correction `ADR152_I15_ROW`), and no file has a test by that name.** The behaviour is right and tested under another name; GR3a's round-6 and round-7 tables asked for the exact name, but the line's `round_table` fault gave those rounds round 5's table, so the builder never saw the request. Nothing checks that an invariant's named test exists (rule 12): the scenario file checks only I15's first name (`test_govuk_alert_monitoring_scenario.py` about lines 653 to 656). **A fix:** rename (or add) the test under I15's exact name, red against a page that answers 403 or names the right; and a check that every test ADR-152's invariant table names exists in the tree.

### New row 37 (25 November 2026, RM1a's accepted gap in a test: on the standing line, tip `f35dd00b69`)

**Scenario AQ1's "in the order sent" is exercised by nothing that would catch a re-sort.** Every order RM1a's tests send is already newest first, so a page that sorts the rows again by time passes every vitest case; the Python source grep does not list `.toSorted(`. Done when a case sends rows **not** in time order and asserts they are drawn exactly as sent, red with a planted newest-first sort (and with `.toSorted(`).

### New row 38 (25 November 2026, RM1a's accepted gap in a test: on the standing line, tip `f35dd00b69`)

**The fixture Conduit never sends `created_at` in the real route's form (rule 15).** The page's reader turns one time it cannot parse into "could not be read" (502) for the whole queue, so a break in parsing the real form would make every real queue unreadable with every test green. Done when the fixture's `created_at` is the exact form the real alert-queue route serialises (read from its model, not hand-written), and a case shows the page parses it.

### New row 39 (26 November 2026, the owner's batch: "who made it")

**Who made a case, a board or a saved view is left out of the GOV.UK pages for 0.7.0** (GR1a question 2, GG4a question 2, GR1d question 4). Names come later through `display_names`, never a raw subject. This is a later part of its own.

### New row 40 (26 November 2026, the owner's batch: GG2a question 3)

**A CI expansion gate for the page service's graph module.** For 0.7.0 the expansion figure is judged by the owner's Mac alone (800 ms). A CI gate for it, calibrated for CI's software WebGL and shown red first, is a later part.

### New row 41 (26 November 2026, the owner's batch: GG4c question 5)

**Unsharing a board.** GG4c ships sharing with no unshare route; a route and its form, each with its access-control test (rule 4), are a later part.

### New row 42 (26 November 2026, the owner's batch: the live step)

**The live step's stack gains ClickHouse and Azurite (and Keycloak if a group needs it)**, a small part. Line-fix then makes the live step pay group by group, after hand-back 61.

### New row 43 (26 November 2026, GR4a's accepted gap in a test: on the standing line, tip `c33f6d1802`)

**spec/08's scenario TS still names the board page under `reports-figures`** (about line 863, and row TS14 at about line 880), while `FUNCTIONS.yaml` and the tests give it `reports-trends-shown-together`. The scenario test reads only fixed phrases and cited source words, so it cannot see the drift. The spec change is the owner's (proposed in the 12:45 report); after it, a test that reads the TS rows' function ids from spec/08 closes the gap.

### New row 44 (26 November 2026, GR4a's accepted gap in a test: on the standing line, tip `c33f6d1802`)

**No plant shows the page refusing a withheld trend's title or figures** (`pack-trends.test.ts`, the plants about lines 721 to 726: the withheld sentence's count, an empty chart, an empty table, the order). A plant that draws the withheld trend's title and asserts it is caught is owed (rule 15; rule 7's withheld item at its real shape).

### New row 45 (26 November 2026, the owner's ruling at about 13:40 UTC): C040 raised to a security row, **before RL2**

**Security (rule 3 and rule 4): a drawn item re-marked by any path other than the edit route leaves its waiting promotion at the older marking.** The placed backlog's row C040 (`process/lanes/v062/backlog/OPEN_BACKLOG_PLACED_2026-11-19.tsv:13`, open, "in build", Security; DOC1A's report, line 40, lists it among the open rows that let a person see something). A promotion's `items_marking` (the highest marking of the drawn items it carries) decides who may review it: `promotion_ageing.py` about lines 170 to 184 lists a waiting promotion, and sends its alert, only to a reviewer `cleared_to` both its `dataset_marking` and its `items_marking`. That marking is raised only by `promotion_store.raise_marking` (`promotion_store.py` about lines 237 and 574), which is called on the author's own edit alone: `edit_drawn_item` (`services/api/app.py` about lines 5196 to 5219, when the edit's body carries a marking). `Promotions.item_marked` (`promotions.py` about lines 706 to 710) wraps the same call and has no caller on main. **"Re-marks outside the edit route"** means any other way a drawn item's marking rises (the case's marking tool, a migration, a re-marking script, an import or restore of a board): the promotion keeps the lower marking, so a reviewer cleared only to it is shown, and may review, items now marked above them. GG4b's away round (`away/GG4b`, its report, question C) met the same gap from the document's side and found no sweep in the code or the spec. **Owed before RL2:** every path that changes a drawn item's marking raises its waiting promotion's `items_marking` in the same change (or the review list reads the items' markings at read time), with an access-control test per path, each shown red at its real call site (rule 15). A security part: never accepted narrower.
