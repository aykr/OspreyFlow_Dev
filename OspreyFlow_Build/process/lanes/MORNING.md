# Morning, 7 November 2026

Written by the orchestrator at 00:05 and updated at 07:05. Nothing has been pushed. Local `main` holds two merges: studio's L1.1 (`32c0f36`) and glass's L2.1 (`6e178b2`). Their friction rows are assembled.

**State at 04:55 UTC, 8 November (the orchestrator's usage limit reached).** Glass is paused at its own usage limit, with L2.8b's last fix round not started (tree clean at 04e98f8, no lease held; the work left is listed in its last message: D1–D3, D6, D7, text, one leased run). Studio is starting Part B (L1.2b); ADR-140 Amendment 10 is reserved for it. Case is fixing L3.1b's review findings (blocker: drawn datasets copied by branches and alert jumps). Main is pushed and green.

**Paused (your instruction, about 06:35 UTC, 8 November):** every lane stops at the end of its current step: glass after L2.8b, studio after L1.2b (Part B), case after L3.1b. All three steps are merged on `main` and all three lanes are stopped: case's L3.1b (`d198174`), studio's L1.2b (`1fb38ba`, Phase 6's exit met, ADR-140 Amendment 10) and glass's L2.8b (`2671fe3`, ADR-109 Amendment 10, the new `make confinement-check`). Each was kept on local make ci (`make -k` where Docker Hub's 429 refused the image scans) and make test, whose only failures were this machine's own. No new step is briefed until your new instructions. Then `main` was pushed to `origin` once (see `PUSH_LOG.md`), and GitHub's CI on it is watched and recorded below, **not fixed**, as you asked, to be folded into the restart.

**GitHub's CI on the push (`e89d44a`, run 42461907095, 08:12–about 08:30 UTC): failed. Recorded, not fixed, as you asked.** 28 jobs passed (all seven trivy image scans included) and the same five failed as on the previous push's run (`05d2d84`, run 42448543395), so this push adds no new failing job. There are two causes:
1. **The runner's Python is 3.14, not 3.12**, and altair (`altair/vegalite/v5/schema/_config.py:6491`, `class StepKwds(TypedDict, closed=True, …)`) fails at import under it: `TypeError: _TypedDictMeta.__new__() got an unexpected keyword argument 'closed'`. Every module that imports it fails at collection: `test` (150 collection errors, no test run), `conformance` (110), `conformance-model` (1, `test_phase6_extraction_and_resolution.py`) and `route-coverage-check`. Locally the venv is 3.12, so make ci and make test never see this. Likely fixes: pin the CI's Python to 3.12 (`setup-python`/uv) or move altair to a release that supports 3.14.
2. **`glass-perf-a11y-keyboard`: 2 failed**, `a11y/every-harness.spec.ts:163` on `case-screen-options-harness.html` variant c, dark and light: axe's `target-size` (WCAG 2.2 AA, serious) on the ghost button "Add many from a list". It's the case lane's screen.
The full failed-job log is in the orchestrator's scratch (`ci/gh_e89d44a.log`), not committed.

**Pushing (your instruction, about 06:20 UTC):** CI runs locally on every merge, and `main` goes to `origin` in one push at the very end, not after each merge.


## Decided on my recommendation while you were away (from 10 November, about 05:40 UTC)

Your word, 10 November: "going forward can you go ahead with the recommended option, for all the options that are
decided this way, draw up a summary for me, when i come back online". Each entry: the question, what I chose and why,
where it is recorded, and how to overrule it. Overrule any of them and I'll reverse it.

1. **ADR-148 question 2: where the settings and key files live** (model settings, map settings, the write-only
   keys) on the cloud-platform profile. **Chose (a):** in Postgres (RDS), the keys encrypted with a KMS key the
   namespace holds, each replica told of a change through Redis. **Why:** it needs nothing the Cloud Platform team
   may refuse; (b), Kubernetes Secrets the Conduit writes, needs a Role to write Secrets in its own namespace.
   **Recorded:** ADR-148's open question 2, closed in the decision log; P8 builds it. **To overrule:** say (b).
2. **ADR-148 question 3: Java in the Conduit on the cloud-platform profile.** **Chose (a):** this profile builds
   the Conduit without Java, and the basemap is built off-platform with `ospreyflow map build` and uploaded.
   **Why:** a smaller image with fewer scan findings, and the profile needs no in-product build. **Recorded:**
   ADR-148's open question 3, closed; P7 builds it. **To overrule:** say "one image everywhere".
3. **How L3.9 applies your type-mapping ruling** (case's proposal, my agreement). The Studio's Map step maps each
   drawn type to any type of the target's domain model, defaulting to the same name. Items whose type is unchanged
   move into the target as the same element, as L3.4's promotions do. Items mapped to another type are written by the
   load as new elements of that type, keeping their marking, grading and drawn provenance, each with an inferred,
   scored SAME_AS back to its original. Nothing is collapsed (rules 5 and 6). One load and one revert, which also
   withdraws the copies, their links and their SAME_AS. A picture, or a Same/Not-the-same decision, on a retyped item
   is left out with its reason. **Why:** an element cannot change its class, and keeping unchanged items as the same
   element keeps L3.4's revert. **Recorded:** ADR-143 Amendment 7 (case writes it). **To overrule:** say which part.
4. **The work split into two tracks, and P6 moved to platform-b** (your request, 10 November: group the work for a
   demo-ready version and carve out the client's install). Track A (demo-ready) and Track B (ADR-148's
   client steps) are in the build plan's new "Two tracks" section. **Chose:** to move P6, the gazetteer panel, from
   after P9 (your client record's order) to platform-b after P5b. **Why:** the demo needs P6, and otherwise it would
   wait two days on the client chain. **To overrule:** say "P6 after P9".
5. **The demo deployment for screenshots** (D2b needs one, and Docker is off on this Mac). **Chose:** a separate named
   deployment built from `main` on your test server, never touching `osprey-small`. **To overrule:** say where
   instead.
6. **Merging in batches where steps don't overlap** (your question about parallelism). **Chose:** studio's L1.5,
   platform's P5 and docs' D2a merge together into one merge result, gated once, right after admin's L2.7, instead
   of one after another (about 1½ hours saved). A failing batch is split to find the cause. Steps that touch the same
   files still merge one at a time. **To overrule:** say "one at a time".
7. **Your request, 10 November: at demo-ready, refresh your deployment and publish a new version.** Planned for
   when Track A is merged (about 21:00 today; the decks, D2b, aren't part of the product repo, so it doesn't wait for
   them):
   1. `make ci` and `make test` green on `main`, the merge gates as usual.
   2. Your local deployment: `ospreyflow backup` (data and Enron, kept out of `~/Documents`), then Docker Desktop
      started and `ospreyflow start --build --name default`, restoring from the backup if needed (your word of
      8 November). Docker stays on afterwards for your demo; the lanes' stacks stay on the server.
   3. The product repo: `OspreyFlow_Build/scripts/publish_user_repo_update.sh` (its checks refuse real names, local
      paths, `osprey.yaml`, `data/` and the real-data list), then `git push origin main` in `OspreyFlow_user_repo`.
   The new README stays a draft until you approve it, so the published README is today's. (The review found the
   draft sat under `OspreyFlow_Core`, which the publish copies whole; docs is moving it to
   `OspreyFlow_Build/process/lanes/docs/README_DRAFT.md`, and I check the published tree for it before pushing.)
   **To overrule:** say what to change.
8. **Disable moves a private view to someone who may not be cleared for its count (admin's L2.5b review).** A view
   sends its node count unfiltered (`case_views.py`'s `chosen`), so a private view transferred at Disable would show
   its new owner how many nodes the creator chose, some perhaps above their clearance (rule 3). Options: (a) hold the
   recipient of a view or board to the case's ceiling (they must clear the case's highest marking), now, in admin;
   (b) count `chosen` per reader, in case's code, which also fixes the same count on every shared view. **Chosen:
   both, strict first** — (a) in L2.5b now, so nothing leaks today, and (b) carried to case, after which (a) can be
   relaxed by a later amendment. Recorded as ADR-145 Amendment 9 (reserved). **To overrule:** say "views at the
   case's unit alone", as Amendment 8 reads, accepting the count until case's fix lands.
9. **The install checks the backups folder before writing anything (P5b's review).** The install did not run the
   doctor's backups checks, so a folder inside the checkout (where every backup would later be refused) or a synced one
   was accepted silently. **Chosen:** the install runs them: the checkout refused, a synced folder warned. **To
   overrule:** say "doctor only".
10. **A throwaway named deployment on the test server for P5b's update path.** A named deployment's `ospreyflow
   update` now really backs up and, on failure, rolls back with `down -v` and a restore; only a fake had seen it.
   **Chosen:** one throwaway deployment, `p5b-test`, synthetic data, on ospreyflow-test, torn down after, never near
   `osprey-small`. **To overrule:** say "fake only", and it is recorded as an open risk instead.
11. **Gazetteer identifiers in a case's own data (CARRIES row 23, raised by studio).** A gazetteer loaded through the
   Studio arrives as a plain file, so nothing marks it as a gazetteer and its osm_id and similar identifiers show in
   node reads. Options: (a) withhold the gazetteer-only identifiers from every node for every reader, and match a
   Location on its name alone, uprn kept on a case's own Location; (b) let the Studio mark a source as a gazetteer and
   stamp its places (a new field); (c) leave it. **Chosen: (a), the strict reading**, as ADR-147 Amendment 3 (reserved,
   platform-b, after P6; it touches shared and case files, so it goes as one reviewed step). Cost: an analyst's own
   data loses those six identifiers in reads. **To overrule:** say "(b)" or "(c)".
    *As built (platform-b, decision 4):* a Studio load still matches on its own match key (OS Open Names'
    `os_place_id`), as the reader's scoped principal, or a re-load would duplicate every place; the Test's preview of
    a would-create node is the uploader's own file; an existing node the Test returns loses the six like any read
    (a carry to studio).
12. **BPMN and DMN: stored, or produced on demand? (rules-b's L2.11a.)** ADR-146 says each rule "is saved as" BPMN
   2.0 and DMN; the codec as built produces them on demand from the rule's sentence. Options: (a) the editor's save
   writes both files beside the rule at every version, and Export returns the stored files; (b) an amendment saying a
   lossless serialisation meets the decision. **Chosen: (a)**, the decision as accepted (no ADR is amended away);
   rules builds the save in L2.11, rules-b records the shapes as ADR-146 Amendment 5. **To overrule:** say "(b)".
13. **The rule editor's rules (rules' L2.11, six decisions; ADR-146 Amendment 6).** (1) *Make live*'s second person
   follows the dataset's existing promotion policy: where it asks for review, another holder of `deploy_rules` at
   Author level approves, never the author; a composite asks if any member does (the alternative, a separate setting,
   would be a new Admin control). (2) *Test* runs over 30 days on the stored draft, its result kept on that version,
   and *Make live* is refused unless the version going live is the one tested. (3) At most one draft and one live
   version; *Save* needs `author_rules`, *Make live* `deploy_rules`. (4) A rule's dataset is one the case reads; a
   change naming another is refused. (5) *When* gains "a screening list refreshes"; a new rule cannot take the
   whole-deployment scope. (6) The migration puts each rule in its dataset's home case, reports any dataset without
   one, dry run first. **To overrule:** name the number.
14. **Faster test runs (your word, T1): one product change I allowed.** T1's brief said "no product code", but the
   biggest cost was the graph adapter applying the schema one statement per round trip (about 30 s per live test). I
   ratified changing `graph_arcadedb/schema.py` and `client.py` so the schema goes as one script, for the Conduit's
   start-up as well as the tests (one code path, rule 15). No restore on a refusal: main's own partial-apply
   semantics, completed by the next idempotent apply (a restore could drop another replica's type). Measured: a fresh
   schema 15.8 s to 0.2 s; the whole graph conformance suite passes. **To overrule:** say "tests only".
15. **For your information: `osprey-small` on the test server is safe from the lanes' builds** (platform-b checked,
   read-only). Every image it runs is pinned by digest, so no lane's build can change what it starts. Two things to
   know: (a) its own images are kept only because its containers use them, so no `docker image prune` on that
   server, and do not remove those containers, or the next `up` must pull from ghcr.io; (b) its ingest image
   (`ghcr.io/aykr/ingest@sha256:52f8c292…`, the batch profile) is not on the server at all, so an ingest job there
   would pull it from ghcr.io and needs registry access. Nothing to decide unless you plan an ingest on it.
16. **No new demo-track steps before tonight's release (your word, 10 November afternoon).** What a review or
   test finds goes to CARRIES for tomorrow, unless it is a real access-control (rule 3) problem or blocks the demo.
   T1's merged parts are folded into its one step on the dashboard.
17. **Two rule-editor decisions from L2.11's independent review (rules; ADR-146 Amendment 6).** (a) A pattern
   rule or an AML/KYC template added through *What raises alerts* now runs "just for me" (its author's own alerts),
   never into the case's queue untested; a case-wide rule is written in the rule editor, with Test and Make live
   (ADR-146 decision 3). A template-to-draft path with its own Test is tomorrow's carry. The demo's templates still
   work for whoever adds them. (b) A rule runs as its author, who must hold `author_rules` or `deploy_rules` (the
   right to have written it), on every run path; its reach stays its declared dataset alone. Before, a Rule author's
   live rule ran at a load but never on a schedule. **To overrule:** say "(a) case-wide at once" or "(b) …".
18. **Run counts across units (studio's L1.7 review).** A dataset's "runs today" counted every unit's runs into
   it, and the number reached unit-scoped readers: the quota bar, a refusal's words (to the external service too),
   the budget alert. **Chosen, on the strict reading:** only a holder of `administer_system` sees the number;
   everyone else is told the quota is used, without a count. Recorded in ADR-141 Amendment 1. **To overrule:** say
   "show the count".
19. **Your laptop's rebuild moves to after the whole build; heavy runs move to the server (your word, 10 November
   evening).** Item 7's step 2 (your local deployment) waits until both tracks are finished; the product repo is still
   published from `main` at demo-ready, tonight. Lanes run `make -k ci` and `make test` on the test server (Docker and
   trivy there, so the image scans really run); browser tests can run there too now (Chromium and its 12 system
   packages installed with your approval; `osprey-small` untouched), one lane at a time until per-lane ports land
   (T2). Lanes never open desktop apps on this Mac (a deck agent tried Keynote this evening).
20. **The fix-and-check stage shortened (your word, 10 November evening).** (1) My independent review starts when a
   lane's code is built, in parallel with its own reviewer, so both reviews' fixes go in before one round of gates;
   (2) a self-check list of today's recurring findings in every lane's prompt; (3) a lane rebases onto main just
   before its gates, never after; (4) `make test` in parallel on the server (admin's T1, tomorrow). Aim: a step's
   fix-and-check from 3–5 hours to 1–2.
21. **About 30% of the lane work on the Sol account from 20:50 (your word, 10 November).** Platform already runs on
   sol; case and studio-b switch at 20:50, each at a safe point (pause-done, then resumed on sol), so 3 of the 9
   running sessions are on sol. The demo track (rules, studio, docs) stays on ayan through tonight's release.

## Restart, 8 November afternoon: O-six (six lanes), on your records of today

**Your rulings:** six lanes; rules, case, studio and platform on the `sol` account, the orchestrator, admin
and docs on this one; model engines, each job's model and their keys managed in the Glass's Admin place
(keys write-only, the CLI kept for headless and recovery), map keys the same; docs waits until rules'
L2.9 and L2.10, admin's L2.5 and platform's P1 and P3 run deployed in both themes, and gains the README,
an architecture guide, the welcome pages, the website and the GOV.UK wording. Recorded as ADR-142
Amendment 3 (written), with ADR-135 Amendment 2 and ADR-147 reserved for the platform lane.

**Done:** reservations (`46b73c4`); the lane scripts for six lanes and two test stacks, each new test red
first (`208ee66`, `process/lanes/O6_RED_RECORD.md`); stack b's containers created and checked live under
its lease; the build plan, runbook, progress table and the five first briefs (admin L2.4 part 2, rules
L2.8c, case L3.2, studio L1.3, platform P1); worktrees `admin`, `rules` and `platform` set up. The
studio, case and glass sessions are retired (each replied "retired"); their worktrees are clean and merged.

**Your rulings, 9 November about 05:10 UTC (the eight questions below and item 68; all answered):**
1. Java: **(A)**, a Classpath-exception entry in the licence register, the runtime in the Conduit image (platform, P5,
   ADR-147 Amendment 2).
2. Screening lists: **(a)**, L1.6's reference lists are the store of record, ADR-133's Lists tab read-only then
   retired (studio-b, ADR-133 Amendment 9; rules moves its picker and re-screening, the carry already in CARRIES).
3. Alert timing: **(a)**, the 250 ms residual accepted; nothing to build.
4. Promotion revert: **(a)**, the operator command only, as built (case, L3.4).
5. Proposal text: **(b)**, as built, only to an accepter cleared for the case's marking (ADR-143 Amendment 4's open
   question closed).
6. Gazetteer beside a case: **(c)**, not my recommendation: gazetteer places are copied into each case's dataset at
   load (platform, P5, ADR-147 Amendment 2). The copies keep 3b: their source identifiers withheld from every request
   reader and never matched.
7. Private networks: **(a)**, an operator's allow-list in `osprey.yaml` (studio-b, ADR-140 Amendment 15).
8. Gazetteer unit (item 68): a build setting (platform, P5).

Also, 9 November about 04:55 UTC: every lane session except platform's had exited about two hours earlier (cause
unknown; worktrees intact). All seven were resumed in fresh sessions from their HANDOFF and state. rules-b's orphaned
vite on 5184 was left running (stopping it was refused to me); admin's stack-c lease passes to its resumed session.
It happened again at about 05:40 UTC, platform's session included: Terminal.app itself had quit, with swap at 23 of
24 GB (Docker's VM alone 11.4 GB), so memory pressure is the likely cause. All eight were reopened (platform fresh
on P5). Three orphaned live pytest runs were left to finish; their leases pass to the resumed holders. **Corrected:** I told you
`osprey-probe-arcadedb-new` was not a lane's; it was stack a's ArcadeDB under its old name (`lane_stacks.tsv`), and
removing it took stack a down. Platform, holding a's lease, recreated it at 05:42 (127.0.0.1:2491, arcadedb
26.10.1, empty databases). The lesson: I check `lane_stacks.tsv` before calling any container unused. The sisters (studio-b, case-b, rules-b) stay on `sol`: about 30% of the steps left.

**A new question for you (studio-b's L1.8; access, so yours):** ADR-145 Amendment 4 decision 12 says a disabled
action says who can, with people's names ("You need Review promotions; D. Engineer and S. Lead have it"). No
route today tells anyone but an administrator who holds a right.
- (a) Studio-b's recommendation: a route listing, by display name only, the holders of a right among the people
  who hold a level in the dataset's home case, for a reader who can read that case.
- **Your ruling, 9 November about 09:50 UTC: (c).** Name the roles that hold the right ("the Data engineer and Studio
  lead roles have it; ask an administrator"), never people.
- (b) Name no one at all.

**A question for you (platform's P3; the licence register, so yours):** building the local basemap needs Java 21
(planetiler). The only runtime here is Eclipse Temurin, GPL-2.0 with the Classpath exception, and spec/00 §7 says
"GPL and AGPL never pass".
- **(A) Platform's recommendation:** add a Classpath-exception entry to the licence register for a Java runtime
  in the Conduit image (about 100 MB, jlinked, pinned by digest). The exception keeps our code outside the GPL,
  as it does for every program on a JVM.
- (B) Keep Java out of every image we ship: `ospreyflow map build` runs planetiler in its own container on the
  host, pulled by you, never shipped; the Glass's Build button names that command.
- (C) No build in the product: building stays a documented manual step on a machine with Java.
Built meanwhile: Java is out of the image and *Admin › Maps*' Build says so in words; the rest of P3 goes on.

**Two more questions for you:**
1. *(studio-b's L1.6; it would retire part of an accepted ADR)* Two deployment-wide screening-list stores now
   exist: ADR-133's (the Lists tab, which KYC rules screen against) and L1.6's (Studio › Sources, versioned as
   reference lists, per ADR-140 Amendment 9). Which is the store of record?
   - **(a) Recommended:** L1.6's; the rules lane moves its list picker and re-screening to it, and ADR-133's
     Lists tab becomes read-only, then retired.
   - (b) Both: a Studio import also writes ADR-133's store, so the rules keep working unchanged.
   - (c) ADR-133's: the Studio connector becomes a front end to it.
   Built meanwhile: (a)'s store, with ADR-133's store and Lists tab left fully working.
2. *(rules' L2.9; access, so yours)* An alert's address refuses every unreadable or missing alert after the
   same 250 ms, so its timing tells nothing, except for an alert whose evidence takes longer than 250 ms to
   read. **(a)** accept that residual (rules' recommendation); **(b)** cap the evidence an alert may cite;
   **(c)** a larger wait. Merged meanwhile with the 250 ms wait.

**One more question for you (case's L3.4; ADR-143's open question 2, named for you):** can a promotion be
reverted online?
- **(a) Case's recommendation:** an operator command only, for now (`python -m scripts.revert_promotion <load_id>
  [--dry-run]`, the Conduit stopped as ADR-127 Amendment 9 says); the board shows the command to a data engineer
  and tells an analyst to ask one.
- (b) An online revert route for promotion loads only, for the proposer or a data engineer, refused once anything
  else rests on the promoted items.
- (c) Online, data engineers only.
Built meanwhile: the revert core and the offline command; any online route is a thin wrapper over it.

**And one more (case-b's L3.5; access, so yours):** the Studio's Model tab shows a proposed link type's text (its
label, meaning, proposer and reason, written inside a case) to the dataset's data engineers who accept types,
who may hold no level on that case. Should the case's marking limit that?
- (a) Case-b's recommendation: no; the text is about the model, not the case's data, and the data engineer must
  read it to decide.
- **(b) Built meanwhile, the strict default:** the text shows only to an accepter cleared for the case's marking;
  others see that a proposal exists above their clearance, without its words.

**And one more (platform's P4; amending ADR-099, so yours):** place search reads the gazetteer as a dataset. But a
case reads exactly one dataset (ADR-099 Amendment 12), so adding the gazetteer means a composite of the case's
dataset and the gazetteer, and a composite case is read-only for loads (Amendment 15): place search would cost a
working case its loads.
- **(a) Recommended:** treat a gazetteer as reference data a case reads beside its own dataset, through the same
  access step (handling kept), without making the case a composite (an ADR-099 amendment).
- (b) Leave it: place search only in cases that read a composite including the gazetteer.
- (c) Copy gazetteer places into each case's dataset at load.
Built meanwhile: (b), the gazetteer as a dataset, nothing read across the dataset boundary.

**And one more (studio-b's L1.6; it would admit private addresses, so yours):** the Studio's SQL and API connectors
refuse every loopback, private, link-local and inside address, so a client's database on a private network can't
be reached. Should an operator be able to admit one?
- **(a) Recommended:** yes, an allow-list in `osprey.yaml` (installer-level, not Admin), each entry a named host or
  network the operator admits, everything else still refused.
- (b) No: connectors reach only public addresses.
Built meanwhile: (b).

**Needs you before any lane opens:**
1. Close the three retired windows (studio, case, glass).
2. Write `~/.ospreyflow/accounts.conf` (yours alone; the tooling never writes it):
   ```
   account ayan = ~/.claude-ayan
   account sol  = ~/.claude-sol
   orchestrator = ayan
   lane studio   = sol
   lane case     = sol
   lane rules    = sol
   lane platform = sol
   ```
   `~/.claude-sol` must be signed in (`CLAUDE_CONFIG_DIR=~/.claude-sol claude`, then `/login`). Then say
   go, and I open the five lanes with `lanes_launch.sh open <lane>`, checking first that a sol session's
   messages reach me.
3. **GitHub's CI on Python 3.14** (above): `ci.yml` is yours. I recommend pinning the jobs' Python to 3.12
   (the version the project builds with), as a diff for you to apply, or with your word I apply it.

## For your review tomorrow: decisions I took on my recommendation

You asked at 23:45 for the build to run on its own, with design conflicts settled on my recommendation and
listed here. Each line says what was decided and where it is recorded; overrule any of them and I'll reverse it.
New ones are added at the bottom as they happen.

1. **A case opened from an alert keeps an empty layer of its own** (your no-branches ruling names branches only). Recorded in ADR-143 Amendment 1 on case's branch.
2. **Existing case copies keep an empty layer each** until L3.2: a branch can't be told from an alert jump, and linking them to the original case's layer would leak. L3.2's migration moves anything in those layers into the original case's layer.
3. **The rule audit's old entries lose their words** when they name an alert (L2.8b), because nothing can check them.
4. **L2.8, a jump to an alert whose evidence isn't whole is refused as a missing alert** (ADR-124 Amendment 17, reserved for glass).
5. **L2.8, confirming a link repoints every open alert citing its old revision** in the same close (ADR-109 Amendment 9, reserved for glass).
6. **A swept alert whose cited link can't be read is raised without its node**, rather than stopping the sweep.
7. **QA: a Studio load writes into the pipeline's own dataset, refused unless that dataset is the case's loading dataset** (Part C, after L3.1; open limit in ADR-110 Amendment 15 until then). This follows your earlier ruling that only a case loading into a dataset sees its pipelines.
8. **The port guard now reaches every Python process a test starts, and turns uvloop off** (`b232abf`), after the fourth rule 14 breach of the day.
9. **L3.1 not merged at its final review (00:05):** two blockers. First, a monitor in a case could stamp an alert naming a subject from the case's own layer into the shared source (a rule 3 leak). Second, the migration fails outright once any branch reads its original's layer. My rulings: an alert any of whose referents or links is in the layer is written into the layer, and the migration counts and names a branch as reading its original's layer. Case is fixing both, with tests red first, before merge; your conditional approval still applies to the fixed branch.
10. **A branch member with no level on the original case does not read the original's layer** (the same reasoning as the alert-jump exception). ADR-144 Amendment 1 decision 2 didn't address members who exist only in the branch.
11. **An alert in a branch that rests on the original case's layer has its node withheld and its queue row raised** (case's call within my ruling): it can go neither to the source (a leak) nor into the read-only layer.
12. **ADR-110 Amendment 17** carries studio's Part A2 findings, because Amendment 15 had been rewritten in place on a branch. It was restored, since decisions are amended, never edited.
13. **L1.2c (your option A): reverting the returning row's load puts its link back exactly as it was before the merge.** The load record keeps the link's prior state for its own-key merges only, never shown anywhere, and restored at its own marking. A revert is refused, in words, if the link has been written since. The other two options were a counted unmerge, which would leave the reverted load's values on the link, or marking the link reverted, which would leave a gap in its history.
15. **L2.8b, alert transactions are read in the reader's own case**, not the alert's: the alert's own case was a filter without an access check. A rule-evaluation entry's findings count is withheld from a reader who can't see every finding. The other link-replacing paths move to a new L2.8c.
16. **The new right to edit a dataset's domain model, `edit_target_model`, is held by the data engineer** (ADR-112 Amendment 6, reserved for case). ADR-140 decision 4 names the right but no holder, and the developer holds the other Studio rights.
17. **An existing dataset's first domain model is the union of the packs its cases chose** (FIBO, NIEM, STIX), seeded as a live version 1 by a one-off script with a dry run first (ADR-126 Amendment 3, reserved for case). A dataset whose cases chose none gets bare POLE. Without this, deriving packs from the model would strip every existing case of its packs, losing its KYC figures for example.
18. **L2.8b's repoint journal follows the graph's own record of what replaced what**, instead of a table of its own. The table could record a write that never committed. Because L2.8b is already past its two review rounds, anything new found from here goes to L2.8c rather than L2.8b.
19. **L1.2d: an id that two link types share is refused, not guessed.** A route answers 409 in words. A background job (resolution, extraction) skips that one link, records the skip where a person sees it, and carries on with the rest.
    - **Superseded at 03:55:** item 19 is replaced. A shared-id refusal would itself tell the reader that another link exists, which they may not be cleared to see. So every link write now names the type its caller already knows, and there is nothing to refuse.
20. **Each dataset gets a highest-marking field now (L3.1b), set when it's made.** For a drawn dataset it can't be above its maker's own clearance; every other dataset defaults to the deployment's highest marking, so nothing changes for them. Enforcing it on writes stays with L3.3, and Admin › Datasets will show it.
21. **A pipeline's pinned model version is a record only for now (studio, for L3.1b).** A Test runs against the live model by default. Someone who may edit the model can name the open draft instead; anyone else is answered as if the draft didn't exist. Deploying still needs a Test against the live model. A dataset with no model leaves the pin empty.
14. **L3.1b's four questions, settled on my recommendation:**
    - **Home case Author:** an existing dataset's home case gets its creator as Author. If that's a service account or a person no longer active, it gets none and is listed as "needs an owner".
    - **Composites:** a composite gets a home case; an analyst layer never does.
    - **The old `investigations.domains` column** is kept as a record, not dropped.
    - **Environments:** one home case per dataset per deployment until releases bring a second environment.

### O-six (8 November, afternoon)

22. **The second stack's ports are 2492, 55434, 6380 and 9002, bound to 127.0.0.1 only** (stack a's
    ArcadeDB listens on every interface; b's had no need to). Its containers copy stack a's images and
    settings, and its Postgres was given an empty `ospreyflow` database, as stack a has. ClickHouse's
    18123 stays stack a's alone, because `test_statelessness_clickhouse.py` starts it itself. Stack b's
    object store did not answer in the smoke test: unproven until a lane's first live run uses it.
23. **File ownership after the split:** rules owns the shell, Home, the status bar, the theme and the brand
    (L2.9 reworks the places and the GOV.UK header); admin owns Admin except Models and Maps; platform owns
    those two sections and the map, geocoder and model modules; docs owns `welcome/**` and the README.
    L2.7's Home section is built by agreement with rules.
24. **The steps keep their numbers** (L2.4 part 2 to L2.12) under their new lanes, so the records still
    read; the glass lane's done rows stay in the progress table.
25. **Platform's steps are P1 to P4,** P1 (models in Admin) first, then P2 (usage and limits, which
    `spec/00` and `spec/04` promise and nothing builds), P3 (maps in Admin, after P1, so map keys follow
    P1's rule) and P4 (the analyst's basemap switch and place search). P1 asks you, through me, where a
    key written from the Glass is stored and whether a key change needs a second person.
26. **The CI failure on `case-screen-options-harness.html`** (axe's target-size) is carried into case's
    L3.2 brief.
27. **Fresh sessions, not repurposed ones,** as you agreed: each brief tells the new session which
    report to read first.

28. **Rules' L2.8c questions, settled on the recommendations** (rules' and mine): a cloned link's original
    is marked `superseded_by` its clone, and `supersede_node` reports each pair to its caller before commit,
    so every supersede reaches the repoint journal (rules found the originals were only marked `reverted`,
    so the settle could not follow them); "publishing's removals" is Amendment 10 point 6's second gap
    (a removal pushed to open canvases at once, a small working-set change ratified at merge); and D8 is
    measured under a named lease and stack and recorded in ADR-109 Amendment 11 (reserved, `10cd960`).

29. **Case L3.2, Q1 and Q3, on case's recommendations:** until L2.9's private view, the alert jump keeps
    making a case of its own (its own layer, no origin link, so no branch word remains); and jump cases
    made since L3.1 stay ordinary cases, because moving them would show their maker's marks to people
    they never shared them with. (Your rulings the same afternoon: *Ask the model about these* keeps its
    conversation with a private view only its creator sees; a shared branch's view is private to its
    maker, its other members named in the migration's report.)
30. **Studio L1.3, all three on studio's recommendations:** a schemas-only commit merged first for the
    staging steps and source references (published recipes stay byte-for-byte); a staged row's source
    references go in each element's existing provenance, so no adapter change; ADR-140 Amendment 11
    reserved (`f359ee3`) for what phase 7a built.
31. **Your P1 and admin rulings, for the record:** keys in the gateway's own database through its admin
    API (not my recommendation; every deployment gains that database, and ADR-135 Amendment 2 carries
    its key, backup and offline-install consequences); engines and defaults in a models file beside
    osprey.yaml; no second person, every change audited; a new `manage_models` right (ADR-112
    Amendment 7 reserved, `4c2edce`); a layer's size in bytes stored; the promotion policy field built
    now in L2.4 part 2 and enforced in L3.4.

32. **Admin's footprint count respects handling, reversing my earlier settlement.** I had settled R1 as a
    count "with no principal". The independent review showed that let an administrator learn that SECRET
    or restricted items exist in a layer, and their size, without clearance (rules 3 and 7; ADR-124
    decision 10). The count now takes the administrator's own principal and counts only what it may
    read. If you want administrators to see every layer's full size regardless of markings, that is
    your ruling to make as an ADR amendment; until then the strict rule holds.
33. **Case's L3.2 is split.** L3.2 is the views, the migration and the Conduit without branches; L3.2b
    (a fresh session) the Glass's Views panel and wiring `no_branches_check` into make ci, whose
    real-tree test is red until then.
34. **The object stores' ports are guarded** (`fdfc244`). A studio offline run had written three synthetic
    files to stack a's store on 9000 while I had left it unguarded; nothing was read.

35. **An alert naming a corrected node is still withheld from its readers** (rules' finding, ADR-109
    Amendment 11 point 7): it becomes its own small step, L2.8d, before L2.9, on rules' recommendation.
    It withholds too much rather than too little, so nothing leaks meanwhile.

36. **No row key reaches provenance or the Glass, hashed or not** (studio's L1.3 review, then its own
    reviewer): a plain hash of a booking id or a phone number can be reversed by trying every value, so it
    is still a source-system identifier (rule 7). An element names its source row by source, row number
    and load; the load's own record resolves that on the server. This replaces my first ruling (hash it).
37. **All three ready steps were held by their independent reviews** (admin L2.4 part 2, rules L2.8c,
    studio L1.3), each for a real access or rule 8 defect, and sent back with a fix list. None of the three
    had run its own lane-reviewer first; each has been asked to, as the plan's review rule 1 says.

38. **A removed composite case's layer is never merged, only deleted or left** (admin's Q5, on its
    recommendation): ADR-143 Amendment 2 decision 1 merges a removed case's layer "into the dataset", but a
    composite holds none of its members' data. The alternative, merging into a member dataset the merger
    chooses (an Author of that member doing it), is yours to choose for L3.4.

39. **Merges now stand on the lanes' own gate runs when the tree is the tested one** (your ruling), and a
    finished lane's idle session is ended and reopened fresh for its next step (your ruling). The first
    such merge, admin's L2.4 part 2 (`a1d7f94`), took minutes rather than half an hour.
40. **Admin's L2.5 is split:** L2.5b finishes *Disable…*'s transfer list once case's ownership route
    (L3.8) is on main, several case steps away.

41. **Your answers given in the lanes' own windows, for the record.** Rules L2.8d: a corrected node's own
    pair recorded by each caller (no port change); carry (g) built now from my review's items 11 and 13;
    ADR-109 Amendment 12; the alert store's DDL under one advisory lock. Admin L2.5: custom roles in a
    versioned Postgres table, held as `role:<id>` in Keycloak and read per request; the Super user a
    preset of analyst, data engineer and rule author, never one role; the guard rails (no edit leaves no
    enabled holder of manage_people; no unknown right, both halves of a decision 7 pair, or a right the
    giver lacks), recorded as ADR-145 Amendment 5; team members are the holders of the team's role.

42. **A dashboard identity stays a case Viewer; no other service account is a member** (admin's L2.5 Q5,
    reconciling ADR-112 Amendment 5 decision 5, "a service account can't be a case member", with ADR-111
    decision 7, which has an Author grant a dashboard's identity Viewer so Superset can read its feed).
    A dashboard at Editor or Author is refused, as is any other service account anywhere; owners, team
    members and leads refuse every service account.
43. **Platform's P1 held by its independent review** for two credential defects: an engine's address could
    be changed to send its key elsewhere (my ruling: changing the address drops the key, which must be
    entered again), and a failed rotation deleted the old key while reporting it set. Case's L3.2 held for
    a rule 3 merge path into another case's layer, and for live suites not run on its final tree.

44. **Rule 14 slip, platform on stack a (about 15:5x UTC), reported and undone by the lane within minutes:**
    a refused acquire chained with `;` ran on, creating a probe database and network on stack a's Postgres
    while rules held it; nothing of the owner's or the tests' own databases was touched. Rules re-checks
    its run for that minute. Prompt L now says `acquire … &&` only, and no docker or psql on a stack not held.

45. **A backup holds no model key** (platform P1): spec/05 §6.1, "a backup carries no secrets", already binds,
    so the gateway's key rows are left out of every backup and each restore says which keys to enter again.
    The restore refusal and its override flag go. The cost, re-entering keys after any restore, is the one
    §6.1 already accepts for every other secret.

46. **A live-only regression on main since rules' L2.8c (`befcf56`):** 14 live pack tests fail, because their
    fixture passes no alert store and Amendment 11 now refuses one without the journal. Neither L2.8c's
    offline make test nor its leased run included those files. Fixed (tests only) on lane/rules, landing
    with L2.8d. Lesson for every lane's leased run: include each live file the change can reach.

47. **Merged since the restart:** admin L2.4 part 2 (`a1d7f94`), rules L2.8c (`befcf56`), case L3.2 (`c3fc52f`),
    studio L1.3 (`04a8cdf`), platform P1 (`b2fc5e2`), each after independent review rounds that each found a
    real access or credential defect. Fresh sessions now run admin L2.5, rules L2.8d, case L3.2b, studio
    L1.4 and platform P2. Rules' L2.8d is held by its review: the rule audit leaked the words the strict
    ruling (b) withholds. **Main's Glass calls the branch routes L3.2 removed until L3.2b merges, which
    must be before the single push.**

48. **Your answer in case's window (L3.2b), for the record:** an opened view is a read-only lens: the canvas
    shows only the view's items, laid out and collapsed at its threshold by the Conduit, the timeline set to
    its window, a banner "View: <name> · n not shown · Back to the case"; nothing in a view changes the
    case's working set.

49. **Studio L1.4, on studio's recommendations:** staging steps are pipeline nodes (one source of truth;
    the recipe's staging list built from the graph at save); per-step counts on the load report, withheld
    with the other counts; rejection refs with no row key; a dataset's own reference list read from its
    version file, written by a small import module until L1.6 builds import, a run with no file refused in
    words; the drawer's sample over the first ten rows with the person's own token, writing nothing.

50. **Your two rulings before stepping away:** admin's Q3b (a), only the administration rights must be held by
    whoever gives them; rules' lowered-alert question (a), not my recommendation: a no-node alert follows a
    correction that lowers its evidence, as a lowered cited link already does, the correction being the
    authorising act (the audit entry and pack items follow too).

51. **Platform P2, on platform's recommendations (each can be widened later):** limits per engine, per team
    when teams exist; a budget in tokens, not money, so no price list is kept; **no usage per person at all,
    and no person id sent to the gateway** (the conservative choice; recording who uses models is yours to
    turn on). The gateway's own per-model limits proved unenforced, so each engine gets its own gateway key.

52. **Your permission for the docs lane's start:** when D2's condition is met, I refresh your deployment on
    this machine: `ospreyflow backup` first (the data, Enron included, so nothing needs a long reload), then
    `ospreyflow start --build` from the checkout, restoring the backup if the rebuild needs it. Model keys
    must be entered again after a restore (backups carry no secrets). Still never `make dev-up` for lane
    tests, never airbyte on 8000.

53. **Rules' L2.8d merged** (`7dfb3a1`, your ruling (a) applied to the queue, the audit and packs alike;
    main's 14 red pack cases green again); rules' fresh session is on L2.9. **Admin's L2.5 held by its
    independent review** for a privilege escalation: Invite did not apply your Q3b rule, so a people manager
    could invite an administrator and sign in as them; plus the lock-out race and a cached right on open
    sockets. Being fixed.

54. **Rules and Monitoring is gated as ADR-146 decision 2 says** (rules L2.9, a tightening): offered only to
    triage_alerts and author_rules holders, its routes refusing anyone else. Meanwhile the Data Engineer loses
    rule deploy and retire, an alert's detail and screening-list administration (held rows stay, shared with
    the Studio's Runs); the Administrator loses the rule audit (back with Admin › Audit, L2.6) and
    screening-list administration (back with the Studio, L1.6). Home's counts are unchanged.

55. **Merged:** admin L2.5 (`3656678`, the Invite escalation fixed) and case L3.2b (`3eca381`) in one gated
    batch, whose one integration fault (admin's Roles screen listing the removed branch_case) was fixed in it;
    **main's Glass no longer calls a removed branch route, so the single push is no longer blocked.**
    Playwright no longer reuses a server already on its port (`758328a`): two lanes' keyboard runs had been
    served another worktree's tree. Fresh sessions: admin L2.6 (Audit, ageing), case L3.3 (drawing boards).

56. **Your switch at about 20:55 UTC:** sol runs out of tokens until 21:30, so rules, case, studio and platform
    were paused cleanly (each a HANDOFF.md and a wip commit, no stack held) and resumed on the default account;
    every lane and this orchestrator now share that one account. `accounts.conf` still maps them to sol, so
    their next fresh sessions after 21:30 go back to sol unless you say otherwise. Platform P2 merged
    (`66009ab`); P3 begins with P2's carried credential fixes. Open, yours if you wish: should the geospatial
    admin routes drop their extra osprey-admin role check and rely on manage_geospatial alone? Kept both
    (dropping one would loosen access).

57. **Sister lanes (your ruling):** case-b (L3.5, L3.7, then L3.8), studio-b (L1.6, then L1.8) and rules-b (L2.12
    after L2.9) on sol; the parents and everything heavy on the default account; a third test stack, c
    (ADR-142 Amendment 4). case-b and studio-b open at 22:00. **Docs split into D2a** (README, guides, welcome,
    website, GOV.UK) **and D2b, every deck** (your ruling: the overview, architecture, Prison Intelligence demos
    and script, AML, pitch and AE decks) after the rule editor and drawing boards are merged.

58. **Your ruling on rules' L2.9 Q1:** the Rule author role gains read_alert_queue (whoever triages must read
    the queue), amending ADR-112 Amendment 5, so Rule authors are offered Rules and Monitoring.

59. **A rule 3 defect already on main, found by the independent review of studio's L1.4:** a source author
    could read another dataset's uploaded file by naming it in a pipeline's source node and previewing it
    (the save gate never checked a node's file against the dataset's own folder). Fixed in L1.4 before it
    merges, at one choke point covering Profile, preview, Test and the run. Test and the Map preview also
    lacked the drawer preview's guards (a hidden-row count oracle). The file-path gap is also in the code
    already pushed to `origin` (`e89d44a`'s `_confined` checks only the ingest root); no deployment runs it,
    and the fix goes out with the run's single push.

60. **For L3.4, settled now (case's question):** withdrawing a drawn item leaves in place a promoted link the
    withdrawer may not see (the drawn node goes, the promoted link stays), so the withdrawer learns nothing of
    it (rule 3) and no promotion is undone silently; refusing would reveal the link, and withdrawing it would
    undo a promotion without a word.

61. **Two access tightenings taken by me as the strict default (overrule if you wish):** (1) rules' L2.9: an
    alert's address must do the same reads whether the alert is present, hidden or absent, so its timing
    reveals nothing; the lane had accepted a timing difference without a ruling. (2) admin's L2.6: the
    model engines' change history is shown only to manage_models holders, not every audit reader (it named
    other units' people). Both steps held for these and their other review findings; L2.9 merges before L2.6.

62. **Studio L1.4 merged** (`16a709e`; the file-path gap closed); studio's fresh session is on L1.5 (expert
    steps). **Case's L3.3 held by its review:** opening a board counted drawn items the reader may not see
    (my ruling, strict: count only withdrawn or deleted references, ADR-144's lost-access count); the marking
    ceiling was not enforced through a composite; a withdrawn node's matches stayed live.

63. **Docker's disk filled (310 MB free of 197 GB)**, failing every object-store upload on all stacks. I pruned the
    build cache and dangling (untagged) images only: 85 GB free now; no tagged image, volume or container was
    touched, and your deployment's and airbyte's 16 containers kept running. Lanes told to re-run any live test
    that failed on an upload. Rules' L2.9 merged (`057a10e`); rules is on L2.10, and rules-b opened on sol for
    L2.12. Platform's P3 held for a map-key exfiltration path and host-check bypasses; being fixed.

64. **Two accepted ADRs reconciled (studio-b's L1.6), overrule if you wish:** ADR-146 decision 2 keeps
    load_screening_lists inside Rules and Monitoring; ADR-140 Amendment 9 decision 3, your later and more specific
    record, puts the deployment-wide list connector in Studio › Sources. Settled: the right acts in both (ADR-146
    Amendment 3); no one's rights change. Tied to your open question on which store is the store of record.

65. **Rules-b's L2.12 display choices (logged by the lane; overrule if you wish):** the Reports Viewer's banner
    reads "From alert: ‹its title›" (no short alert numbers exist; adding them is its own step); on the
    alert-monitoring board filtered to a rule, the outcomes and time-to-close panels say "(every rule)" until they
    are counted per rule (a small follow-up); "closed as not of interest" means false positive or no further
    action.

66. **The gazetteer becomes a dataset (platform's P4, settled within the rules):** the loaded place names sat in no
    dataset, so no case could search them. The build now stamps them as a dataset, `gazetteer-osm-<region>`,
    which a case's Author adds like any other; nothing is read across the dataset boundary. Platform's P3 merged
    (`246b51d`); platform is on P4, its last step.

67. **Studio-b's L1.6 held, a strict default taken:** a SQL or API connection had no dataset scope, so any source
    author could read any connection into any dataset they could edit. Settled strictly: a connection is bound to
    the datasets an administrator names, and a source may name only a connection bound to its own dataset. Also
    held for hidden files read, byte caps applied after the whole body was read, and connection secrets lost on
    every `apply`.

68. **Platform's P4 sent back after my independent review, with rule 7 settled strictly.** A gazetteer's source
    identifiers (`osm_id`, `uprn`) count as source-system identifiers. So once a case adds a `gazetteer-osm-*`
    dataset, they are stripped from every response the Glass gets (search, expand, node detail), not only from
    place search. Place search's "more places match" now counts name matches only. **For you:** the gazetteer
    recipe hard-codes its unit as `unit-1` (`recipes/osm_gazetteer.yaml:24`). That fails closed, but in a
    deployment with no unit of that name no case can add the gazetteer. I recommend the build takes the unit
    as a parameter; say if you would rather keep `unit-1`.

69. **Platform gains a P6, on my recommendation:** your ruling 6 (gazetteer places copied into a case's dataset)
    is built in the Conduit by P5, but nothing in the Glass can add or remove a gazetteer yet. P6 is that panel
    beside the place search, reachable by keyboard. Overrule it if you'd rather it waited.

70. **Removing a gazetteer from a case deletes nothing, on my strict default (platform's P5).** Deleting copies
    except those a case's link rests on would let an Author infer a link they can't see, from a place that stays.
    So every copy stays as the dataset's own place, still with its identifiers withheld. Removal stops the
    gazetteer's refresh and takes its places out of place search, the same for every copy. Overrule it if you
    would rather removal deleted unlinked copies and accepted that small existence signal.

- **Docker, 9 November about 09:00 UTC (your word):** removed 21 exited containers, `govuk-*` (18) and `noggin*` /
  `allmynoggins*` (3), plus earlier one exited `osprey-test-tls-*`. No volumes or images touched;
  `buildx_buildkit_noggin-release0` (exited) left, as its name starts `buildx_`.

- **Accounts, 9 November about 09:05 UTC (your word):** every lane moves to the default account (`ayan`) at its next
  changeover. The sisters (studio-b, case-b, rules-b) stay on `sol` until their current step merges or their
  session ends, then reopen on `ayan`. `~/.ospreyflow/accounts.conf` still names `sol` for some lanes, so I
  pass `--account ayan` explicitly; edit it to match if you like.

71. **Case-b's L3.7 merged (`e935ded`), with two choices for you to overrule:** promoted items are regraded too,
    and a later revert of a load whose link was regraded is refused for that link; a scheme file is never edited
    in place once items are graded in it (a change makes a new scheme).

72. **Two more test stacks, d and e, on your test server (`ospreyflow-test`, 9 November about 12:00 UTC, your word).**
    Nothing on it was wiped: its existing `osprey-small` deployment (about 12 GB of 62) was left running. d and e
    are built like stack b, bound to 127.0.0.1 there, and reached through one ssh tunnel per stack that
    `stack_lease.sh up` opens and `down` closes, so the tests and the port guard see localhost ports as before.
    Checked live under a lease: ArcadeDB, Postgres, Valkey and the object store all answered. **For you:** on that
    server port 1099 (likely the `osprey-small` ArcadeDB's JMX) listens on every interface and its firewall
    (ufw) is inactive, so it may be reachable from outside. Not changed by me; worth closing.
73. **Every test stack on your server, none on this machine (9 November about 12:30 UTC, your word: "instead of using
    my machine for testing the stack, use the small server").** The machine had rebooted; every lane session was gone,
    Docker Desktop was not running, and the leases on b (case) and c (studio) were left by dead sessions, so I removed
    them. Stacks b and c were recreated on `ospreyflow-test` like d (same images and settings, their own ports, bound to
    127.0.0.1 there) and listed in `lane_stack_hosts.tsv`. The new `~/.ospreyflow/no-local-stacks` switch makes
    `stack_lease.sh` refuse stack a, the last local one, even when it is asked for by name. b and c were checked live
    under my lease: ArcadeDB, Postgres, Valkey and the object store all answered through the tunnel. Three cases were red
    first against the old script. The fixture now gives every case a no-op `ssh`, so no case reaches the real server.
    **The cost:** `test_statelessness_clickhouse.py` runs under stack a only, so it cannot run until stack a is
    switched back on (`rm ~/.ospreyflow/no-local-stacks`, with Docker Desktop started). Docker Desktop stays off,
    so the local image scans in `make ci` are refused (`make -k ci`, as on the 429 days). Each lane uses the lease
    script from main's checkout, not its own branch's copy, until it next rebases.
    **Corrected, 12:50:** a stack's Postgres needs an `ospreyflow` database beside `osprey`. d had been created
    without it, and so had b and c, which I built from d's settings. Studio and studio-b each found it on their
    first runs: those runs failed (InvalidCatalogNameError), and each lane withdrew them as unmeasured. Each lane
    then created the database under its own lease (b by studio, c by studio-b), and I created it on d and e under
    mine (checked). It stays when a stack goes down. Whoever rebuilds a stack runs `CREATE DATABASE ospreyflow
    OWNER osprey` after creating its Postgres.
    **Your word, about 13:05:** up to four leased live runs at once, raised from two now that the stacks run on the
    server. Platform took d and case took e at once; rules takes the first stack to free up.
    **Live runs on the server itself (your word, about 13:20, option A).** The server is on the public
    internet, not your local network: one Valkey round trip through the tunnel took about 720 ms, so live runs were
    network-bound (case's 15-minute run was heading for 45). The new `stack_lease.sh remote <lane> -- <command>`
    copies the lane's worktree to `~/osprey-runs/<lane>` on the stack's host and runs the command there, next to
    the containers. It sends only what git tracks or would track, so nothing gitignored (the real-data exceptions,
    `data/`) leaves this machine. `osprey.yaml` goes as committed. It builds the server's venv (`uv sync --frozen`),
    copies the lease's info file there for the port guard, and runs the command with the stack's ports. I
    installed `uv` in root's home on the server; Node is not installed, so `test-js` and Playwright stay on this
    machine. The red records: three cases red against the previous script, then the two defects that matter
    planted at their call site (no `--exclude-standard`; the local `osprey.yaml` sent), each turning the case
    red. The first copy took about 2 minutes; the server venv built and 58 offline tests passed there.
    **Your rulings, about 13:45 (all as recommended):**
    1. CI on Python 3.12: already applied as `68e2ec3` (your word of 8 November) and waiting for the final push;
       nothing more to do.
    2. A removed composite case's layer is only deleted or left, never merged into a member (item 38 stands, L3.4).
    3. The server's firewall: ufw is on, denying all incoming except 1099 (ssh) and 443 (osprey-small). Checked
       afterwards: a fresh ssh works, port 443 is reachable from here, and the containers are healthy. Item 72's
       "1099 may be the ArcadeDB's JMX" was wrong: 1099 is the server's ssh port.
    4. Every new leased live run uses `stack_lease.sh remote`, after one trial run of mine; runs already started
       finish over the tunnel, and Playwright and `test-js` stay on this machine.
74. **Backups out of the checkout (your word, about 14:00).** On this machine: the latest local-lite set
    (`20261105T101543Z`, 5.3 GB) moved to `~/OspreyFlow/backups` (mode 700, size checked before and after);
    the two older sets and the four OpenTofu `.terraform` provider caches (1.8 GB, re-downloaded by `tofu
    init`; the tracked lock files kept) deleted. `OspreyFlow_Core` went from 21 GB to 3.2 GB. Only about 2 GB
    of disk came back, probably because the sets shared blocks (APFS clones). In the product: ADR-114
    Amendment 37 (written): every install names its backups folder at setup, no backup is ever written inside
    the checkout, and `doctor` names sets left behind and warns about a synced folder. Platform builds it as
    P5b after P5 (CARRIES). **For you:** Google Drive (a `solirius.com` account) had the oldest set open and
    appears to sync this repository from `~/Documents`, backups included. Those sets held the Enron dataset,
    which ADR-035 §C3 admits for this device only. Their copies in that Drive, and its trash, are yours to
    check and remove. The kept set is now outside `Documents`. Left for you: a stray untracked folder named
    `" .."` (820 KB, a copy of a pytest cache, made 12:52 today) in `OspreyFlow_Core`.
75. **The tunnelled live runs stopped, and the server run proved (your word, about 14:40).** Studio, studio-b,
    platform and case stopped their runs over the tunnel (platform's: 25 tests in 89 minutes). Each is recorded
    as withdrawn and unmeasured. My trial of `remote` on stack c ran three live files (Valkey, Postgres,
    ArcadeDB), 76 tests in 31 seconds on the server, 2 minutes with the copy. One failure is main's own: a stale
    branch test in `test_valkey_store.py` (carried to case). The lanes now rerun through `remote`. The stray
    files are in `~/OspreyFlow/stray-2026-11-09/`, and the Drive sync of `~/Documents` is off (your word).
76. **Docker off again (your word, about 15:00).** Docker Desktop had started itself after the reboot and run
    your `default` deployment (`osprey-local-lite`, 15 containers) for about 2 hours, with swap at 9 of 10 GB.
    Stopped with `ospreyflow stop --name default` (data kept in its volumes), and Docker quit; memory went to
    64% free. **For you:** turn off Docker's "Start Docker Desktop when you sign in" so a reboot doesn't bring
    it back. Admin's L2.6 and rules-b's L2.12 are ready to merge, and my independent reviews of both are running.
77. **Admin's L2.6 sent back after my independent review (about 15:35).** Six must-fixes, the access ones checked
    against the code by me. Operations' waiting promotions are open to every `operate_schedules` holder, where
    ADR-145 Am 4 decision 11 says the dataset's Authors with `review_promotions` and administrators. The
    dataset-source settings' words (legal basis included) are shown in the audit beyond any Admin read. The
    overdue alerts' reader is matched by stored id alone. The picker's `writers` read has no live test. Three
    figures have no gate file, and some files are unlisted for ratification. **My calls:** the strict reading of
    the accepted ADR for each, so none comes to you. A seam contract test is left for L3.4's promotion store.
78. **Rules-b's L2.12 sent back after my independent review, and reopened on `ayan` (about 15:45).** A blocker:
    main's new `GET /v1/grading-scheme` (L3.7) turns the branch's open-routes pin red, so it rebases first. Also:
    `make test` never ran its vitest half; Admin's tips cover Roles only, where the carry says Roles, People
    and Datasets; and there is no ratification list. My earlier review's items 2 and 4 went unrecorded, their
    text lost with the previous orchestrator session; this review stands in for them. No rule 7 or fixture
    defect was found.
79. **Stacks f and g, a ClickHouse on each server stack, six live runs at once (your word, about 15:50).** f and g
    were built on the server like b to e, with the `ospreyflow` database. b to g each have their own ClickHouse
    (`clickhouse-server:25.8.33.6`, 18124 to 18129), and the lease pins its port and credentials; only a stack
    with no ClickHouse row is pinned to the closed 59994. **`remote` hardened after studio's run lost its ssh
    session an hour in** (16:02; the server was not loaded, load 5.5 on 16 cores): the run now starts detached on
    the host (`nohup setsid`), logged in `osprey-runs/<lane>/.runs/<stamp>/log`, and is followed with ssh
    keepalives. `remote-log <lane>` reattaches and returns the run's exit code, and a second run is refused while
    the lane's last is alive. I stopped studio's orphaned pytest on the server. Five cases were red against the
    previous script, and 109 lane-tooling tests pass. Live on f: ClickHouse answered as `osprey` on 18128, 25
    tests passed in 28 s with the copy, and `remote-log` reattached with the same exit code.
80. **Docker started again at 16:19 UTC** (launched as an app, with no containers; not by me, and no lane
    record shows a start). Quit again on your word, and every lane told never to start it. The Docker setting
    "Start Docker Desktop when you sign in" is still yours to turn off.
81. **Admin's L2.6, the second review (about 16:40): nine of ten fixes hold; decision (j) sent back.** The lane
    had logged, as its own decision, that an Author's unit is not checked for the promotions list and the
    overdue alert. The case's own access check refuses another unit's Author outright (`get_authorized`'s
    `owning_unit`), so (j) would have shown another unit's promotions to someone every read refuses. Checked in
    the code by me. It comes out, with a cross-unit Author added to the L3.4 contract test and to A8. **My call,
    not yours:** the strict reading of Am 4 decision 11 and rule 3.
82. **Two server gaps found by studio-b's first remote run.** Git had no identity for root, so a test's
    throwaway repository could not commit: set once in root's global git config ("OspreyFlow test runner",
    `test-runner@ospreyflow.invalid`). The server's venv is synced without the `extraction` extra (spaCy,
    transformers, torch), as CI's is on purpose (ADR-108 phase D), so cases needing spaCy skip there as in CI.
    Lanes record them as not run. My call: torch would add gigabytes to each lane's venv on the server.
83. **Admin's L2.6 merged (`0194eec`)** after three independent review rounds. I gated it at the merge result, since
    the lane's gates predated its last fixes. `make -k ci` and `make test` fail only where this machine fails
    (Docker, the local `osprey.yaml` and Valkey) and on main's phone-extraction case. test-js: 2,775 passed;
    `MatrixView.budget` failed under a load of 18 and passed alone twice. Also: case-b reopened on L3.8 (your
    word), and two carries for studio from studio-b's review. Rules-b's and studio-b's fix rounds are in review.
84. **The Mac restarted again at about 17:09 UTC**, the third time today. The load averages read 26–27 on 12 cores
    just before: every lane's `make test`, vitest and Playwright at once, plus my rules-b merge gates; Kandji's
    file-scanning agent works harder under that load. A restart helper session (`ospreyflow-73`) resumed me and
    the eight lanes, and released stack c (rules' run there was lost). Detached runs on the server survived:
    studio on b, platform on d, case on e. **New, my call:** a lane asks me before any heavy local run (`make
    test`, `make -k ci`, test-js, Playwright, glass-perf), and at most two run on this Mac at once. Lost with
    `/private/tmp`: my uncommitted offline-on-server work, rebuilt in `~/dev/osprey-wt/orch-offline` and
    committed on `orch/offline-remote` (`b999d10`; three cases red against main, 112 pass). It is being trialled
    now, and rules-b's merge is being gated with it.
85. **Your ruling, about 17:50 (case-b's L3.8, access):** when a person being disabled owns an item the
    administrator can't see (above their clearance in their own unit), Disable is refused with its own 409,
    `withheld_items`, whose words name nothing about the items. It stays refused until an administrator of that
    unit cleared to the item's marking, or the item's case Authors, transfers it; nothing is moved by anyone who
    can't see it.
86. **Rules-b's L2.12 merged (`dcb1406`, brought onto main's later records as `3790da0`).** I gated it at the
    merge result. `make -k ci` fails only where this machine fails. test-js: 2,813 passed, with
    `MatrixView.budget` failing under a load of 29 and passing alone. `glass-perf` green: the 50k/250k first
    frame in 5.4 s. make test's pytest half ran on the server through the offline verb and was no redder than
    main's own run there. That copy's own failures (no git, no Node, the run folders in its root) are being fixed
    before the verb reaches main. Platform's P5 and case's L3.4 are ready, and my independent reviews of both are
    running. Studio-b's L1.8 merges next.
87. **Your ruling, about 18:05 (the licence register):** `git`, GPL-2.0-only and in the Conduit image since Round
    13bf, leaves the image if nothing in the Conduit calls it at runtime, and the licence gate goes back to
    refusing every GPL package. If something does call it, that comes back to you. Platform's P5 had let it
    through as "awaiting the owner" with no question on record.
88. **Sent back after my independent reviews (about 18:05):** case's L3.4, with two blockers confirmed in the
    code. The waiting-promotions seam is wider than L2.6's contract (4 of its 9 readers fail), and a merge's
    read grant can be reused. Platform's P5 has nine must-fixes, no leak: the set-up console's map Build broken
    by a required `--unit`, the Java image never scanned, the `git` exemption, incomplete red evidence, and an
    unaudited partial copy.
89. **Your ruling, about 18:15 (git, revisited):** the Conduit does call git at runtime. Publishing a Studio recipe
    commits it to a repository on the recipe volume, because spec 09 §6 makes the repository the record. So, (b):
    studio replaces the git command with dulwich, under its Apache-2.0 licence, in L1.7 (CARRIES). Then git
    leaves the image and the licence gate stops admitting it. Until then git stays declared, waiting on that
    carry.
90. **The offline verb on main (`ada8460`, fixed at `dc0b7cd`); studio-b's L1.8 merged (`6b63bbb`, onto main as
    `f8933ae`).** Lanes' `make test` and test-js now run on the server, which passes 9,590 or more with 2 known
    failures, where this Mac fails 24 with 30 errors for want of Docker. Rules found that a second call rewrote a
    running lane's copy before refusing it; that cost rules a live result. Now refused before anything is touched,
    the old run layout included. At studio-b's merge I first applied its registry and harness diffs, which belong
    with its tips patch. registryCoverage went red, so I took them out again and carried them with the tips
    (CARRIES). Case-b's L3.8 merges next. Admin has a fresh session on L2.7 (your word).

## Two questions for you (case's L3.4; access, so yours; strict defaults built meanwhile)

1. **Who may delete a removed case's layer from Admin?** Case had made it deployment-wide (to match Admin ›
   Datasets' list), so one unit's administrator could withdraw another unit's removed-case layer, closing its
   merges and rejecting its waiting promotions, with no undo.
   - **(a) Recommended, and built meanwhile:** only an administrator of the dataset's own unit; another unit's
     request answers 404, as *Name an Author* does.
   - (b) Any administrator, deployment-wide, as case first built it.
2. **May a Reports Viewer who is an Author of a dataset's home case make the five removed-case writes** (open,
   merge or cancel a layer merge, delete)? ADR-112 says a Reports Viewer is refused every write; ADR-146
   decision 10 says read-only.
   - **(a) Recommended, and built meanwhile:** no. The writes need a dataset Author's right, which a Reports
     Viewer doesn't hold.
   - (b) Yes, as an Author, amending ADR-112 for this case.
   - **Your rulings, about 20:05: (a) for both.** Admin's Delete of a removed case's layer is for an administrator
     of the dataset's own unit only (another unit 404 alike). A Reports Viewer, even one who is an Author, is
     refused the five removed-case writes (ADR-112 stands). Built so already; ADR-143 Amendment 5 drops
     "provisional".

91. **Case-b's L3.8 merged (`2317b49`, onto main as `01a2a75`), with ADR-145 Amendment 8 written: your Disable
    ruling.** Three findings were settled at the merge, each a one-line census entry or a fix of mine: the
    route's audit action classified among reads in admin's census; the route recorded as not yet a section's
    (L2.5b draws it); my `SKIP_JS` test given a clean environment (red when run inside `make test SKIP_JS=1`).
    Admin's L2.5b is now unblocked (CARRIES). Case's L3.4 is in its third round with two questions for you
    (above). Studio's L1.5, rules' L2.10, platform's P5 and admin's L2.7 are building or testing.
92. **Studio's L1.5 (expert SQL) sent back after my independent review (about 19:50).** The sandbox itself held
    (an AST gate, external access off, the configuration locked before user SQL). But a SQL step could **lower a
    row's marking** (`SELECT * REPLACE (NULL AS classification)`, or a window copying higher-marked values into
    lower-marked rows). **My call, not yours:** the strict reading of Map's "tighten, never loosen". A step that
    rewrites, drops or computes a handling-bound column is refused. Also: forgeable `_ref` provenance, a refusal
    able to quote a cell value, Test blocking the event loop, an unbounded output, a cross-dataset test that
    couldn't fail, and three shared files committed on the branch.
93. **Two of mine, fixed (about 20:00).** My census line at case-b's merge was too long, so main failed ruff
    (E501); wrapped at `b0671be`. Also, Google Drive had left **11,633 empty `Icon` files** across the main
    checkout, its `.venv` included. One inside `jsonschema_specifications`' schema folder broke the audit tests
    here, so I removed them all, after checking every one was empty and none is tracked. The lane worktrees in
    `~/dev` were never synced. `.git` still holds leftover temporary objects from today's crashes (git warns about
    them); harmless, and left for you, or for a `git gc` when no lane is working.
94. **Admin's L2.7 sent back after my independent review (about 20:45).** Needs you serves the overdue-promotion
    alerts without the items' own marking (the gap I carried at 19:40), so it could show a reader what the Studio
    hides. Also: only 4 of 69 keyboard specs rerun, and the words test missing most Admin sections. **My call:** no
    above-clearance proposal flag in Needs you. It leaks whether any proposal is still open, and that reader
    can't act on it (ADR-143 Am 4 (b), strict). Studio's L1.5 is clear once its live run is green (a GROUPING
    SETS rule added in the last look). Rules is fixing ClickHouse's `event_frequency` on c.
95. **Rules' L2.10 sent back after my independent review (about 21:05).** Team routing is sound (the read in the
    SQL at every alert read), and the `event_frequency` fix is correct at its edges. But the new
    `rule_evaluation_failed` audit entry shows the sweep's counts to readers its firings are hidden from (rule 7),
    and its gates predate three adapter commits. ClickHouse `account_activity` was changed unreported, so the two
    adapters now disagree. The read-path purge is proved only against a fake. Checked in the code by me; my call.
96. **Your word, about 21:35: more in parallel.** Three new pieces start now:
    - **platform-b** (a new sister lane) builds P5b, ADR-114 Amendment 37's backups folder, beside platform's P5;
    - **studio-b** swaps the git CLI for dulwich, then lands the Studio's tips after L2.7;
    - **docs** starts D2a now, leaving out the alerts and rules pages until L2.10. This relaxes your earlier gate
      on docs; the README stays a draft for your approval.

    Case-b, rules-b and the old studio-b session were closed, their work merged (your word).
97. **The UK public sector client's Cloud Platform (your client decision, about 21:50).** ADR-148 is reserved
    (`9b2e74f`) and written as ACCEPTED (design) (`0ab4eb2`). The build plan is applied (`35fac3b`): P7–P11
    after P5 (P11 held), L1.9 and L1.10 for studio-b, D2c for docs, the merge order and the ownership lines. P7's
    brief (`process/lanes/platform/BRIEF_P7.md`) opens a fresh platform session after P5 merges, proving itself
    on a kind/k3d cluster on your test server, with no client access. Nothing building today stopped.

## Questions for you: ADR-148 (recommendation first)

1. **ADR-148 question 2, the settings and key files** (model settings, map settings, the write-only keys) that
   every Conduit replica reads:
   - **(a) Recommended:** in Postgres (RDS), the keys encrypted with a KMS key the namespace holds; each replica
     notified of a change through Redis.
   - (b) Kubernetes Secrets the Conduit writes (needs a Role to write Secrets in its own namespace, which the Cloud
     Platform team may refuse).
2. **ADR-148 question 3, Java in the Conduit:**
   - **(a) Recommended:** on this profile, the Conduit without Java; the basemap is built off-platform and uploaded.
   - (b) One image everywhere, accepting the larger image and its scan findings.
3. **ADR-148 question 1, the recipes repository:** asked only after P8's report of who reads and writes it.

98. **Case's L3.4 merged (`32c6f49`, onto main as `1fba324`)** after three independent review rounds and your two
    rulings: promotion, the waiting-promotions seam filled, a removed case's layer merged or deleted, Admin's Delete
    in the dataset's own unit, and the Reports Viewer refused every write. I gated it at the merge. My own slip,
    caught there: the merge's CI-wiring apply left a conflict in `ci.yml`; resolved, and the two tests reading it
    pass. Admin's L2.7 merges next, on top.
99. **My mistake overnight: about six hours lost.** At about 23:45 UTC I asked you L3.9's type-mapping question as
    a blocking question, and nothing moved until your answer at about 05:20. Eight lanes sat idle 5½–7½ hours
    waiting for stacks, slots, reviews and merges. I now never wait on a question while lanes are running: it
    goes here, the recommended option is built, and I carry on (saved as a standing rule).
100. **Your ruling, about 05:20 (L3.9):** "The entity type matching should be resolved through the ingest studio
    where the type is mapped to the types in the domain model." So the merge's Map step maps each drawn type to
    any domain-model type, as a Studio load does, and the load writes the items as those types; recorded in
    ADR-143 Amendment 7 (reserved). **For you, from docs:** `publish_pages.sh` must copy `drawing-boards.html` and
    `three-places.html` before the site is next published (you alone publish).

## Evening, 7 November: your records of 7 November applied

Done from `process/inbox/specs_2026-11-07/` (its prompt's steps 1–3, 5 and 9; step 4 is sent):

- **Reserved and appended unchanged:** ADR-146, ADR-143 Am 2, ADR-144 Am 1, ADR-145 Am 4, ADR-140 Am 9, ADR-112 Am 5, ADR-142 Am 1 (`129ebb9`, `ba8a194`). Every number was the one you drafted. **What I changed:** one path in ADR-142 Am 1 (the launcher's and the heartbeat's paths, given from `scripts/` where the check needs `OspreyFlow_Build/scripts/`), so citation-check finds them; and three files the records name before their steps build them (`tools/ui_words_check.py`, `tools/no_branches_check.py`, `apps/workspace/src/help/roles.ts`) are allowlisted, with the step that removes each entry.
- **My own amendment renumbered:** I had used ADR-142 Amendment 1 at 18:15 for "a merge's make ci takes no lease", not yet pushed. I reverted it (`edfe77c`), and it now follows yours as Amendment 2.
- **The build plan** takes `BUILD_PLAN_CHANGES.md` in full (`ce785b8`), with merge order items 7–14, and `progress.tsv` gains the new steps.
- **Glass L2.4 part 1 merged** (`d035223`), make ci green on the merge. Part 2's brief is rewritten to the new columns and waits for L3.1 on main.
- **O-acc built** (ADR-142 Am 1): accounts, `pause`, `pause --now`, `pause-done`, `switch`, `fallback-switch`, `merge-ok`, `orchestrator --account`, the monitor's `paused` state and *Account*. Each check shown red with its own branch removed (`process/lanes/O-acc_RED_RECORD.md`). The runbook's commands are in its new "Accounts, pausing and switching" section. **For you:** write `~/.ospreyflow/accounts.conf` when you want a second account (with no file, every session uses `~/.claude-ayan`, as today), and restart the monitor so it shows the *Account* column.

| Lane · step | State | Next |
| --- | --- | --- |
| studio · L1.2a | building (events-only withdrawal, part A redo); holds the lease | its report, then my review; L1.2b unchanged |
| glass · L2.4 | part 1 merged | part 2 waits for L3.1; then L2.8 (G2, G3, G9) |
| case · L3.1 | the branch-layer fix is in (`ed83cf9`, `9e516f7`); waiting for the lease for the live set and the migration rehearsal | my review, then the merge |
| docs | idle | D2 opens after L2.9 merges; no "three places" edits meanwhile |

**Two calls of mine on the branch-layer fix (case asked):**
- A case opened from an alert keeps an empty layer of its own. Your ruling names branches; taking analyst writes away from alert-jump cases would change what users can do, and ADR-146's private view (L2.9) retires the jump anyway.
- The migration gives each **existing** case made from another (`branched_from`) an empty layer of its own, because nothing in the table tells a branch from an alert jump, and linking them to the original's layer would let an alert-jumper read it (rule 3). The output names and counts them. It is written into ADR-143 Amendment 1 as a temporary exception to ADR-144 Amendment 1 decision 2, and L3.2's migration moves anything in such a layer into the original's, tagged `from_branch`.

**A visible change, my call (glass, L2.8b):** the rule audit's log of fired rules will stop showing the words of entries written before L2.8b that name an alert, because those entries don't record the alert's links and transactions, so nobody can check whether the reader may see them (rule 3). The entries stay; only their words are withheld. Say if you would rather have those old entries' words shown to Authors and unit administrators regardless.

**Found on main, not from any lane (studio, 20:50 under its lease):** ClickHouse's `event_frequency` fails on main at `2be871d`. Its RANGE frame offset of 2592000000 (30 days in milliseconds) isn't a 32-bit integer, and ClickHouse refuses it. `make ci` doesn't run ClickHouse, so it stays green. I'll schedule the fix as a small shared step after the current merges.

**Shared test database leftovers (found 00:35, 8 November):** live tests that create deployment-wide rules (`test_load_checks`, `test_rule_sentence_routes`, `test_rule_maker_checker_routes`, `test_rule_schedule`, `test_rule_sentences`, `test_sentence_rules`) leave them in the throwaway Postgres's `osprey` database. Every later case then lists them, so a test assuming it is alone fails. Some of the "red on main itself" figures below may be this rather than code. A test-hygiene step is to come: each live file cleans up after itself, or works in its own database. Until then, figures blamed on main are checked on a fresh database before they're believed.

**Live tests red on main itself (case's main-side run, 22:29–22:35 UTC, under its lease, on `b82a88f`):** these fail with or without any lane's work. `make ci` doesn't run them, so they never showed. Not yet owned by any step; I'll schedule them after the current merges:
- ClickHouse `event_frequency` (above);
- the model and recognition ports (4 LiteLLM, 4 Stanza): no model services on the throwaway stack. This is an environment gap, not a code fault;
- golden recall, `pid_recipe` r1 and r14, `typology_rule_routes` (10 rules listed for a new case), the phase 6 and phase 8 scenarios (phase 8's 403), `witness_statement`;
- the KYC rules' true-positive test, written on 13 October, which expects `closed`. Since ADR-133(d) (`4fd664a`, 1 November) a high-severity alert goes to `closing`, so the test is stale, not the code (glass's finding).

**Your rulings, 23:15 UTC (all as recommended): 1a 2a 3a 4a 5A.** L5 and L6 → ADR-143 Amendment 3; R8 → ADR-146 Amendment 1; QB → ADR-099 Amendment 16 (all three written). L1.2c's option A → ADR-110 Amendment 16, reserved for studio, which builds it as L1.2c. **From now on I act on my recommended option and list it here for you to overrule, rather than asking** (your instruction, 23:15). Your three overridable calls above (old audit words withheld; an alert-jump case's own layer; existing case copies' empty layers) stand unless you say otherwise.

## Since 08:00 (you were away from about 08:20)

You allowed L1.2, L2.2 and the docs lane's first brief, and merging as overnight. The briefs are at `e1423d4` and `cf1dc54`, and the Studio's build plan is committed at `a56f2f9` so lanes can read it. The studio and glass branches were fast-forwarded to `main`, and docs was set up and opened.

| Lane · step | State at 08:40 | What it needs |
| --- | --- | --- |
| studio · L1.2 | you answered Q1–Q3 (a, a, a) at about 09:20; building; ADR-140 Amendment 8 reserved (`6b3895b`) | its report when it is ready |
| glass · L2.2 | you chose 'Rights decide' and narrowing the crossing rights; building. The narrowing changes ADR-112's bundles, so it needs a reserved amendment (I check at review) | its report when it is ready |
| docs · website | **merged locally** as `fb03eae` after review fixes and a rebase; session closed. Your rulings: a section turns 'Built' as soon as its feature merges, in text only; i2 is named once the import's ADR is accepted | none. The publish script still does not copy the two new pages (README.md says so) |
| case · L3.1 | says every review item is built; wider live run under the lease | my second review, then yours. Not merged |

Nothing merged since glass, and nothing pushed. A lane that asks you a question only in its window, rather than in `REPORT.md` as Prompt L says, cannot be answered from here (O3).

## Lanes

| Lane · step | State | Commits on `lane/<x>` | What proves it | Left |
| --- | --- | --- | --- | --- |
| studio · L1.1 | **merged locally** as `32c0f36`; session closed by you | `dbc3956` `4f958f5` `e9b8b31` (after the rebase) | ruff and mypy clean; reviewed; `make ci` on the merge is red on 3 gates, down from 5 (below) | your diff; r1/r14 PID tests red since `2f24d85`; the two trivy findings |
| glass · L2.1 | **merged locally** as `6e178b2`, after two reviews | `7df24ec` to `6f1fa89` (rebased) | the map, `spec/glass_redesign/ALERTS_GAP_MAP.md`; citation-check green; second-review fixes spot-checked | ADR-146 (the alerts journey) after your answers to its §6; widening `APACHE_DOC_PATHS` (O2) |
| case · L3.1 | Q1–Q4 built and recorded (07:35); **review 07:45: not merge-ready**, two cross-case leaks from Q1 (an extraction record readable by case B; the resolution trigger reads layer `NOT_SAME_AS`) and seven untested invariants; your rulings on findings 5, 7 and 8 sent in a nudge | `7a6097f` `ef0a7fa` `8d7c4e2` and five earlier (rebased) | conformance and read-set tests; ADR-143 Amendment 1, ADR-099 Amendment 14 and ADR-136 Amendment 1 written | the two leaks; findings 3–6, 9, 11–13; then your review. Not merged. |
| docs | not opened (P7: after the first merge) | none | none | none |

**Since 05:30:** you closed glass and I reopened it on Prompt R. Its first open swallowed the nudge (an `open`/`resume` defect, fixed red first at `f93e1df`), so I sent it again, and glass is now making the three review fixes before it rebases. Studio rebased once you woke it, and was merged.

**Waiting:** I cannot see the windows. No lane reported a permission prompt, and none shows the signs of one: every lane is idle at its prompt, not mid-tool. Case was silent for 31 minutes while its live suite ran; that was a real run, not a stall.

## make ci

**On the merges `32c0f36` and `6e178b2`** (full run, 05:38–05:42): red on `trivy-image-harness`, `trivy-image-superset` and `test-file-coverage-check` only. ruff and mypy are green. That is three of the baseline's five, and nothing new.

The full run is at `54fbd3d`, with downloads. It has five failures, which are the baseline:
1. Core `lint` (ruff I001)
2. Core `typecheck` (mypy, 5 errors)
3. `test-file-coverage-check` (unwired live tests: 6, per studio)
4. `trivy-image-harness`: CVE-2026-78661 in the compose plugin's `golang.org/x/net`
5. `trivy-image-superset`: CVE-2026-109518 in Debian 12's `apt`

Studio fixes 1 and 2 on its branch. 3 needs your diff. 4 and 5 need a decision (below). The live `conformance` job will also stay red on r1/r14.

## Questions for you (recommendation first)

**Case, L3.1: answered 06:55, all (a).** ADR-143 Amendment 1, ADR-099 Amendment 14 and ADR-136 Amendment 1 are reserved (`81bd510`), and L3.1b is in the plan. Type `read your nudge` in case's window to start it. For reference:
- **Q1.** Where do today's analyst writes go?
  - (a) Hand-marking and `manual_link` into the layer; questions and extractions into the source.
  - (b) All four into the layer.
  - (c) All four stay in the source.
- **Q2.** Where does data go when it is added to a case that reads a composite?
  - (a) The composite's own id.
  - (b) The case's layer.
  - (c) Refused.
- **Q3.** What egress does a layer have?
  - (a) The strictest of its sources'.
  - (b) Always `none`.
  - (c) Set per layer.
- **Q4.** How is phase 5 split?
  - (a) The target model, reference lists and ADR-126 move to a new L3.1b.
  - (b) All of it stays in L3.1.
  - (c) That half goes to Lane 1.

**Glass, L2.1** (the full text is in §6 of the map):
- **Q1.** One alert list or two?
  - (a) One queue.
  - (b) Both, with the inbox renamed.
  - (c) As today.
- **Q2.** Where do the new alert kinds live?
  - (a) The drawn-item match in the case queue; promotions overdue in *Needs you* and Operations.
  - (b) Both in the case queue.
  - (c) A *board* queue kind.
- **Q3.** What does "my team" mean?
  - (a) A label plus filters.
  - (b) The unit only.
  - (c) Remove it.
- **Q4.** How does an alert lead to the case and back?
  - (a) A private view with "← Back to the alert".
  - (b) Home's rows only.
  - (c) As today.

**Orchestrator:**
- **O1.** The trivy findings.
  - (a) Rebuild without cache; where no fixed package exists yet, add a dated `.trivyignore` entry.
  - (b) Hold `make ci` red until upstream ships a fix.
- **O2.** `product-tree-link-check` and the provenance check scan a fixed file list, so `spec/glass_redesign/` and `spec/ingest_studio_redesign/` are never checked.
  - (a) Widen both to every `spec/**/*.md` except `06_DECISIONS.md`.
  - (b) Leave them as they are.
- **O3.** A nudge reaches only a lane that is mid-turn.
  - (a) Record this in an ADR-142 amendment; you wake an idle lane by typing in its window.
  - (b) The orchestrator may `resume` an idle lane that is ready to merge.
- **O4.** Case edited files outside its ownership map: `services/api/{datasets,questions,model_routing}.py`, `scripts/{case_seed,stamp_datasets}.py`, `a11y/every-harness.spec.ts`.
  - (a) Ratify them for L3.1.
  - (b) Move them to a shared commit.

Also asked by the lanes:
- Reserve ADR-146 for "the alerts journey" (glass), and an ADR-136 amendment once case Q3 is ruled.
- `make dev-up` collides with your deployment on 2480 (case).
- `BUILD_PLAN_INGEST_STUDIO.md` is uncommitted (case).

## Diff for `ci.yml` and the Makefile (yours to apply)

1. A `lanes-check` target, added to `ci:` (as sent in chat at 22:45). It runs the five step-0 tests and `python -m tools.adr_reservations_check`.
2. Studio's diff, on `lane/studio`: `OspreyFlow_Build/process/lanes/studio/L1.1_ci_makefile.diff`. It adds six live test files to `ci.yml`'s `conformance` job and to the `test` ignores in both files. The reviewer checked it hunk by hunk.
3. On case's branch: `test_analyst_layer_store.py` and `test_migrate_cases_to_one_dataset_store.py` need the same wiring. The lane has not written a diff yet.

## Notes

- **For you to rule when back (studio):** under "Only the rows' events", a dropped row that comes back merges into its own old link, so three loads can't be reverted (ADR-127 decision 6). For now this is recorded as a known limit (my call). The options: **A** (recommended), count a returning row's merge into its own withdrawn key's link as the row's own, so its load reverts (step L1.2c); **B**, keep it as a limit; **C**, a returning row writes a new link (the pair shows twice until a revert).
- **A possible rule-3 leak on main, found by studio:** a Studio load stamps no dataset, and two cases' rows on the same pair merge into one link, whose occurrence count then includes the other case's. Studio proves it after Part A, and fixes it as Part A2 if it's real.
- **The monitor's NEEDS YOU** now holds only what needs you (`f594705`/`237898f`); merge-ready and behind-main items are listed for me and never notified.

- **18:10, case L3.1's final review: not merged** (your go-ahead was conditional on it passing). Eight fixes sent, all my calls within your read-only ruling: a composite case's leftover canvas items are reported as unplaced, never written into a member; monitors keep working, with a composite case's alert nodes going into its layer; schedules and runs on a composite are refused before anything is written; the corrections' last word closed; a red companion per check; the Postgres composite check tested on Postgres; a migration rehearsal on a seeded throwaway stack.
- **A risk for you:** running `scripts.migrate_cases_to_one_dataset` makes every case that names several datasets a read-only composite case, your own deployment's included (no loading, extraction or confirming there until composite writing is designed). Case's rehearsal will list which seeded cases that hits.
- **Studio's shared schema commit** (RowElements.event_ids) is on main, with make ci green.

- **18:00, first push.** `make ci` fully green; `main` pushed to `origin` at `03a3dae`, and `git ls-remote` matches (PUSH_LOG.md). Merged since the last note: glass L2.3 (variant B, `d4fe5e5`) and the CI wiring (`03a3dae`, your diffs, applied by me on your word). **My calls while you were away:** glass's three L2.4 questions (placeholders' rights; Proposed types under Data; Approval rights a placeholder), all as recommended. Case's records that aren't dataset content keep working in a composite case. Studio adds event ids (A), with the schema as a shared commit first. I ended studio's exhausted session and opened a fresh one.

- **Stopped at the orchestrator's usage limit (about 13:20).** Merged to local main since the last note: studio's Part 0 (`f00afec`) and glass's L2.2 (`fd38da4`). make ci is red only on `test-file-coverage-check`, which waits for your diff, studio's `L1.2a_ci_makefile.diff`. It supersedes L1.1's; apply one, not both. Open:
  - **Case L3.1:** your ruling "Composites read-only for now" has been sent. Case rewrites L3.1 to refuse every non-layer write in a composite case, then needs a review and yours.
  - **Studio Part A (`b875c5d`):** not merged. The review found that a link's withdrawal still depends on other cases' rows (`edges_created` differs when a row comes back; the live links and their events differ). That needs your ruling: withdraw only the dropped rows' events and leave every graph element (recommended), or record the residue. Also the case half of `only_this_pipeline` was never shown red, the live test's plants aren't real, and the reds aren't on record. Part B is to start in a fresh studio session.
  - **Glass L2.3 part 2 (`7aba817`):** must-fixes 1–3 are done; it hit its usage limit. Left: REPORT.md, the minors and a full keyboard run. Reopen it with `lanes_launch.sh resume glass`.
  - **The Matrix performance budget:** still to be measured by me on a quiet machine.

- **Your ruling, 13:00 — 'Never withdraw nodes':** a snapshot's withdrawal takes back a dropped row's links and events only. This closes a rule-3 leak on main since phase 4: the node staying, and the Runs tab's 'graph writes' figure, revealed that something hidden touched it. ADR-110 Amendment 15 is reserved (`a2de4ad`); studio builds it in Part A, and its allowlisting of the unfiltered read is dropped.

- **12:30, studio L1.2 merged** (`25b1084`, registry ids `0bf628b`). `make ci` on the merge: the trivy images are green now, but `route-coverage-check` (the new preview-graph route isn't in spec 03) and `provenance-annotation-check` (11 'phase N' in spec 09 and DEMO_GUIDE) turned red. That is my process slip: I ran `make ci` after keeping the merge, not before. Studio fixes both as Part 0, and merges now keep `make ci` on the merge result first (`2edd327`). Phase 6's exit is not met (L1.2b).

- **My calls, 12:05, glass L2.2's third review:** a place is offered only for the rights that reach its entry screen's first read, so the Studio opens for `edit_pipelines` as on main. Legacy `loader` and `source_approver` accounts are no longer offered a Studio that would then refuse them. `/v1/exports` (the compliance ledger) gets an explicit Admin rule. ADR-067 Amendment 1 is released unwritten. **Case L3.1's fourth review:** two more composite gaps (an entity's confirm or retract changes the member; accepting an email finding fails), both inside your existing rulings, so sent to case without a question.

- **Your ruling, 11:40:** only a case that loads into a dataset lists or opens its pipelines, in the store's query. **My sequencing:** it lands as L1.2a after L3.1 (the build plan's merge order), and L1.2 merges on main's current rule first. L1.2b closes phase 6's exit. **Settled from the code, not put to you:** glass's two questions (the seven routes already refuse Analysts on main; schedule preview is exempt from place assignment because it reads no store).

- **Corrected, 11:20:** the 'Re-home the routes' question rested on wrong facts. The first glass review missed that each Studio route also checks a Studio role, and I passed its reading on unverified. So Analysts never could upload or read sources, and Administrators only previewed schedules. Your corrected ruling: no route moves place; places follow the routes' full checks; only the run history narrows, to `run_pipelines`. ADR-145 Amendment 1 is to be rewritten to the true facts before merge. The lesson: I check a reviewer's access claims against the code before they become a question for you.

- **My judgement, 11:05, under your delegation:** dev-up's ports stay as they are. Moving ArcadeDB off 2480 would have pointed the demo guide's reset (`drop database`), the hand-run Conduit and `seed_paysim` at your deployment, because they default to `localhost:2480`. The leased stack is now the throwaway test stack the lanes already used, and the lease checks it.

- **main's fast test tier** (`ci.yml`'s `test` job, not `make ci`) has three real failures from phase 4's withdrawal: `test_revert_elements_by_type` and `test_write_onto_a_reverted_node` (SQL expectations), and `test_unfiltered_node_lookup_confined` (`snapshot_withdrawal.py` calls `live_edges_touching`). Your ruling: studio fixes them as L1.2a, after L1.2. Two more fail on this machine only: `test_deployment_schema` (your local `osprey.yaml`) and `test_layout` (`graphify-out` at the root).

- **Owner rulings, 10:45.** Trivy: rebuild, then a dated ignore where no fix exists yet. The perf budget (`MatrixView.budget`, failing on main) is to be measured under the lease on a quiet machine. Widen the link and provenance gates to all of `spec/` except the decision log. Ratify out-of-map changes where needed (now in the build plan). Owner questions now reach the owner through the orchestrator, by cross-session message.

- A change to `lanes_heartbeat.sh` reaches a running `watch` only after it is restarted (Ctrl-C, then run it again). The merged-lane false alarm was fixed at `cc2e443`, and the monitor was restarted at 07:20.

- A beat the orchestrator sends on a lane's behalf records the orchestrator's head, not the lane's (glass, 05:53). Send it from the lane's worktree. Minor; not fixed tonight.

- `origin` is public and stands, as you ruled. Pushing waits for a green `make ci`.
- Case's throwaway ArcadeDB was bound to `0.0.0.0:2491`, not loopback. It is stopped now.
