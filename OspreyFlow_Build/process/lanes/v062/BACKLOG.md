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

### New row (19 Nov, from SE3's first verifier): the draft's PUT route confirms no version until the Glass sends one

SE3 makes the model draft's creator check mandatory on every write (save, replace, discard) and confirms the version where
a version is passed (replace and discard, by the store; the import path passes the one it planned). The PUT draft route's body
carries no version, so that route confirms none: adding one means a schema change (the draft input type, which regenerates
the TypeScript types) and a Glass change, neither in SE3. ADR-152 decision 11, X5, says "save, replace and delete check the
draft's creator and an expected version", so this half of X5 is **owed**: the Glass sends the version it opened, the PUT route
requires it, and a stale save is refused in words. Owed with the Studio's Model step (IS2), which waits for SE3. Not yet
assigned.
