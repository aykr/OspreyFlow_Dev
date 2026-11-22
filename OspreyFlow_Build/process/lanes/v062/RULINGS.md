# The owner's rulings for the v0.6.2 slice line

Rulings given in conversation, written here so the conductor and every seat read them (rule 11). Newest first. No
client's name or abbreviation is written in this file, nor in any message about it.

## 19 November 2026 (night): the owner is away until morning; the standing word for the night

The owner's word, 19 November 2026 (evening). Standing until he says otherwise; he is away until the morning.

1. **Start anything that becomes ready, without asking, up to four builders.** In this order when there is a choice: CO3 as soon
   as PL3 merges, then BL7, PL2, PL1, BL2.
2. **Verify and merge whatever passes, one at a time. Push when GitHub is green** (the 18 November ruling on GitHub failures
   still applies).
3. **Do not start** PL4 (needs the owner's word, and AD1), AD1 (needs the key-handling review) or AD5 (needs PL4). **Do not touch**
   CO2, GG6 or BL6: they wait for the line fixes (the third line-fixes session).
4. **Stop starting new work, and finish only what is running, if any of these happens:** either account passes 70% of its
   weekly allowance; a call to `sol` is refused again; a merge runs longer than 60 minutes; two slices stop for the same
   environment cause.
5. **Anything that needs a decision that is the owner's: leave it stopped and list it.** Do not wait on him for anything else.
6. **In the morning, one table:** what merged, what is running, what stopped and why, and usage per account.

## 19 November 2026 (later): four standing rulings on rounds, tracks, builders and starting

The owner's word, 19 November 2026 (about 06:00 UTC). Standing: they apply to every slice, without asking per slice.

5. **From a slice's third round on, a gap in a test never blocks.** If the verifier finds no fault in behaviour, the
   slice merges, and each remaining test gap becomes a backlog row, without asking the owner. A fault in behaviour still
   sends the slice round again. (Findings are marked "FAULT IN BEHAVIOUR:" or "GAP IN A TEST:" by the verifier.)
   **This takes effect once the accept-step session's work (the owner started it on 19 November) is in the line**;
   until then GG6 and BL6 wait for it, with no more rounds (the owner, 19 November, answer (a)).
6. **A stopped slice frees its track.** When a slice stops for the owner, the next ready slice on that track starts at
   once. GG1 does not wait for AD2, and BL7 does not wait for BL6.
7. **Four builders.** The owner has set balanced to four builders and four rounds in the dial, by day and by night, and
   tracks 3 and 4 are on sol in the accounts file. (The line counts only slices in the building or verifying phase against
   the builder limit, so a stopped slice already frees its place.)
8. **Start everything that is ready**, under the standing approval: SE2, SE3, SE4, BL7 and GG1, as the builder limit allows
   and the account windows (under 90%) permit; the rest start as places free up.

## 19 November 2026: rounds, accepting a slice narrower, and the invite form's design rule (AD2, BL6, GG6, SE4)

The owner's word, 19 November 2026 (early morning UTC):

1. **AD2: a general design rule replaces the earlier one.** The invite form is drawn only when everything it depends on
   has loaded. Until then it shows a loading or error message, never a choice and never a statement about what the
   inviter can give. Tests cover a late and a failed load of each thing it depends on. One more round (round 5 of 5).
   **If AD2 stops again it is set aside, the owner is told, and GG1 is freed to start without it.**
2. **GG6 is accepted narrower, on the owner's word, and merged as it is.** The ADR-014 Amendment 2 sentence ("Still not
   checked": the production-build tile test sits outside every gate) is added later, with the gate wiring it describes;
   the backlog row stays. No round.
3. **BL6 is accepted narrower, on the owner's word, and merged.** The test that pins the printed line with the client's
   word replaced in a path becomes a backlog row. No round.
4. **Verifier findings are reported split** as "fault in behaviour" and "gap in a test" (18 November, in the briefs of the
   extra rounds).
5. **SE4 is split.** SE4 holds C016, C164 and the board list cut at 100; `cases_pulled`, C170, C246 and L09 wait for their
   own build ids and rulings.
6. **Not yet possible:** the slice line has no step that merges a slice whose last verdict is findings (the merge
   script requires a verifier pass at the tip; `resume.py` has no accept action). Items 2 and 3 wait for one, which only
   the owner's hand can add to the line.

## 18 November 2026: MapLibre 6 now, Sigma 4 first in the GOV.UK modules (GG6, GG2, GG5)

The owner's word, 18 November 2026 (about 14:15 UTC), on the evidence in `slices/GG6.md`:

1. **GG6 is a new slice on the plan, under the standing approval.** Today's workspace moves to `maplibre-gl` `>=6.4.1 <7`
   on Sigma 3. ADR-014 Amendment 2 is **accepted by the owner**, not proposed. The acceptance must include: the map
   loading tiles in a real browser on the new version; the performance budget; and `make trivy` passing with the
   CVE-2026-85061 entry gone. Nothing in the evidence was run in a browser, so every claim there is unproved until a test
   shows it. **If a browser run shows a regression, the slice stops and the owner is told. No fallback to 5.x**: trivy
   still fails it.
2. **The GOV.UK graph and map modules (R4, R8; GG2 and GG5 on the plan) start on Sigma 4.** R4's first step proves the
   performance budget (`spec/02_GLASS_FRONTEND.md` §5) on Sigma 4, and falls back to Sigma 3 if it cannot. **The shared
   package imports no `sigma`, `@sigma/*` or `maplibre-gl`** (the check that fails if it does, shown red and then green in
   scratch, is described in the evidence; it is wired in only after it is shown red in the tree, rule 15).
3. **Moving today's React workspace to Sigma 4 is decided after R4 has met the budget.** It is not planned now.

## 18 November 2026: GitHub failures that are not ours (standing)

The owner's word, about 13:20 UTC, on a run of main whose `conformance-recognise` job failed in the image build
(`stanza.download`: `ConnectionResetError`, no test of ours failing):

1. A job that failed on a **download, network or runner fault, with no test of our code failing**: the conductor reruns
   it (`gh run rerun --failed`), up to **twice**, without asking, and tells the owner afterwards.
2. While such a run is in progress or being rerun, slices that pass the **full gate on the Mac may merge on the Mac**.
3. **Nothing is pushed to origin until GitHub's run on main is green.** (The push script defers while a run is in
   progress; the conductor therefore makes no commit to main in the moment between a run finishing red and its rerun
   starting, and says if it could not keep that.)
4. If a rerun fails a second time, or **any job fails in our code**, the conductor stops merging and brings it to the
   owner **at once**, with the job, the failing test and the commit.

Every report says which of these applied.

**Superseded on 20 November 2026 (the owner: "Applied", the fourth line fixes are on main).** Item 1 stands as the
first step of the new rule below. **Items 2 to 4 are replaced** by the 20 November ruling "GitHub is a second opinion, not a
gate" (section of 20 November 2026): merges go on the Mac's full gate whatever GitHub's last run says; every merge is
pushed; a red run is rerun once by hand; the same test of ours failing on the rerun too makes the line write a stop that
refuses merges, which only the owner clears; a release needs GitHub green on exactly the commit released (`release_green.py`).

## 18 November 2026: how the line runs, to cut down what needs the owner's hand

The owner's four rulings of 18 November 2026 (about 12:40 UTC).

1. **Standing approval to start a slice.** The conductor may start any slice whose build id is already on the owner's
   plan without asking, once it has (a) run the slice's acceptance and checks commands in a scratch worktree on main and
   shown the acceptance **red for the right reason** and the checks **green**, and (b) passed the citation check on the
   brief. Still the owner's: scope, rulings, protected files, the GOV.UK demo, the live step, a new build id, and anything
   that loosens or exempts a check. *How the conductor reads (a):* where the checks command names the slice's own new test
   file, which cannot exist on main, the check is run without that file and the table says so.
2. **Batches.** A stopped slice does not interrupt the owner. The conductor carries on with every other slice it can and
   brings the open decisions together, as numbered questions with options, at **13:00 and 18:00** the owner's time
   (this Mac's clock), or sooner only if every track is stopped. Security faults and anything that cannot be undone still
   come at once.
3. **The conductor's own malformed command.** Once the line has a step for it, the conductor may correct and resume a
   slice that stopped **only because the conductor's own command was malformed**, provided the corrected command runs the
   same test files, is proved on main first, is logged, and the owner is told afterwards. Never to change what a check
   tests. Until that step exists, the conductor keeps giving the owner a resume script. (The step's own limits are in the
   line, not in this file: the conductor can edit this file, so no authority here is enough on its own.)
4. **Fix the line's gaps now** (reverses "leave them"). One session outside the line, started by the owner, with the brief
   `slice-line/proposals/LINE_FIXES_BRIEF.md`, in this priority order: (a) a resume step, and the step in 3; (b) a dry run
   of a slice's frozen commands at `slice_start`, which refuses to start a slice whose commands do not run; (c) the test
   settings the Stop hook and the merge script lack (the Playwright slot, `env: full`: F4, F6, F8); (d) the hashed list
   reaching a slice's worktree without the owner (F5); (e) usage recorded per slice, seat and account; (f) a red GitHub run
   stops merging and shows on the board (F2); (g) BL1's record name (F3), then F1's three protections. Each with a test
   shown failing first; one set of diffs and one list of commands for the owner to apply.

## 18 November 2026: three compressed files exempt from the client-name check (BL6)

The owner's word, 18 November 2026, on the verifier's findings for BL6 round 2:

- The client-name check (`OspreyFlow_Build/tools/client_name_check.py`) exempts **exactly these three paths, and only
  while each is not text**: `OspreyFlow_Build/marketing_site/OspreyFlow Intro Video.mp4`,
  `OspreyFlow_Build/marketing_site/deploy/assets/ps-govuk-matrix.jpg`, and `OspreyFlow_Core/docs/pdf/user-guide.pdf`. Each
  holds the client's abbreviation only as chance bytes in compressed data.
- **Adding any other file to that list needs the owner's word each time.** The list's comment in the tool says so.
- The check cannot read real text inside a PDF, an image or a video, so those files are not covered by it. That is a
  backlog row (`BACKLOG.md`, "The client-name check cannot read inside a PDF, an image or a video").
- As worded, the exemption is the whole client check for those paths while they are not text (the full name too, not only
  the abbreviation). The verifier noted that this is wider than its reason; the conductor asked the owner whether to
  narrow it to the abbreviation.

## 18 November 2026: the live step

- Off, a change that reaches live tests merges on the offline gates; each live test not run is owed, the board shows
  what is owed, and a release is refused until every owed live test has run.
- The merge script's live step is off (`OspreyFlow_Build/process/lanes/v062/live_step.yaml`), until the demo's
  images no longer share tags with test builds. The owner turns it on. On, it waits for the server's run queue or
  refuses (`OspreyFlow_Build/process/lanes/v062/slice-line/README.md`, "The live step").

## 18 November 2026: the client's name and Laurium (build id BL6)

1. **Where the client's name stays.** Only in `OspreyFlow_Core/NOTICE`, `OspreyFlow_Core/services/laurium/NOTICE`,
   `OspreyFlow_Build/tools/licence_check.py` and `OspreyFlow_Core/services/laurium/licence_gate.py`, as the licences
   require. Everywhere else it goes, in every form (the full name and the abbreviation), including beside Laurium in
   specifications, notes and recorded gate output.
2. **The wording.** "UK public sector client"; where the text credits Laurium, "the library's publisher".
3. **Laurium** may be named in the product and its records. Neither Laurium nor the client is ever named in a
   website file under `OspreyFlow_Build/marketing_site` that is published.
4. **BL6 is the first real slice through the line**: the reword, together with a gate check. Any naming of the client
   outside the four files above fails; any naming of Laurium or the client in a published website file fails. The
   check uses the hashed list (`OspreyFlow_Build/marketing_site/client_hashes.py`), so no name is written down. The
   owner adds the full name to the hashed list.

### What BL6's builder needs to know (found 18 November 2026, on main at a4c441f)

- **What exists.** By the hashed list (which today holds the abbreviation, not the full name): 21 occurrences in 14
  files, 2 of them in `OspreyFlow_Core/services/laurium/NOTICE`, which stay. By the full name, read from the NOTICE
  files' copyright line: 23 lines in 13 files, 9 of them in the four files that keep it. Two of the occurrences are
  inside a cited file path in `OspreyFlow_Build/spec/06_DECISIONS.md`; no file in the repository has that path, and the
  ruling covers it too. The two hits in tests are a docstring and a comment, which no code depends on.
- **The hashed list is local.** `client_names.local.sha256` is gitignored (the owner's ruling, 12 November 2026) and
  never committed. The owner, 18 November 2026: the merge gate reads it from the main checkout and refuses the merge
  if it is missing (built: the full gate copies it into the merge tree); on GitHub the check says in words that it was
  not run, never passes silently (as `client_hashes.ABSENT` does today).
- **What "published" means.** `OspreyFlow_Build/marketing_site/publish_pages.sh` publishes, from `deploy/`,
  `index.html`, `intro-video.html`, `public-sector.html`, `monitoring.html`, `assets/` and `.nojekyll`; and each of
  `sites/org/` and `sites/net/` whole. `OspreyFlow_Build/marketing_site/sites/README.md` and
  `OspreyFlow_Build/marketing_site/deploy/README.md` are never published, and the product export
  (`OspreyFlow_Build/tools/publish_user_repo.py`) takes `OspreyFlow_Core` alone. The one Laurium mention under `marketing_site` is in
  `sites/README.md`: the wording rule "Laurium is not named (the owner's decision, 12 November 2026)".
- **Laurium beside the client.** Where a record credits Laurium to its publisher, the publisher becomes "the library's
  publisher"; Laurium's own name stays.

## 20 November 2026: PL1, PL2, BL2, AD1, PL4 and PL6 (the owner's words of the day)

- **PL1 is the four demo and install faults (N05, N06, N07, N11)**; "sound" meant "in working order". PL1a (N05 and N06) is agreed on
  the readings: N05 keeps the resolution order and warns when the recorded home wins over a different product in the current
  folder; N06 exempts synthetic packs only from the checkout refusal. PL1b (N07 and N11) follows PL1a.
- **PL2** is the connection setting with the computed default and a refusal below a floor, and the Java notice in the image with a test.
  Cut as PL2a (Java notice) and PL2b (connection limits); the floor (420), the ceiling and the scope are the conductor's, told to the owner.
- **BL2:** the placed table is committed as it is, with a note giving both counts (180 placed; 154 open on 18 November; the 26 are
  the 19 "cannot tell" rows and the 7 proposed N19 rows).
- **PL3's fixed secret-shaped string** in a test plant is fixed in the next slice that touches `apps/pages`; tests generate one at run time.
- **AD1** is cut in three: AD1a (the server half, no workspace file), AD1b (the screen) and AD1c (the key review's open items). AD1a
  builds beside PL4 and is held unmerged; AD1b follows PL4 with its two imports adjusted (`keyboard/models-harness.tsx`,
  `keyboard/admin-models.spec.ts`); AD1a and AD1b merge back to back, with no release between; AD1c after them. The owner's rules for
  keys bind every AD1 slice: write-only, replace and remove and never reveal, audited without the key, only a holder of the right,
  the server command stays as a second route, synthetic keys only.
- **How the line is arranged from now** (the owner, 20 November, after the fourth line fixes). Standing.
  1. **Pull from the merge queue.** No new build starts while two verified slices wait to merge. Six builders is the ceiling, not the target.
     A build that is ready but held by this rule is reported as "ready, held for the merge queue", not as a problem.
  2. **Merge order is by what unblocks most**, not first finished. After CO2: PL4a, then PL10, then PL2a and PL2b. PL9a ahead of the PL2 pair
     once it is verified.
  3. **Builders by area**, so slices seldom collide: Platform (PL4, PL7, PL8, PL9, PL10, CO2); Studio (IS2 to IS6, CO1); Graph (GG2 onward, WS4);
     Admin, reports and rules (AD1, AD3 to AD5, GR2 to GR4, RM1). No two builders in one area's folders at once unless their briefs name
     different files.
  4. **Verifiers start the moment a build is green.** They never wait for a merge.
  5. **One or two scouts always run one or two builds ahead** of the builders, so each brief and its questions are ready early.
  6. **The owner's decisions come twice a day, about 09:00 and 16:00 UTC**, as one table with the recommendation first. Carry on with everything
     that does not depend on them. The owner is interrupted between batches only for a fault in security behaviour, a GitHub stop, or a line of
     his that frees work with nothing else to do.
  7. **Line faults go to the backlog.** Fixes are applied at most once a day, in a quiet window the conductor offers.
  8. **Each report starts with three numbers:** merged since the last report, verified and waiting to merge, builds held by rule 1.
  9. **No slice joins the merge queue until the cheap checks have passed on its tip:** the lint and format checks for every file it touches
     (ruff, eslint, the line-length rule), and the scan-map check for any test it adds, with its scan row already committed if it needs one. These
     go in every brief's checks from now on, and the conductor runs them on every slice before its merge starts (a merge attempt costs 25
     minutes; the checks cost seconds). The conductor's helper for this is kept in the conductor's scratchpad, not in the product.
  10. **Backlog rows for the line:** (a) the builder's Stop check always runs lint and the scan-map check, whatever the brief says; (b) a slice
      whose only open finding is a test gap is offered to the standing accept before it is sent to another round (PL9a missed it).
- **GitHub's keyboard failures: no stop, measure first, fix after slice E (the owner, 20 November, later).** (1) **No stop; merging carries on.** (2) **Before calling it a flake, measure it:** `alerts.spec.ts` and `account-unread.spec.ts` thirty times each on CO2's merge commit (`a38ccc8`) and thirty on its parent, on this Mac when no merge is in its test step, failures out of thirty for each. If the parent is clean and CO2's commit is not, it is a regression and comes to the owner at once; if both fail sometimes, or neither does, it is timing on a slow runner. (3) **The fix slice** (the specs wait for focus and for the count that arrives asynchronously, red first with a slowed clock) is cut now but **starts after PL4's slice E**, because slice C edits the same files; it goes with the default-view-name security row, first in the workspace queue. (4) **Until then each report says GitHub is red on the keyboard job and names the specs** (`alerts.spec.ts:275` and `:802`, `account-unread.spec.ts:35` and `:47`), so a new failure is not hidden behind it. **A rerun that passes counts as green for a release.**
- **The ledger tails (the owner, 20 November, later): a small Ground-lane slice to end the merge bounces.** Two slices append to the end of `spec/06_DECISIONS.md` and `spec/ADR_RESERVATIONS.md`: a `.gitattributes` entry gives those two files the union merge so two appended blocks are both kept. Not a line file and not protected. Acceptance: a test in which two branches each append a row and an amendment and the merge is clean with both kept, in either order; the reservation check still fails on a duplicate number, shown red; a check that an edit to an existing line is still caught by the reservation and decision-log checks if not by git. If the scout finds union unsafe for the larger file, the reservations table alone, with the reason. Started under the security-lane exemption.
- **SE5 merged on the owner's accept; the open rows go to AD1a (the owner, 20 November, later).** (1) **SE5 is merged as it is, first, ahead of everything except a PL4 slice**: on its branch no key reaches a wrong address on any traced path, which is the fault it was built for, and main is worse on every open row today. (2) **The still-open rows** (SE5's 10, 11, 15, 16, 19, 21, the start-up rows and design rules 3 to 8) **are not dropped: they are rows 29 to 38 of AD1a's key-path table and part of AD1a's restart as one design** (a record of intent written before a credential is deleted and cleared on success; one decision for the words and the mark; "put back" said only when it was; start-up marking every engine whose record says a key is set and has none); each open row is an acceptance test with a planted fault. (3) **The rule, refined:** a fault that can expose a key, show it back, log it or send it to an address it was not given for is never accepted; a fault that leaves an engine unavailable or the words wrong is fixed in AD1a and named in the release notes meanwhile. (4) **Release notes** say what SE5 fixes and what is open until AD1 lands (BACKLOG). (5) **PL4b2 is merged on the standing rule;** its one gap becomes a backlog row; then B3 and slice C start. (6) **AD1a: after SE5 merges, take main in and restart with the two add-round lines it already has.**
- **The owner's answers to the 20 November table (later):** (1) **SE5**: the add-round line is in; its builder is restarted with the one task agreed. (2) **SE6** is cut into SE6a and SE6b and all five points are confirmed as written; **addition: the administration guide says in a sentence that a chart needing Mapbox tiles will not load, and why.** (3) **SE7**: yes to all three; the default view name can
  reveal an unfiltered count to a reader, so it is a security row, first in the workspace queue after PL4's slice E. (4) **NW1** is cut as a new build, small, beside SE6a, with the failing test first (a start with every pull refused); it is fixed before DC1's wording, with SE6a and SE7: **DC1b and DC1c now need SE6a, SE7 and NW1 merged.** (5) **The browser measurement: option 3.** Nothing is measured by hand; the fix goes in
  regardless and **SE6b's standing test is the proof**; the pre-approved stack slot is released (none was taken). **Until SE6a is released, the wording says the tracking fix is in v0.6.2 and says nothing stronger about v0.6.1.** (6) The expired-token fix is CO2b (below).
- **The two red GitHub runs are explained (the owner, 20 November, after reading the logs):** runs 44730215386 and 44739376824 failed the same test of ours, `test_auth_entra_pages.py::test_a_token_from_a_realm_client_without_the_audience_mapper_is_refused` (both parameters), with "token rejected: Signature has expired": the parameters call `default_claims` at collection, so the token's 300-second life has ended
  by the time a 40 to 49 minute GitHub suite reaches it; on the Mac the suite is fast and it passes. A fault in CO2's test, not in the product and not a flake. The two keyboard failures in `alerts.spec.ts` were on the first run only. **Build CO2b** (a small fix slice, ahead of everything except a PL4 slice and SE5): each case mints its token when it runs, a red-first proof by moving the clock
  past the token's life, a check of every other test that signs a token or sets an expiry once per module or session (the Conduit's auth tests and PL9a's and PL10's new tests), the ones with the same flaw fixed, and a standing guard. **The red runs are not rerun and no stop is written: GitHub stays red on this test until CO2b merges, and every report says so until then** so a different failure is not hidden behind it.
- **DC1: the platform's stated intent, in the websites and the opening of the documentation** (the owner, 20 November; the source is `Claude outputs/ospreyflow_intent_2026-11-20/PROMPT_ORCHESTRATOR.md`, which is binding and is not copied here).
  Ground lane. **Evidence first, then diffs for the owner's approval; nothing reaches main, and nothing is published, pushed anywhere public or deployed, until he says.** It touches no file under `apps/workspace` while PL4 runs and takes no merge slot ahead
  of a PL4 slice, SE5, PL9 or PL10. **DC1a** is the truth check by read-only scouts, no builder; the report goes to the owner before anything else starts, with, for each gap, the choice "fix it first as its own small slice, or word the text to what is true today"
  (his decision); the Superset finding, if confirmed, is proposed (not started) as a small security slice with a standing browser test. **DC1b** (the two websites, through `build.py` only; the paragraph byte for byte from one constant), **DC1c** (README and the four guides,
  fresh wording; the correction of the three audit statements is part of it whatever else is decided), **DC1d** (welcome and install pages, not before PL4's slice E) start only after his word on DC1a; each is built on its own branch and verified, then stops; its whole diff and
  a rendered copy go to `Claude outputs/ospreyflow_intent_2026-11-20/`; it merges only on his line. The paragraph is never edited, reflowed or re-punctuated, and no new wording for it is proposed. Rules for all wording: outside the paragraph no "guarantee" about security or
  privacy outcomes; argue for open source on its merits, naming and characterising no proprietary tool (the architecture guide's section 9 table is listed for him as a question and unchanged until he answers); every claim true of the shipped product as DC1a found it (hosted model
  engines are an opt-in and described as one); plain English, British spelling; no client, competitor or partner named anywhere; synthetic data only. His questions come in one table in the twice-daily batch.
  **The owner's rulings on DC1a's report (20 November, later):** (1) **GDS Transport is not a gap against constraint 1** (it applies only to UK government, which is sovereign over it); keeping it off everywhere else stays with PL7 and AD4. (2) **Fix first, before any wording:**
  **SE6** (Superset's usage tracking switched off, no outside address in its content policy, and a standing browser test that no page a signed-in person can reach, in Superset, the Glass or the pages service, requests anything outside the deployment unless an administrator enabled a
  feature that needs it) and **SE7** (C045, a failing access-control test first), both in the security lane, cut and started under the queue rule; **DC1b and DC1c need both merged.** (3) **"Every access, export and model call must be attributable" stays in the paragraph and the gap is closed
  as SE8** (sign-in events recorded; every model call recorded with who asked, for which case and to which engine, in one record; every export writes its ledger row); **the guides state what "access" covers: every read and write of case data, with the reference reads that carry none (the type
  list, map tiles) named as outside it; until SE8 merges the guides say "coming"**; SE8's row is written and **it does not start ahead of PL4, PL9 or PL10 work**. (4) **PL11** (the licence register and gate for model weights, map data, fonts and base images) is later; the wording says "coming"; its row is
  written. (5) **The architecture guide's section 9 is reworded without naming any product; the named table moves to the internal specification** (in DC1c). (6) **The older site is not edited and does not carry the paragraph; DC1d's wording goes on the pages' own Home and Help.** (7) The browser measurement
  is added to the report when done and its result is told to the owner outside the batch.
  **DC1a measurement, pre-approved (the owner, 20 November, later): one local stack slot on this Mac, without asking again,** to measure the Superset question. Conditions: local stack, synthetic data only (not the test server, not the GOV.UK demo, nothing reachable
  from the internet); run when no merge is in its test step, and release the slot as soon as it is done; measure in a browser: sign in, open a dashboard at the `bi.` address and each other page a signed-in person can reach, and list every request to an address outside
  the deployment with the page that made it (an empty list is a result); change no setting to shorten the list (the product as it ships); no password, token or key in the report; if it costs little more, use the same slot to answer whether a first install can be made with no
  internet from a bundle, otherwise leave that as "read, not measured" and say so. The result goes in DC1a's report.
- **SE5: fix main's model-key address fault now** (the owner, 20 November, option 1). A scout found that main's model key code can leave gateway entries at a new address the record does not hold after a failed or interrupted
  address change whose undo also fails, and that a later key set then sends the key to that address (a reasoned path, to be reproduced first; if it cannot be, the build stops and the owner is told). Build **SE5**, security lane,
  touches no workspace file, runs beside PL4, **merges ahead of everything except a PL4 slice**. Fix: a failed address change never leaves entries the record does not agree with; the undo failing is loud (words and an audit record without the key), never a log line alone;
  start-up compares every entry's address with the record. The owner's key rules bind it. AD1a merges main in afterwards and keeps the stronger behaviour. Release notes name the fix in plain words (BACKLOG). **A fault in key handling is never accepted narrower:**
  AD1a's round 4 is judged against the conductor's table of every key path, and any row it does not close stops AD1a and goes to the owner.
- **The merge queue does not wait for SE5 (the owner, 20 November, later).** Merge in order: PL10, PL9a, PL1a, PL2a, PL2b. SE5 jumps to the front the moment it is verified, and a PL4 slice ahead of that. "Goes first" means first
  among what is ready, **never an empty merge slot.**
- **PL4 condition (b), changed again (the owner, 20 November, later).** If `dist_compare` reports the built output **SAME** against slice A's baseline (identical apart from path-only differences), the next PL4 slice **may merge without waiting for GitHub**:
  identical bytes cannot change the budget, accessibility or keyboard results. GitHub's run stays a second opinion, as for every other merge. **The wait for GitHub green applies only to a slice whose built output differs**; the slice's report says so, with
  what differs. Slice E's budget comparison on the Mac stands. (This supersedes the first change: a slice still starts building the moment the previous one merges.)
- **AD1a restarted with the whole key-path table as its brief (the owner, 20 November, later).** One design, not four patches: once a key is stored, the clean-up runs on every way out (any exception, cancellation, a refused delete), and start-up puts
  right whatever a killed process left, including SE5's case. Rows 3, 15, 16, 17 and 28 are each an acceptance test with a planted fault at the real call site; everything else in the table is re-checked by the verifier, row by row. It builds after SE5 merges
  and takes main in first. A key-handling fault is never accepted. The brief is the "Restart" section of `slices/AD1a.md`.
  **Rounds given (the owner, 20 November): two `add-round` lines are in `resume.tsv`.** The first is used after SE5 has merged and AD1a has taken main in; the second only for a fix round on the same table. If both are used and a row is still open,
  AD1a stops and comes to the owner with the table.
- **AD1a stopped on a key-handling fault, 20 November (after round 4).** The conductor's table of every key path (`slices/AD1a_KEY_PATHS_TABLE.md`, 28 rows) was made while round 4 built; judged against it, round 4 closes
  row 3 and leaves rows 15, 16, 17 (and the SE5 case, row 28) open, and the round-4 verifier found the same fault (a refused credential delete). By the owner's rule (a fault in key handling is never accepted; no standing accept, no narrower accept) AD1a is
  **stopped and not merged on any record the line writes**. Proposed to the owner: SE5 merges first; main is merged into AD1a (the stronger behaviour kept); the owner adds a round (`AD1a add-round`) with a short brief for the rows that remain; the table is rerun against that tip.
- **AD1a: one workspace file allowed** (the owner, 20 November, option 2 with conditions). AD1a's three red scan tests
  (`test_admin_sections`; in `test_place_routes`: the record of places by role, and the hidden-place refusal for `right:manage_models`) need
  `apps/workspace/src/shell/placesByRole.json`. AD1a may change **that one file** on its own branch, produced by its generator
  (`OSPREY_WRITE_PLACES_BY_ROLE=1` on the record test), never by hand, and no other file under `apps/workspace`. The rule it bends is about
  *landing on main* during PL4, and AD1a does not land then: it stays unmerged until AD1b is verified, after PL4's slice E. When main is
  brought into AD1a before its merge, the file is regenerated again from main's state, not merged by hand, and the three tests are rerun.
  The brief's "Round 2" section says so (`slices/AD1a.md`).
- **PL4 goes ahead of AD1**, released as five slices A to E to start after ADR-152 Amendment 1 is committed by the owner. The owner's
  ruling on ADR-152 decision 6: R2 may land as five changes, each leaving main green and changing no behaviour. `glass-shared` is an
  npm workspace dependency. Only the invite form's plain parts (`givableCodes`, `givableLevels` and the like) move; `People.tsx` and
  every React component stay in the workspace (I1). Conditions on "nothing changed": (a) slice A's comparison script tolerates
  differences that come only from a file's new path (chunk names, module order, source maps) and fails on a real change, shown red on a
  planted change of behaviour and green on a planted move before any later slice relies on it; (b) the budget, accessibility and
  keyboard runs are proved on GitHub after each merge, the next PL4 slice does not start until that run is green, and if it is red
  because of the slice the conductor stops and tells the owner; (c) slice E's budget comparison against A's baseline is on the Mac,
  with nothing else running. `PARITY_EXCEPTIONS.yaml` decides when a GOV.UK deployment drops React: each line is the owner's. While
  PL4 runs nothing else touches `apps/workspace`.
  **Condition (b) changed by the owner, 20 November (later):** the next PL4 slice **may start building as soon as the previous one has
  merged**; it does not wait for GitHub. It **may not merge** until GitHub's run on the previous slice's merge commit is green for the
  budget, accessibility and keyboard jobs. If that run is red because of the slice, the conductor stops the next one and tells the owner.
  Slice A moved nothing, so slice B starts building the moment A merges. The protected-file diffs of slice A go to the owner as soon as it
  lands (`slice-line/proposals/PL4A_MAKEFILE.diff` and `PL4A_CI_YML.diff`, each passing `git apply --check`; the Makefile comment names no
  `OspreyFlow_Build` path, as the builder's last round corrected, because Core's committed files may not name the Build folder).
  **Slice B confirmed by the owner, 20 November:** `packages/design` is a plain folder (no manifest, relative imports); `apps/workspace/Dockerfile` and `harness/Dockerfile` each copy it;
  the `declare module "*.css"` shim stays in the workspace; the JS colour mirrors stay (slices C and D); the acceptance does not carry the figure 111 but asks that **no code, configuration, test, build or
  guide file names the old path** (past decision-log entries are history, not rewritten, and are allowlisted for the citation check with the reason). `process/CLAUDE.md` is changed by the owner from
  the conductor's one-line diff (`slice-line/proposals/PL4B_RULES_ROW.diff`). The rest of the design folder: `scale.css` and `panelType.css` move in a **slice B2 straight after B** (plain token-only CSS imported by
  `primitives.css`); `primitives.css` stays with its React primitives and `fonts.ts` stays in the workspace (the conductor's reading, a scout confirms before B2's brief; all inside PL4).
  **Superseded the same day by the owner's ruling on the rest of the design folder (next item).**
- **The rest of the design folder** (the owner, 20 November, on ADR-152 decision 6's "tokens.css, primitives.css, fonts; read by the React workspace and tree-default alike"): (1) `scale.css` and `panelType.css` move in
  **slice B2**; (2) **`primitives.css` also moves to `packages/design`**, in B2 with the two files it imports or a B3 straight after, with the same proof (the built CSS identical to the baseline): it is plain class-based CSS with
  no React, the pages use the same classes so the Default tree looks the same as today, and the `.tsx` primitives stay in the workspace; (3) **fonts**: `fonts.ts` may stay in the workspace because it is tied to the Vite bundle,
  **but which families and weights are used is stated once in `packages/design`, and both front ends load from that list, each its own way. A test fails if either loads a font the list does not name.** (4) **Standing rule,
  restated:** any time the conductor would leave out or defer something an ADR names, it is brought to the owner as a question before the brief is written. (The conductor's reading of 20 November that `primitives.css` and
  the fonts stay out of PL4 was exactly such a deferral; it was put to the owner as a question and is overruled.) Cut: **B2** = `scale.css`, `panelType.css`, `primitives.css`; **B3** = the font list and its test. The `pages` side of
  the font rule is a prerequisite in the brief of the first page build that loads a font (PL7).
- **PL6** (the `pages` image scan): the scan script and its test with three planted faults; no edit to the Makefile or `ci.yml`
  (those are the owner's diffs).
- **Six builders** under balanced, tracks 5 and 6 on the default account (committed by the owner, 50ba572).
- **Panel frames are not a parity exception.** All ten panel actions are rebuilt for the pages in plain TypeScript as the new build
  **PL8** (needs PL3 and PL4; GG3 needs PL8). Row 517 of the front-end inventory goes in `FUNCTIONS.yaml` with an empty route. **Only
  the light/dark switch is a parity exception**; the other lines of the owner's list stand (478, 496, 520; 482 is a function with an
  empty route, planned as IS3; 515 and 516 as the owner decides line by line).
- **Standing design rule for the GOV.UK pages.** They keep the Default theme's behaviour wherever it can be rebuilt in plain
  TypeScript. An exception is only for something impossible or meaningless on a server-rendered page, and each is agreed by the
  owner. A scout for every GOV.UK page lists what the React screen does and flags anything the page would leave out, **before a
  builder starts**.
- **GitHub is a second opinion, not a gate** (the owner, 20 November). Once the fourth line-fixes session
  (`slice-line/proposals/LINE_FIXES_4_BRIEF.md`) is applied: merges go on the Mac's full gate alone, whatever GitHub's last run says;
  every merge is pushed, waiting only while a run is in progress; a red run is rerun once without asking; only a test of ours failing
  twice stops merging and comes to the owner with the job, the test and the commit; a release still needs GitHub green on the commit
  released. This replaces items 2 to 4 of the 18 November ruling on GitHub failures and the sentence in ADR-142 Amendment 9 ("while
  main is red, every merge is refused"; the owner applies `ADR142_AM9_COST_SENTENCE.diff`). **Applied by the owner on 20 November**
  (commits eeb217b to e29d1dd; 355 cases, every planted fault caught, installed). From then the conductor: merges on the Mac's gate
  whatever GitHub's last run says; when a run on main ends, runs `merge_slice.py watch-github`; if red, reruns it once by hand and then
  runs `merge_slice.py push-pending`; if the same test of ours fails on the rerun too, the line writes a stop and refuses merges, and the
  conductor tells the owner at once with the test, the job and the commit (only the owner clears it, `clear_github_stop.py`); a release
  needs GitHub green on exactly the commit released (`release_green.py`).
- **Two foundations every page build needs** (the owner, 20 November, after the stage 4 scouts): **PL9**, a real sign-in for the page service (the round trip,
  the session on the server, the page service's own client in the realm, sign-out and renewal; ADR-152 decision 5), and **PL10**, the `/v1` forwarder with the
  token kept on the server, uploads included. Both need only PL3 and touch no workspace file; they run beside the queue and beside PL4. Every page build's brief
  names both. Cut: PL9a (Keycloak first) and PL9b (renewal, provider-side logout, Entra after CO2); PL10 in one.
- **Scripts off: core works, extras excused.** Every task can be completed without scripts (read, search, forms, show, hide and fold panels, a table in place of
  the graph). Resize, reorder and the drawn canvas need scripts and are agreed exceptions **for that case only**: lines in `PARITY_EXCEPTIONS.yaml` marked
  "scripts off only".
- **Settled, not to be asked again** (the owner, 20 November): IS5g Verify waits for GG2 (no table exception); the Runs screen's Airflow download becomes the
  one neutral job file; IS5a builds the Studio frame and the Pipelines place goes to IS4, IS5's cut a to g is agreed; the pages carry the rights tip on Connect
  and the rights check on drawn merge (a backlog row adds both to the React screens); the matching rule lives on the type record, and IS2 is cut as the port, then
  types (after PL4 C), then make-live, versions and reference lists; IS3 is the read-only map, editing the run order and the whole-dataset load are IS6 with its
  Conduit change, a table with scripts off and lines as an enhancement; both trees carry the panel actions, PL8 in three slices, `frame-scroll.spec.ts` is in scope,
  the layout stores move in PL4 slice D; the Needs-you jump and typed text kept behind the help overlay are rebuilt, not excepted; PL7 in two (PL7b adds a test that a
  GOV.UK deployment renders no Superset; PL7a fixes the guide's section 6a); the GOV.UK demo is protected: no render change reaches it without the owner's word.
- **Deferred:** GG2's scope and the I12 thresholds, until GG2a (the budget page) has measured Sigma 4 on the owner's Mac; the numbers go to the owner then.
- **Slice A of PL4 may start** (Amendment 1 is on main, 2bcee28); its baseline is taken on main as it is after GG6 with nothing else running at that moment.
  `FUNCTIONS.yaml` follows the owner's rulings of 20 November, not any older text (row 517 is a function, PL8).

## 20 November 2026, AD1a rounds 7 to 9 and the virtual-key listing (the owner)

- **Row 36:** start-up never lists or reads the gateway's credentials (the listing returns the first and last two characters of each key). A key is never shown back, to a person or to the product. Instead a note of intent is saved before any credential is deleted or stored and cleared when the change is complete; start-up marks unavailable every engine with a note outstanding. The specification was corrected to this (ADR-135 Amendment 14 point 9).
- **Rounds 7 and 8** closed rows 28, 40, 36, 41, 21. **Round 8 stopped** with two audit-name rows open (42: the edit path's failed rotation has no `key_rotated` row; 43: `set_key` on an engine marked unavailable names its failure `key_set`). No key is at risk on either. **Round 9 (one round)** on those two rows; if either is open afterwards AD1a stops and goes to the owner, who then decides between a further round and accepting it with the two rows named in the release notes.
- **N4:** yes. Start-up may keep the gateway's listing of its own virtual keys (`GET /key/list`), because it holds hashed tokens and no key material. The specification says so beside the row-36 ruling, and a test shows nothing from that listing reaches a log, an answer or the audit.
- AD1a stays unmerged until AD1b is verified, in any case.

## 21 November 2026: the owner's answers to the twelve questions from IS1 and BL3 (file 009), and the leftovers of BL2 (file 008)

All as the conductor recommended. **Each is binding on the briefs named.**
1. **A type record carries** class, identifiers, the matching rule, and properties with an indexed flag (IS2). 2. **"Use it only"**: a third option in the inspector worded "use it only", with the hold behind it (X4; the slice that touches the inspector and the engine's hold branch: IS4's pipeline canvas, with the held-rows store). 3. **"Runs after"** is an ordered list on the dataset's model record, exported with the release (IS6, and IS2's record shape). 4. **Preview sampling**: a bounded reader (first N rows, stop reading) at the three call sites in `studio_profile.py`, `studio_staging.py` and `studio_map.py`; **N = 10** (CO1, server side; the Glass call from `NodePreview.tsx` is the Studio slice's). 5. **Expected version** on the model draft's PUT and DELETE, before IS2 saves (IS2's first step; SE3 left it owed). 6. **The page service stays off until a Studio page exists**; **the missing `pages.enabled` entry in the deployment schema is briefed with the next page slice (IS5a)**. 7. **The status bar is its own row in the shell slice** (GG2's shell, with ADR-124's withheld sentence). 8. **The Studio's map step is a new IS slice, named before IS3's brief is written: IS4m, under the existing build IS4 (the pipeline canvas); no new build id.** It waits for IS4's canvas and for the Sigma 4 proof (it mounts its own Sigma instance and is the only dragging in the Studio). 9. **Scenarios: one per slice before its page, with a first batch now**: the first batch is the scenarios for IS5a and IS3, written as the first item of each brief. 10. **GG5 is briefed now, with the strict-policy run on MapLibre 6.19 first**; the 18 November claim of a CSP build is void and the brief says so; **rotation and pitch (N22) stay GG5's own**. 11. **One evidence seat (RS1) after the PL4 chain is clear, CO1's two rows (C043, C068) first.** 12. **The removed identity's rows staying in the mart (N19) is its own small slice, SE6b, under the existing build SE6 (privacy), with the security builds and ahead of the platform ones; failing test first.** **N21 is a documentation fix with a test (platform, not security).**
- **The seven rows that need the client's environment or a definition (C150, C131, C151, C161, C167, C172, C178) stay parked under that reason, and C150 and C131 move from "in build" to Later.** (The placed table is the decision record's and is not edited: the move is this line.)
- **The seven proposed rows are N16 to N22** (`backlog/N16_N22_RENUMBERED_2026-11-21.md`); N18 (the pulls table) goes with the security builds ahead of the other new ones; C023 stays with the demo items and PL5 and holds neither BL2 nor CO1.
- **BL2 is done** when the papers are on main (the run-sheet row RS1 is queued work, not BL2's); **CO1 is written** (`slices/CO1.md`).
- **PL4d3d at round 8** (the owner): no fault and one test gap, accepted; the gap (no test runs the part of `rebaseline` that builds the workspace itself) is the first open row in `BACKLOG.md`. **At that merge the conductor checks the rebaseline step by hand** (the new baseline folder was built from the merged commit; its diff against the old lists only declared and knock-on units) and reports what was seen. His two `add-round` lines for PL4d3d are not used for an accept.

## 22 November 2026: sol until its reset (the owner, file 012)

sol is at about 89% of its week (the board read 88% at 05:30 UTC; default 56%) and **resets at 12:00 today, his local time** (the Mac's clock reads the same as UTC). **Until the reset the 90% stop does not apply to sol: keep using it for the seats and tracks it has.** (1) **If sol reaches its real limit, a seat on it fails on a rate limit: that is the account, not the slice. No round is counted against the slice; I tell him which seats stopped; a started slice moves to another account only by the line's own route (never by hand).** (2) **When choosing which waiting work to start first on sol: PL4's seats and the verifiers before anything else**, so a limit falls on the least important work. (3) **After the reset the stop returns to 70%** (his ruling of 21 November); I tell him when I see the reset (sol's seven-day figure falls). (4) **default keeps its own limit as it is.** **The pause of file 010 (no merge and no new seat until his "file 011" after the patches) is not lifted by this ruling.**

## 22 November 2026: the owner's answers on slice E (file 013), after file 011's work

1. **Scope: (a)**, `canvas/` and the files the decision text names (`color/nodeVisual.ts`, `ontology/schema.ts`); the other plain files move when a slice needs them. 2. **The structural types: (b)**, they do not move now (their only consumers stay). 3. **`communities`, `communityAssigner`, `communityWorker` stay in the workspace.** 4. **`labelChoices` and `iconChoices` stay.** 5. **The five files that must be split (`iconImage`, `linkMenu`, `selectionActions`, `toolbarCompact`, `toolbarVisibility`) stay in the workspace until a page build needs one**; not for good: the page build that needs one says so, and the split is cut then as its own slice with declared units. **There is no E2 now.** (A backlog row records the five files and the three structural types so the later split is not forgotten.) 6. **Proof: slice E is one slice and proves SAME; if anything in it cannot be SAME, stop and tell him before it starts.** 7. **The budget: (c), no run on the Mac; GitHub's budget job is the check. But a record requires the Mac figures: the answer does not change that record; the sentences are brought to him and he rules** (below, in the morning report). 8. **The files D3e's brief left stay.** 9. **The map's plain files are left for GG5a and GG5b.** 10. **Slice E may start the moment PL4d3e has merged; AD1a and AD1b merge back to back after slice E.** **Order: nothing here changes file 011's order.**

## 22 November 2026: the Mac run stands (the owner, file 014; withdraws answer 7(c) of file 013)

**The Mac budget run stands; his answer 7(c) is withdrawn; ADR-152 invariant I11 and his ruling of 20 November are unchanged.** (1) **The conductor takes the budget figures on the Mac now that PL4d3e has merged, with nothing else running: it pauses the seats itself at the first moment that costs least (no merge in its gate; no builder mid-round if it can wait a few minutes), records the figures where `PL4_BASELINE.json` says they belong, and tells him the figures and how long the pause was.** (2) **He approves slice E's list as reported: 25 whole-file moves, one slice, proof SAME; if `chunkedTextureRefresh` fails the package's no-browser-global test, that one file stays and the conductor tells him.** (3) **Slice E starts as soon as the figures are recorded.** (4) **Compare once after slice E has merged, the same way; if a figure moves beyond the budget's own tolerance, stop and tell him before AD1a and AD1b merge.** (5) Everything else in 013 stands.

## 22 November 2026: how slice E's speed is compared (the owner, in chat, after the figures of file 014)

**With about 12% between two browser runs, the comparison after slice E is: three runs on the Mac after it has merged, the middle value compared with the middle of the before-runs; only a move larger than the run-to-run spread counts as a change. The Matrix view's first frame already sitting at its limit (about 2,480 to 2,550 ms against 2,500) is a backlog row, not slice E's fault.** (The before-runs are in `PL4_BUDGET_FIGURES_2026-11-22.md`: three unit runs and two browser runs; **the conductor takes a third browser before-run at the next quiet moment before slice E merges, so both sides have a middle value**.) Backlog row 18.

## 22 November 2026: the algorithm every remaining part runs (the owner, file 015, decided after the morning: two merges in six and a half hours; the server's one result was right and was set aside)

1. **Build** on the Mac, as now. 2. **Verify and server test together:** the moment a part's builder's checks are green, send it to the server; the verifier reads it at the same time. **Until the demo-server session's change lets a part be sent at "checks green" (its file 013), send it the moment it is verified.** 3. **Server first:** no part takes the merge slot until its server result is back. Send waiting parts as a stack in merge order, three at a time (`early_warning.py A B C`); while the Mac merges, send the next stack; keep the server busy. 4. **Green on the server: merge it, in the stack's order.** 5. **Red on the server: rerun the named test on the part merged with today's main, never on the part's own tree.** Green there: it queues. Red there: it does not take the slot. **(a) Broken only by what merged ahead of it (a conflict, a moved path, a file another part edited): a fix-up:** the builder changes only the files named in the conflict or the failing test; the verifier reads only that change; it goes straight back to the server; **until the line-fix session builds this lane (its file 009), use the shortest route the line allows and tell him what it cost.** **(b) The part's own fault: back to its builder for a round, as now.** 6. **Merge on the Mac:** the whole gate, as now, until he turns the switch that lets the server's green count; then the short remainder. 7. **Push, then GitHub's check, as now:** a second opinion, and a release needs every job green.
**Order:** the critical path first (slice E, then AD1a and AD1b back to back, then the speed figures), then whatever unblocks the most. **Each report carries one table: every part in flight and which step it is at (build, verify, server, merge, pushed), with the server's result beside it, and how many minutes the server sat idle since the last report.** His rules that stand: a key or security finding is never accepted; the owner's files are the owner's; the protected files go to him as diffs; nothing public.

## 22 November 2026: the git-identity test counts as green for the server-first rule (the owner, in chat, about 12:20 UTC)

**While the git-identity test (`test_accept_any_round.py::test_the_owners_accept_is_refused_when_the_builder_committed_after_the_verifiers_record`, line fault 12) is unfixed: a server result whose only red is that one test counts as green for the server-first rule (file 015, step 3 and 4). Any other red is handled as the algorithm says.** IS5a's result (run `1248d5f15a762da1`, the only red that test) is the first case; its merge started 12:14 on that reading.

## 22 November 2026: the stop on an account near its limit is 95%, not 90% (the owner, file 016)

**From now the stop on an account near its limit is 95%, not 90%: it replaces "under 90%" wherever the rulings and the conductor's practice say it, for both accounts (default and sol), and it replaces the return to 70% after sol's reset that he spoke of on 21 November** (so the "sol stop 90% until Sunday's reset, then 70%" and "default stays at 70%" of earlier entries are superseded by 95%). (2) **The line's own check still says 90% until the line-fix session's patch (its file 010) is applied; until then the line may refuse a start between 90% and 95%: when it does, the conductor tells him in one line and starts the part the moment the account resets or the patch is in, without asking again.** (3) **If an account reaches its real limit while a seat is running, that is a seat failure, not the part's: no round is counted, and the conductor tells him which seats stopped.** (4) The order of starts is unchanged: the critical path first.

## 22 November 2026: RL1 and SE9 start now, behind slice E and the Admin form (the owner, in chat, about 11:40 UTC)

**Start RL1 and SE9 now, behind slice E and the Admin form (AD1a, AD1b) in priority. If the line refuses because sol is at 90%, start them the moment sol resets at 12:00 without asking him again.** **Tell SE9's builder that `OspreyFlow_Core/services/api/app.py` is a collision point today and to keep its changes there as small as it can** (the SE9 brief says so, and names a new module with a thin hook as the way). At 11:44 the line answered "sol is at 91% of its seven-day limit": RL1 waits for 12:00; SE9 has no row or brief yet (a read-only scout of the saved views and the deletion paths is writing the facts first).

## 22 November 2026: a hold on merges while three patches go in (the owner, in chat, about 09:10 UTC)

**When SE8c's merge finishes, hold the next merge until he says; he has three patches to apply and will say when they are in.** Only merges are held (seats and records commits go on unless he says otherwise): DC1c, IS5a (which also needs an `add-round` line for one mypy line) and anything else verified wait.

## 22 November 2026: GitHub's `slice-line-check` job (the owner, in chat)

**If the rerun of `slice-line-check` fails again, that does not stop merging: it is the line's own test failing in its set-up (`test_accept_any_round.py::test_the_owners_accept_is_refused_when_the_builder_committed_after_the_verifiers_record`), not a product test. This is his ruling for this one test only. A release still needs GitHub green on every job.** He also asked whether the conductor's watcher reads every job of a run: **it does not** (line fault 13): until the line-fix session changes it, the conductor reads every job of main's last eight runs by hand before each merge and at each report.
