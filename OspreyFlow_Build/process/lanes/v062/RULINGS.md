# The owner's rulings for the v0.6.2 slice line

Rulings given in conversation, written here so the conductor and every seat read them (rule 11). Newest first. No
client's name or abbreviation is written in this file, nor in any message about it.

## 28 November 2026, about 12:10 UTC: the server comes back for parallel builds (the owner, in chat; replaces "no new away rounds")

1. **Away build sessions on the server, in three streams.** **No Mac builder starts for any of these parts.** Each comes into the line as before: round 1 merges `away/<ID>`, then the verifier, the server and the full gate. The owner's exception to the 23 November rule covers these branches, and an away session may build on its own stream's unmerged work.
   - **Boards** (GG4d, GG4f1, GG4f2, GG4f3): starting now, from origin/main.
   - **Cases** (GR1f1, GR1f2, GR1f3): once GR1d is on main.
   - **The Sigma spine** (GG2b, GG2d, GG2e1, GG2e2, GG2f1): once GG2a is on main.
2. **GR1d's row is cut now** from its 26 November draft, every proposal (a), with who made a view left out. Its round 1 merges `away/GR1d`, already in the main checkout. **GR1d and GG2a go as early as the queue allows:** two server streams wait for them.
3. **Merge order, by what each unblocks:**
   - WS4a and GG2c;
   - then GR4c with SE9h, SE9j and SE9k;
   - then AD1c;
   - then the page parts.
4. **A part that draws with Sigma 4 may start before WS4b and merges after it** (decision 9 allows writing early). WS4b's round 1 starts in the first slot after WS4a and GG2c land.
5. **An away drafting session re-reads the old drafts against today's main** and writes briefs for GG2b, GG2d, GG2e1, GG2e2, GG4d, GG5b, GA1b, GA1c, GA1d, GG4e1 and GG4e2. The conductor cuts rows from them. Any question of the owner's kind goes to him.
6. **Every brief written from now builds the GOV.UK page only.** A list of each default-look twin is kept for 0.7.5 (`process/lanes/v062/DEFAULT_TWINS_0.7.5.md`).
7. **Two exceptions to the line freeze:**
   - paying the owed live tests (line-fix is writing a plan);
   - the small CI model for conformance-model, briefed now as ruled on 27 November (a) (CO3g), with its CI change a diff for the owner.
8. **An approval stop on a spine part goes to the owner when it happens,** not in the batch.
9. **The 03:00 to 03:50 no-merge rule is dropped.**
10. **When fewer than 6 parts wait to merge, the conductor tells the owner,** and he puts builders back to 6.

## 28 November 2026, about 10:45 UTC: spec/08's scenario sections, no union merge (the owner, in chat)

1. **No union merge for `spec/08_ACCEPTANCE_SCENARIOS.md`.** 66 showed it is not safe there: pages edit paragraphs in place, and a union keeps both versions silently. The line is frozen.
2. **In GA1a's and GG3a's rule-5 rounds after GG3b lands, each part's new scenario section goes directly after a different named existing section, not at the end of the file**, so the two touch different lines:
   - GA1a's Scenario AC goes after Scenario TS;
   - GG3a's Scenario SP goes after Scenario BD.
   git merge-tree must show the two merge cleanly together; then they land as one train.
3. **The same rule holds for every later part that adds a scenario:** its round table (or brief) names the existing section its own section goes after.

## 28 November 2026, about 09:00 to 09:35 UTC: the fastest path to 0.7.0, and the CI split automated for today (the owner, in chat)

1. **For the rest of the build: the fastest path to 0.7.0.** The line stays frozen.
   - A line fix is made only if a red stops all merging or blocks the release.
   - It is the smallest possible, proved by a real gate first, and it goes to the owner.
   - Merges run back to back.
   - The owner's decisions are batched at about 17:00, unless something stops all merging.
2. **Builder order:** GR4c takes the first free slot, ahead of PL8b and IS4a; then GA1a, GG3a and GG3b.
3. **CO3d's split diff** (`CO3D_CONFORMANCE_SPLIT.diff`) is applied by the owner. **Today only, it is automated on his word:**
   - When the GG4b and SE9g train has landed and its records commit is in, and no merge or records commit is running, the conductor touches `/tmp/gap_for_ci` and starts nothing on main.
   - The owner's watcher checks the diff's hash, applies it and commits it.
   - `/tmp/ci_applied` is his "applied": the conductor pushes with its next records commit and carries on.
   - If `/tmp/ci_apply_failed` appears, or neither file appears within 10 minutes, the conductor carries on without the split. It runs `git status` first: a changed but uncommitted `ci.yml` is left for the owner and named in the 17:00 batch.
   - The two conformance parts' times from the first run go to the owner.

## 28 November 2026, about 07:20 UTC: the 07:00 batch answered (the owner, in chat)

1. **CO3d and the conformance-model parts: (a).** They wait until 0.7.0 is cut. Conformance reds are cleared by one rerun each (D44).
2. **CO3d's job-split CI diff is written now, for the owner to apply** (technical, his standing word). The line never writes `.github/`.
3. **The seats-test red on `d79baab`** (`test_build_seats.py::test_one_seat_per_part_at_a_time[verifier]`) gets one rerun after the conductor's push. It comes to the owner only if it is red twice.
4. **The rest of the batch is agreed:**
   - builders start at 09:00, in the order GR4c, CO3e, PL8b, IS4a, then GA1a, GG3a and GG3b;
   - the first train (GG4b, SE9g, SE9i, GG2c, WS4a, SE8g, AD1c, CO3c) is pre-checked on the server while the Mac is off, and lands as one train when the owner is back.
   - The owner closes the laptop at the conductor's "safe to close" and says "back" at about 09:00.

## 28 November 2026, about 06:05 UTC: the new plan to get the build moving (the owner, in chat; it replaces his morning rulings of a few minutes earlier)

1. **65 is reverted on main** (`bd646f1`, `git revert 087c0d7`; the owner's commit, pushed with the conductor's next records commit). The gate is as it was when SE9d merged. **"applied": merges restart now**: GR1b, GG4b, then trains of the clean parts, with server stacks at 3 jobs. **A standing rule until 0.7.0: no merge starts between 03:00 and 03:50 UTC.** (Line-fix's 68 and 69 of the earlier message are replaced by this revert and by item 3.)
2. **The line is frozen until 0.7.0 is cut.** There are no hand-backs, no new away rounds, no server verifiers or builders, and no capacity changes. Builders and verifiers run on the Mac.
3. **The `app.py:19905` citation that blocks SE9h, SE9j and SE9k: a small test-only part, cut now and merged first (GR4c).** It makes `test_govuk_pack_trends_scenario.py` find the add-item route by its text, not by a line number. It updates `away/GR4a_ADR152_DECISION10_CITATION.diff` to match, for the owner to apply. SE9h, SE9j and SE9k merge after it, with no re-citing.
4. **CO3e: (B).** It lands as (A) now: the case waits for the field's focus and for the second ageing read before ArrowUp. A separate product-fix part (**CO3f**, after CO3e) does three things, red first, with the late-ageing plant as its proof:
   - gives `AdminPlace` a stable `api`;
   - makes sure a late read never overwrites an administrator's edit;
   - checks the other Admin sections for the same shape.
5. **Refreezes for GA1a, GG3a and GG3b, as their builders proposed**, each with `test_route_pins.py` and `test_page_lists_merge.py` added to its checks. The owner's resume.tsv lines are dated 2026-11-28.
6. **Builders: the next parts in the build order, briefed on the owner's standing word (D274), keeping a night's queue.** Any question in a brief is answered (a) unless it is one of the owner's own kinds, which waits for him. Fill all four slots now.
7. **The owner's decisions are batched:** sent to him at about 07:00 and 17:00, not one at a time, unless one stops all merging.
8. `test_build_seats.py::test_one_seat_per_part_at_a_time[verifier]` (GitHub's runner red on `d79baab`) goes in line-fix's batch (from his earlier message).

## 27 November 2026, 22:24 UTC: 66b and 65 applied (on the owner's word of about 19:40, tonight only)

1. `/tmp/apply65.out` read "done: 087c0d7 committed on main (not pushed); suite: 1075 passed; early warning: 301 passed; citations: clean; install.sh not needed". So 66b (`8fbbeb4`) and 65 (`087c0d7`) count as applied. They are pushed with this records commit, and the overnight plan resumes.
2. **CO3e's item 1 waits for the morning** (the owner, about 21:30). Options (A), (B) and (C) go in full in the 06:00 report, with what each changes for a user. CO3e's builder slot goes to the next part that is not blocked.

## 27 November 2026, about 19:40 UTC: tonight's plan (the owner, in chat; tonight only where it says so)

1. **Conformance: `8e01ceb`'s conformance job is D44's one rerun.** If `test_schedule_executor` is red again, it waits for the owner in the morning. The morning report says what cancelled 11ca672's rerun job at 18:42, if that can be found.
2. **Merges:** SE9d, GR1b, GG4b, then trains of the clean parts in the planned order. The server stacks stay within 3 jobs, and `git merge-tree` runs before each merge.
3. **No merge starts after 21:00 UTC that could still be running at 22:00.** At about 22:00 the owner applies 66b and then 65, in one command on the Mac, and is offline until about 06:00.
   - While they run, no merge starts, and no seat starts that their install would stop on (`run_seat.py`).
4. **The owner's word for tonight only:**
   - **When the Mac's `/tmp/apply65.out` shows "done: … committed on main",** 66b and 65 count as applied. The conductor pushes them with its next records commit and resumes the overnight plan.
   - **If either apply stops ("stopped at …"),** it has taken itself back. The overnight plan resumes without them, and the owner hears in the morning.
5. **Overnight, no merge starts between 03:00 and 03:50 UTC** unless 65 is applied.
6. **All 4 builder slots stay busy** on parts whose briefs are on main and that are not blocked. GA1a, GG3a and GG3b take main in after 66b, and GG2a after WS4a.
7. **Anything that needs the owner's word stops and waits for the morning.**
8. **At 06:00 the conductor has ready:**
   - what merged;
   - what waits for the owner;
   - GitHub's state on main.
9. **CO3c is briefed** (`slices/CO3c.md` and its row) under the 11:15 ruling. It goes in the next records commit, so a slot has work overnight.

## 27 November 2026, about 18:20 UTC: 66s first, for speed (the owner, in chat)

1. **66s comes first:** a one-row hand-back from line-fix, carrying `scan_map.tsv`'s row for `tests/glass_trees/test_route_pins.py`. It applies in minutes. After it, the owner says "applied" and merges restart in this order:
   - SE9d;
   - GR1b;
   - GG4b;
   - then trains of the clean parts.
2. **66b and 65 go in together, in one later gap this evening.** The conductor gives the owner that gap when they are ready. 66b still carries the `shared-entries.test.ts` change, and GA1a, GG3a and GG3b wait for it.
3. **From 28 November, line fixes go in as one batch, in one overnight window.** The only exception is a fix that unblocks merging.

## 27 November 2026, about 18:05 UTC: the gap for 65, and the scan-map row (the owner, in chat)

1. **65 is applied in the gap.** Then 66b straight after it, from line-fix and shown red first. 66b carries:
   - the `scan_map.tsv` row for `tests/glass_trees/test_route_pins.py`, which 66 left out. That is why SE9d was refused at 17:59, by `slice-line-check`'s `test_the_real_scan_map_names_every_pure_walker_and_nothing_stale`;
   - the `shared-entries.test.ts` change.
2. **The owner says "applied" after both.** Only then is SE9d's merge rerun.
3. **GR1b merges on its current row, with no refreeze.** Its unused line (`GR1b refreeze 2026-11-27`) lapses tonight.
4. **`test_route_pins.py` and `test_page_lists_merge.py` join the rows only of parts that still have rounds** (GA1a, GG3a and GG3b), at their refreeze.
5. **CO3e's brief goes in the conductor's next records commit.**

## 27 November 2026, about 17:12 UTC: the page parts after 66, GA1a's question (the owner, in chat)

1. **GA1a: option (b). 66b comes first, as line-fix's hand-back before 67.**
   - Line-fix changes `shared-entries.test.ts` so that no new page edits it. The test checks that every server file importing the shared package is bundled, with no fixed list or count. It is shown red first.
   - The owner applies 66b in tonight's gap, after 65.
2. **After 66b, GA1a is refrozen with the builder's two changes:**
   - AC17 (`ask.test.ts:790`) checks that `sharedPackageEntries(server)` includes `views/askWords.ts`.
   - The ask scenario (`test_govuk_ask_scenario.py`) checks its own path appears once. Line 1022 says "not once", and a case lists the path twice.
   - Then one round takes main in, with the builder's trial resolution: main's side in `build.mjs` and the test files, and `askPage` last in `pageList.ts`.
3. **Every page part, at its refreeze, adds `test_route_pins.py` and `test_page_lists_merge.py` to its checks.**
4. **Who asked each question: there is no exception.** The page leaves it out as ruled, and the route is not changed.
5. **GG3a and GG3b take the same answer.**

## 27 November 2026, about 17:00 UTC: 11ca672's two GitHub reds, and CO3e (the owner, in chat)

1. **These two reds are not covered by the 11:15 rulings.** Those rulings cover CO3c (`rule-standards.spec.ts:21`) and the conformance jobs, and nothing else.
2. **Keyboard (job `glass-perf-a11y-keyboard`, run 46012575717):**
   - `admin.spec.ts:982` is a focus timing fault. It was green on `9e91748`, and `11ca672` is records-only.
   - The list at `:1040` lost its proved set when Playwright replaced the worker.
   - **CO3e, test-only, standing (a)** (`slices/CO3e.md`): line 982 waits for the field's focus before ArrowUp, and the list's proved set survives a worker restart, kept outside the worker's memory. Each is shown red first.
3. **Conformance (`test_schedule_executor.py::test_run_now_is_refused_while_a_run_of_the_recipe_is_going`, TimeoutError):** its job is rerun once (D44), after `ab0fe78`'s run completes. A second failure goes to the owner.
4. **GG3b** takes the same rule 5 round when a builder's slot frees.
5. **The gap for 65:** when SE9d lands, the conductor says "gap for 65". The builders already running keep going. No new seat, merge or stack starts until the owner says "applied".

## 27 November 2026, about 16:40 UTC: 66 applied, and the order after it (the owner, in chat)

1. **66 is on main as `22d967f`** (two pages built side by side merge cleanly: a union merge for the two page lists, the build finds its bundles, and no test pins the route list). The hold is over. `22d967f` is pushed with the conductor's next records commit.
2. **Rule 5, by `git merge-tree` against `22d967f`:** only a part that still conflicts gets a round, and its verifier then runs again. Against `22d967f`:
   - These still conflict: GR1b, GG4b, GA1a and GG3a. They go back to take main in now, with no round spent.
   - GG3b conflicts too, newly, in the glass-trees scenario tests and the pages tests that 66 changed. It takes the same round when a builder's slot frees.
   - GG2a conflicts in `apps/pages/package.json` and the lockfile. Its round 5 (`slices/GG2a_ROUND5_TABLE.md`) starts only after WS4a merges.
   - These apply cleanly and go to their turn as they are: SE9d, SE9g, SE9h, SE9i, SE9j, SE9k, SE8g, GG2c, WS4a and AD1c.
3. **The order:** SE9d's merge again, then GR1b. Then the server stacks and trains as planned, with SE9g and SE9h in the queue.
4. **The conductor's note to a builder taking main in after 66** (this item is not the owner's ruling): keep both sides. Where 66 made a test read the page list rather than pin a route list, the branch's new page joins the list main now reads, and no pinned list comes back.
5. **65 is still to apply.** This evening, before the overnight gates, the owner gets a gap in which no merge is running.

## 27 November 2026, about 13:45 UTC: SE9i, SE9j, SE9k, and builders during the hold (the owner, in chat)

1. **The hold for 66 is on merges only.** While main is held, the builders are kept busy (up to the dial's 4): the next unbuilt parts whose briefs are on main and that wait on no unmerged part start on their own lane branches, and verifiers run too. **Nothing merges until the owner says "applied".**
2. **SE9i: the amendment is approved as written** (`SE9I_LEGAL_BASIS_AMENDMENT.diff`, ADR-094 Amendment 2). **Round 2 now:** apply the diff on the branch exactly as approved, then write the acceptance test red first and build it as the amendment says.
3. **SE9j: approved with (a) on all five** (`SE9J_SITE_MARKING_AMENDMENT.diff`, ADR-010 Amendment 2):
   - Q1: ADR-010.
   - Q2: the marking is required at upload.
   - Q3: sites stored before read as OFFICIAL, with no re-mark route.
   - Q4: an incident marked below its cell is not placed, and A1 is narrowed to say so.
   - Q5: the case's ceiling applies.

   **Round 2 now:** apply the diff exactly as approved, then build it red first, with the tests the amendment names.
4. **Q4 (b) is a backlog part after 0.7.0** (BACKLOG.md row 49): `site_cell` gets its own marking in both analytics adapters, so lower incidents can be placed again.
5. **The `unit-1` fault in `recipes/site_grid.yaml` is a security fault: new part SE9k** (a grid's cells take the site's owning unit and originator). It is built red first and cut before RL2 (`slices/SE9k.md`).
6. **Line fault 11** (a planned stop is pushed six times and recorded red) goes to line-fix after its vitest change.
7. SE9i and SE9j's round 2 runs on the owner's `clear-stop` lines in resume.tsv.

## 27 November 2026, about 12:55 UTC: the server's reds since 10:14 (the owner, in chat)

1. **The cause:** CPU starvation from capacity option D. Vitest ignores the job's CPU share.
2. **The server is back on its earlier settings:** 3 jobs at 400% and 12G (lanes merger, platform-b and rules-b), which passed. Hand-back 64's fixes stay.
3. **GG4c's and SE9d's reds from those runs are the server's, not theirs.** No round is counted against either part.
4. **After hand-back 66 is applied,** server stacks may be sent again, and trains run as planned. A second stack goes beside the first only when both fit within the 3 jobs.
5. **Both added lines are agreed** (the owner, about 13:00 UTC): no round is counted against GG4c or SE9d for the server's reds, and a second stack goes beside the first only if both fit within the 3 jobs. There will be more room once line-fix's vitest change lets option D return.
6. **Rule 5 after 66, tightened:** it applies only to a verified part that conflicts with main because another part merged first. That part gets one round, and its verifier runs again. **A part that applies cleanly goes to its turn without taking main in.** The rest of the plan after "applied" is agreed as written.

## 27 November 2026, about 11:15 UTC: GitHub's reds and WS4b's CI measurement (the owner, in chat)

1. **CO3c: yes** (test-only, standing (a)): `rule-standards.spec.ts:21` waits for the button before pressing Tab.
2. **conformance-model: (a).** CI's job alone runs a small pinned model, so CI checks the pipeline. The deployment model's golden-set recall is measured on the server's GPU as release evidence. One small part each. The CI change is a diff, technical, approved on the owner's standing word.
3. **conformance: CO3d yes.** Each named test runs 20 times on the server, and real causes are fixed red first. The job is split in two (a CI diff, technical, on the owner's standing word).
4. **WS4b's CI measurement: (d), not a push.** After round 1, its perf suite is measured on the server under GitHub's runner shape (4 CPUs, the same commands, software rendering), three runs. The owner runs the Mac once. Main's CI confirms after the merge. ADR-142 decision 6 stands: no lane branch is pushed.

## 27 November 2026, about 09:55 UTC: GG2a's last round (the owner, in chat)

GG2a conflicts with main in `apps/pages/package.json` and `package-lock.json`, after GG5a. Rule 5 covers it, on the conductor's word. **It is not sent back now.**

**After WS4a merges, GG2a gets one round that does both:**
- **It takes main in.** Both sides' dependencies are kept, and the lockfile is regenerated with npm, never hand-merged.
- **It writes the version-window entry and I20's third test** (D272, D286).

Then its verifier, the server and the full gate run as usual (`slices/GG2a_ROUND5_TABLE.md`).

## 27 November 2026, about 09:50 UTC: the way to hand-back 66 (the owner, in chat)

1. **No hold for 66 now.**
2. **If the stack GG5a, GG4c, SE9d comes back green:**
   - Run the GG4c and SE9d train first.
   - Straight after it lands, before any other merge, train, records commit or new server stack, tell the owner **"ready for 66"**.
   - Hold until the owner says "applied".
3. **If the stack comes back red:** tell the owner **"ready for 66"** at once, and hold.
4. **After 66:** each verified page part takes main in once (rule 5, on the conductor's word).

## 27 November 2026, after 09:40 UTC: the overnight drafts' owner questions answered (the owner, in chat, all as the build adviser recommended)

1. **GR1f1 Q8 (a)** for the page. **Cut a Conduit security part before RL2** that audits the access and datasets reads (SE9h).
2. **GG3e Q3 (a):** the file is streamed through the forwarder's own translation, in one shared function. The anti-forgery and forwarder tests stay unchanged, and stay green with plants.
3. **GG3e Q5b (a)** for the page. **Cut a Conduit part before RL2** that stores the legal basis on the Document, with its amendment as a diff (SE9i).
4. **GG4f2 Q3b (a): a Conduit security part first** (SE9g). `choose_picture` refuses, and `picture_file` answers as none, any Document whose reference is not one of the four image types. Red first. **GG4f2 waits for it.**
5. **GG4f3 Q8b:** the page never names the deployment's highest marking. It says "above the highest marking this deployment holds", permanently.
6. **GG5c Q2 (a):** the conformance case comes first, on both adapters. **If it is red, stop:** the fix is a Vault security part, never a page filter.
7. **GG5e1:**
   - **Q1 (a):** its own page route, with the right checked before any byte and the page service's cap. No forwarder widening.
   - **Q2 (a):** `GET /v1/investigations/{id}/sites` comes as an amendment diff for the owner's approval, with the access case first.
   - **Q3 (a):** built as the routes are. **Cut a Conduit security part before RL2** giving a site a marking (SE9j).
8. **GG5e2 Q1 (a):** turn to the plan, north up, turn by 15 degrees, tilt 0, 30, 60 and flat. Written into `spec/02` §3.5 first.
9. **GG2g Q8 (a):** drawn items are read-only on the canvas, and *Edit on board* is offered only to the item's author. The ADR-143 C15 amendment comes as a diff.
10. **Everything else in those drafts stays standing (a).**

## 27 November 2026, about 09:40 UTC: WS4b's order and its two speed items (the owner, in chat)

The plan and order are agreed: **the GG2c, WS4a, SE8g train, then WS4b.** Two speed items are planned inside WS4b, **never accepted narrower:**

1. **The sweep** (3.5 to 3.8 s against 3 s on the server):
   - Round 1 measures it again with picking ratio 4.
   - The budget is judged on CI's runner (three runs) and on the owner's Mac once (D280 Q6).
   - After round 1, the conductor gives the owner CI's figures, and the owner runs the Mac measurement.
2. **`community-links.spec.ts` is still red:** if it is still red after round 1, **round 2 takes it** (WS4b-perf Q8).
3. **If the sweep still misses on CI after ratio 4, stop** and bring the owner the figures, with WS4c (ADR-119's lever) as the option. **No gate changes.**

## 27 November 2026, after 09:17 UTC: WS4b's look accepted (D286; the owner, in chat)

1. **The look is accepted as now drawn on `away/WS4b-look`:** the export carries every link; link labels are written beside the line as Sigma 3 did; everything else is Sigma 4's own drawing.
2. **WS4b comes into the line when WS4b-speed's report has its Q6 figures.** Its round 1 merges `away/WS4b`, `away/WS4b-perf`, `away/WS4b-look` and `away/WS4b-speed`.
3. **In that slice:**
   - **The canvas-look references** are remade on this look with WS4a's command, under the reason "Sigma 4's look, accepted by the owner on 27 November 2026".
   - **The ADR-152 decision 9 amendment and the WebGL 2 requirement (D280 Q2)** are written as diffs for the owner's approval **before it merges.**
4. **Q3:** `pickingDownSizingRatio` is set to **4**. WS4b-speed's measurement found it better at pointing than 2, and faster. It needs a test on the smallest node at its edge.

## 27 November 2026, after 09:15 UTC: server done (the owner, in chat)

1. **The server's early warning now runs hand-back 64** (`bafa9544`: timing budgets are left to the Mac).
   - It runs with `capacity.json` option D: 4 jobs, 300%, 10G, 3 workers, and two stacks within 4 jobs.
   - The slice cap is 1200% and 40G.
   - The build account's runner is `6bec54ee`, the seat-start fix.
2. **The 09:01 stack (GG5a, GG4c, SE9d) was stopped by the owner** with no verdict, and is sent again.
3. **From now on:**
   - Send stacks that merge cleanly together.
   - Land each server-green stack as one train.
   - Run a second stack beside the first when the parts fit within 4 jobs.
4. **Report:** parts landed per gate, and any server run ended for memory.

## 27 November 2026, about 09:20 UTC: GR1b's numbers, GG4b may merge, the server (the owner, in chat)

1. **GR1b: (a).**
   - Its scenario rows CS16 to CS33 become CS27 to CS44; main keeps CS16 to CS26.
   - The owner's refreeze line is in, for `cases-new.test.ts`'s renumbering alone, with a second send-back line.
   - The line fault (a builder ending on a question was read as green) goes to line-fix.
2. **GG4b:** the builder's three spec edits stay, since they restate what the owner approved:
   - `01_DOMAIN_MODEL.md` §2.2d;
   - `03_CONDUIT_MIDDLEWARE.md`, the PATCH 422 `no_source` and the withholding rule;
   - `08_ACCEPTANCE_SCENARIOS.md` BD3 and BD11.
   - **GG4b may merge. "Never accepted narrower" still holds.**
3. **The server:** the owner reinstalls its early warning for 64 as soon as it is free. When the stack now running ends, **no new server stack is sent until the owner says "server done"** (about 15 minutes). Single merges on the Mac go on meanwhile. The conductor tells the owner when the server is free.

## 27 November 2026, after 06:40 UTC: GR1b; rule 5 widened to any file (the owner, in chat)

1. **GR1b:** the owner's send-back line is in. It is used **only after GR1e lands**, for GR1b to take main in (the case page's own code). One round; its verifier then checks it again.
2. **Rule 5, widened from now until RL2:** a verified part that conflicts with main **only because another part merged first** may go back to take main in **on the conductor's own word**.
   - One round, any file.
   - No round is counted against it, if it is under its limit.
   - Its verifier checks it again, and the full gate runs.
   - **If that round's verifier finds anything beyond taking main in, or the part is at its round limit, it goes to the owner.**
   - Each use is listed in the report.

## 27 November 2026, about 06:35 UTC: stacks that merge together, and trains (the owner, in chat)

Since the train was switched on (26 November, 17:06), every merge has been single, and 12 verified parts are queued. From now:

1. **Before sending a server stack,** check with `git merge-tree` that its parts merge cleanly together onto main. Send only such stacks.
2. **Land every server-green stack as one train** (`merge_slice.py train A B C`).
3. **Where shared-list conflicts block that,** send those parts back to take main in together, then stack them.
4. **Report how many parts each gate landed.**
5. SE9d's merge is run again, and GR1e's rerun goes ahead as planned.

## 27 November 2026, about 06:05 UTC: the overnight drafts; GG5a's two diffs (the owner, in chat)

1. **The overnight drafts** (`drafts/2026-11-27` on server-backup) are taken in under the owner's standing (a) (D274). The drafts are GR1f1-3, GG3c, GG3d1-2, GG3e, GG2f1-2, GG2g, GG4f1-3, GG4g, GG4h, GG4i1-4, GG5c, GG5d, GG5e1-2, GG5f and GA1e.
   - They are copied into `slices/` and queued in the chain plan's order, behind what is already queued.
   - Every question marked as the owner's goes in the next report, for the build adviser.
   - **A slice whose own question is the owner's does not start until the owner answers it.**
2. **GG5a: both diffs approved.**
   - The ADR-152 decision 8 diff (`GG5a_ADR152_DECISION8_RUN.diff`: the run's facts, no decision changed).
   - The CI patch (`apps/pages/test/csp/ci-wiring.patch`, the `pages-csp` job), on the owner's standing word for technical changes.
   - Both are prepared as diffs for the owner to apply.

## 27 November 2026, after 05:50 UTC: WS4b's speed (D282; the owner, in chat, as the build adviser recommended)

1. **Q1:** the label-side fix stays.
2. **Q2:** a slice stops Sigma 4's full reducer re-run at each change of graph state, with a refresh when the camera stops. It includes a test that fails if Sigma's private field changes.
3. **Q3:** measure hover and click on the smallest node at picking ratios 4 and 8 before choosing.
4. **Q4:** link picking comes only from the neighbourhood band in. Keyboard link selection is unchanged.
5. **Q5:** a chunked texture refresh for `@sigma/node-image` 4.
6. **Q6:** after Q5, measure the first-frame gate again, three runs. The gate itself does not change.
7. **Q7:** the Conduit's expansion figure stands; no new gate.
8. **Q8:** community links are judged again after Q2 and Q4.
9. **Where it is built:** away on the server as `away/WS4b-speed`, beside the look round (`away/WS4b-look`). When both report, WS4b's round 1 in the line merges both branches. **WS4b does not start in the line before then.**

## 27 November 2026, about 05:50 UTC: rule 5 widened; GR1e (the owner, in chat)

1. **Rule 5 widened, (a).** Two more files count as shared, append-only lists: `apps/pages/scripts/build.mjs`'s entry list of page word files, and the test pins of a page's tab order (such as `test/govuk/casesServer.ts`). GG3a and GR1b go back to take main in on the conductor's word, no round spent.
2. **GR1e:** its 03:40 refusal was the merge tree's `.venv` losing pydantic partway through the gate. Its merge is run again as planned. **If it happens again, stop and tell the owner**; line-fix is asked to look for the cause.
3. WS4b's speed rulings follow from the owner separately; the look round runs away on the server (`away/WS4b-look`).

## 27 November 2026, after 03:21 UTC: WS4b's look (D281; the owner, in chat)

The owner viewed the comparison.

1. **Export: not accepted.** The link lines are missing from the export, which is a fault.
2. **Hover and selected link: not accepted.** Link labels must be written beside the line as Sigma 3 wrote them, through a local 2D edge-label layer on Sigma 4.
3. **Every other scene keeps Sigma 4's drawing.**
4. **WS4b's look round is building away on the server** (`away/WS4b-look`). **WS4b does not start in the line** until that round reports and the owner has seen the three scenes again.
5. WS4b's speed questions go to the owner separately; they are not the conductor's.

## 27 November 2026, 03:21 UTC: the morning answers (the owner, in chat)

1. **GG4b (security):** its ADR-143 amendment (`lane/slice-GG4b`, `92605bf`) is **approved with (a) on all five**:
   - **Q1:** neither note nor document goes to a reader who cannot read the document. The three small front-end changes are included: the GOV.UK board page accepts such an item; the React inspector's sentence; the React drawing form.
   - **Q2:** editing an old item must add a note.
   - **Q3:** promotion requires a note, whoever asks.
   - **Q4:** at most one batched document read per answer.
   - **Q5:** document reads do not grow with the number of items, and the live step meets `spec/02` §5.
   - The owner's clear-stop line is in (`resume.tsv`, 27 November).
2. **SE9d:** the refreeze line is in, for its corrected `schemas-check` command (`PY=` its acceptance environment, as GG4b's and GG4j's).
3. **GG5a:** WebKit is installed in the shared cache; the clear-stop line is in.
4. **RM1a:** the send-back line is in, for one more take-main-in. **It merges straight after, before any other page part.**
5. **Standing, from now until RL2:** a verified part that conflicts with main **only** in the shared GOV.UK lists may go back to take main in on the conductor's own word, with no round spent. The shared lists are `spec/08`, the scenario tests, `pageList`, routes and pins. Anything else still goes to the owner.

## 26 November 2026, 20:24 UTC: overnight, 26 to 27 November (the owner, in chat; away 21:30 to about 07:30)

1. Keep the line moving: starts, verifiers on the Mac, merges, and trains of up to three where the server has tested a stack. Records commits only straight after a merge or train.
2. **GG5a** (away/GG5a) comes in like GR1a. Its question 1 (the pmtiles 4.5.0 exact pin, the workspace's own version) is approved on the owner's standing word (D274, technical). Its CI patch and its ADR-152 decision 8 diff wait for the owner in the morning; it may merge without them.
3. **GR1d and WS4b wait for the owner's answers in the morning; neither starts.** WS4b's speed is measured on the server overnight (away/WS4b-perf).
4. Anything that is the owner's (security, keys, ADRs, a stop at a round limit) goes to the top of a 07:00 report; never accepted narrower; no switch of the owner's is changed. Something that blocks a slice stops that slice only; the line moves on.
5. The 07:00 report: merges overnight, what is verified and waiting, what stopped and why, and what each away report asks of the owner.

## 26 November 2026, 20:13 UTC: RM1a's last round; verifiers back on the Mac (the owner, in chat)

- **The dial line is out:** verifiers run on the Mac again. GG3a's failed server run (`361735d22464d46a`) leaves it at verifying, round 1, with no round spent.
- **RM1a:** the owner's send-back line is for its conflicts with main after GR1a's and GR4a's merges (the shared page lists, routes, scenario and pins: append-only, both sides kept, main's first). **One round only: round 8 of 8.** If its verifier then finds anything that is not from taking main in, the conductor stops it for the owner rather than spend another round.

## 26 November 2026, 16:08 UTC: this evening's order (B) (the owner, in chat)

When the server stack reports, **GR1a merges alone** and its five parts start. **Then merges hold for line-fix's combined apply** (62, 63, 58, 59, 60; about 50 minutes, the owner runs it). After "applied" the owner switches the merge train on, and the conductor runs **one train of SE9d, SE9e and SE9f on the Mac's whole gate** (`gate_on_build` stays off), watched, reporting each step. **Then a second train: RM1a, CO3b, GG2c**, if verified. Records commits only straight after each merge or train.

## 26 November 2026, 15:40 UTC: the plan agreed; the merge train (the owner, in chat)

The conductor's plan is agreed: GR1a, SE9d and SE9e merge back to back; then the five starts; the next stack is RM1a, SE9f and CO3b; then GG2c and WS4a. **GG2c Q3:** the conductor runs its integration test under `stack_lease.sh` before its merge. **Proposal 2 is line-fix's hand-back 60 (the merge train),** in tonight's combined apply; after it lands, the train takes the server's tested stack (main plus A, B, C) as one gate run. The conductor tells line-fix what 60 needs (`LINE_FIX_NOTES_2026-11-26.md`). **Proposal 1 (two server runs side by side) goes to line-fix now.**

## 26 November 2026, 15:38 UTC: GG2c's answers; records after merges (the owner, in chat)

- **GG2c:** Q1, before-equals-after on one machine is accepted for a move with behaviour unchanged; GitHub's run is the green check. Q2, `OSPREY_PORTS_SLOT=0` inside a D246 namespace is accepted. Q3, the integration test runs once against a leased stack before the merge; the conductor says if the owner must run it.
- **Records commits** (scan rows and every other) are held until straight after a merge, so no pending server green is voided.
- The owner's second SE8g clear-stop line is in.

## 26 November 2026, 14:50 UTC: SE8g (a) (the owner, in chat)

SE8g grows by (a): `await client.create_database_if_absent()` in the four helpers its guard found (`test_assessment_routes.py`, `test_export_routes.py`, `test_statelessness.py`), test setup only, nothing loosened. The owner's clear-stop line is in.

## 26 November 2026, 14:44 UTC: GG2c in; GG5a and GR1d away (the owner, in chat)

`away/GG2c` comes in like GR1a (round 1 merges the branch); by the owner's ruling of 10:45 (D268) GG2c may merge before WS4b. **GG5a (from origin/main) and GR1d (from away/GR1a) are away rounds on the server until 22:00:** no line builder starts for them; each comes in when its report appears.

## 26 November 2026, 13:26 UTC: the 62 hold cancelled; hand-backs together at about 17:30 (the owner, in chat)

The hold for hand-back 62 is cancelled. GR4a merges, and merges and starts carry on as normal all afternoon. **No hand-back is applied until about 17:30 UTC**, when the owner applies 62, 63, 58, 59 and 60 together, with a warning first. **AD1c waits for 63** (its `lists.tsv` row) until then.

## 26 November 2026, about 12:40 UTC: SE9e (a); the extract route; GG2a's add-round (the owner, in chat)

- **SE9e: (a).** Refuse every recipe binding of `object_ref` and `media_kind` on a Document, at validation and at load; only the engine's own writes set them; case 3 becomes "refused" (the owner's word). The owner's SE9e clear-stop line is in.
- **The ingest extract route** (a caller-chosen Document whose `properties_override` sets `object_ref`) is cut as its own security part before RL2: **SE9f**.
- **GG2a:** the owner's add-round line is in; it is used after WS4a merges and GG2a takes main in (the version-window entry and I20's third test). If WS4a does not merge today, the conductor says so tomorrow and the owner writes a new dated line.

## 26 November 2026, about 12:20 UTC: GG2a's Mac figures; Sigma 4 (the owner, in chat)

The owner's Mac run (`~/gg2a-mac-gpu.jsonl`, 3 runs, Apple M3 Pro GPU, all passed): first frame 2,877 / 2,646 / 2,954 ms against 30,000; sweep 16.5 / 17.0 / 16.5 ms a frame; expansion of 500 nodes 555 / 602 / 684 ms against the Mac's 800. **Carry on with Sigma 4; no fallback.** GG2a merges after its verifier and a server green, writing the version-window entry and I20's third test (WS4a Q1 and Q5). Merges and starts resume.

## 26 November 2026, 12:15 UTC: the owner's answers (security, WS4a, GR1e) (the owner, in chat)

(The conductor's earlier headings today were not read from the clock and run about two hours ahead of UTC; from here every time is `date -u`.)

- **GG3b Q1:** yes: a Conduit security part for the document-reader route's `sender_id`, `recipient_id` and `edge_id`, **before RL2**. **GG3b Q8:** (i) a PDF is served as a download (`Content-Disposition: attachment`), never shown in the page; (ii) yes, a security part: a recipe binds `object_ref` on a Document only to a file of the same dataset; (iii) the PID pack's picture references: a backlog bug. **GG4j:** a refusal names only the capped ceiling the board already sent that reader, never the real one. C040 noted.
- **WS4a:** Q1 (a); Q2 (b), CI's reference set first, as a diff to the owner; Q3 (a), the same "ready" moment for both front ends in 0.7.0, **which replaces the 10:35 GG2a Q2 (a): GG2a needs no extra round**; Q4 (a) once WS4a adds a test for the release-local diff; Q5 with GG2a's merge. **Start WS4a.**
- **GR1e:** GR1a Q1 is (a), the query form (ruled at 10:30). GR1e is accepted as built; its Q1 and Q2 (Conduit parts) go to the backlog after RL2.
- **GG2a's Mac run:** the owner runs the command once at a quiet moment, and first says "quiet window". From then until "done", the conductor holds merges and the early warning's Mac-side steps.

## 26 November 2026, about 13:40 UTC: "applied" (61); away rounds in; GG4b ruled (the owner, in chat)

- **Hand-back 61 is on main (`b72aaba`):** the citation red and the beat race are fixed. Starts and merges resume in the conductor's order.
- **Away branches on the Mac:** `away/GR1e`, `away/GG3b` and `away/WS4a` each come into the line like GR1a (round 1 merges the branch). **WS4a's questions go to the owner first; its start is held until the owner answers.** `away/GG4b` stopped at the owner's D268 stop before any code, so it has nothing to merge. `away/live-A` is evidence only. GG2c is still on the server.
- **AD1c's `lists.tsv` row:** line-fix hands it in as a small hand-back after 62. If it qualifies for the conductor's apply-handback, the conductor applies it.
- **GG4b (security), after its away stop:** questions 2 and 4 become **(b)**: on every read path that sends a drawn item, the cited document is re-read with the reader's principal; there is no recorded handling and no sweep. **A budget case for the working set with drawn items** is part of its table. **GG4b is built in the line, not away**, and is never accepted narrower. **Its ADR-143 amendment diff comes first, for the owner's approval.**
- **The ceiling (GG4b question 5 (a)) is cut now as its own security slice.**
- **C040 (re-marks outside the edit route) is raised to a security row, before RL2.**

## 26 November 2026, about 11:10 UTC: five away rounds; starts wait for 61 (the owner, in chat)

Away on the server: GG2c, GR1e, and from about 10:45 GG4b, WS4a and GG3b. **No line builder starts for these five:** each comes in like GR1a when its report appears (round 1 merges the away branch). The line takes SE8g, AD1c, GR1a, GG4a, GA1a, GG3a, GR1b and GG4c, in that order, **once 61 lands.**

## 26 November 2026, about 10:35 UTC: the adviser's batch, all as recommended (the owner, in chat)

- **Security:** GG4a drops its source column until GG4b. **GG4b is cut now as a security part (SE7c's shape):** every proposal (a); its ADR-143 amendment comes as a diff for the owner's approval before merge; never accepted narrower.
- **GG2a:** carry on with Sigma 4; the owner's Mac measurement decides (the conductor gives the one command today). Q2 (a), the stricter first-frame end. Q3: the Mac's 800 ms alone for 0.7.0; a CI expansion gate goes to the backlog.
- **The Matrix is GG2d's.** Decision 9: one exception, GG2c may merge before WS4b; all else waits. **Early starts:** GG3b, GA1a, and GG3a after GR1a; WS4a beside GG2a; not GG5b.
- **Who made it** (GR1a Q2, GG4a Q2, GR1d Q4): left out for 0.7.0; names later via `display_names`, a backlog part.
- GG3b Q6 (a): a browser-runnable type is a stop. GA1b: Editor (fix `ASK_MODEL`'s comment); Q3 (a): a front-proxy timeout under 16 minutes is a stop. GG2e Q2 (a): a parity line. GG5b Q4b: an ADR-152 Amendment 2 diff adding Noto Sans for map glyphs only. GG4c Q5 (a): unshare goes to the backlog.
- **Live step:** a small part adds ClickHouse and Azurite (and Keycloak if needed) to its stack; line-fix makes it pay group by group after 61.
- **Everything else (a):** GR1a Q3 to Q5; GG4a Q3, Q5, Q6 and Q7; every non-owner question in the 26 November drafts; the 25 November drafts with the 26th's corrections. AD4 after RL2. Draft PL8b.
- **Order through the line:** SE8g, AD1c, GR1a (away branch), GG4a (away branch, source column dropped in its round), GG4b, WS4a, GG3b, GA1a, GG3a, GR1b, GG4c; GG2c and GR1e when their away rounds report. **Merges wait for 61** (the citation red).

## 26 November 2026, about 08:30 UTC: "applied" (the owner, in chat)

Hand-backs 55 (`69852bf`), 56 (`db97a76`) and 57 (`d5d62a3`) are on main; starts and merges resume. **Until hand-back 61 is applied,** a merge refused at `slice-line-check` by the beat race counts as "refused by another test": the conductor reruns it, with no send-back.

## 26 November 2026, about 05:40 UTC: the morning rulings (the owner, in chat)

**GR4a:** clear-stop (the stop's "token" was a false flag); round 3 on `slices/GR4a_ROUND3_TABLE.md`: the board page gets its own `FUNCTIONS.yaml` row and id; both pages stay. **RM1a:** clear-stop; its refusal came from two line faults (`server-rerun` runs a vitest name under pytest in a shell string, broken by the apostrophe in "§5's"; a newer green server run on the same tip was ignored), which go to line-fix. **GG2a, question 4, (a):** one more step (round 4, `slices/GG2a_ROUND4_TABLE.md`) adds an opt-in switch opening a GPU-backed Chromium, records the WebGL renderer with every figure and refuses a software one under the switch, red first; CI's gate unchanged; then the conductor tells the owner what to run on the Mac. **away/ci-reds** found SE8f's cause independently, and that the Mac's merge gate never runs the conformance-only files; the conductor proposes how the line catches a break in them before GitHub does, for the owner's ruling. **GG4a's away round** is done (7 questions, one a rule-3 stop on a drawn item's source document); its questions go in today's rulings batch once the owner has fetched it. **A gap with no seat running** for line-fix's hand-backs 54 to 57 (about two hours): no new start, no merge and no records commit until the owner says "applied".

## 25 November 2026, about 19:50 UTC: "take your recommended routes" (the owner, in chat)

**PL4h: option (a)** (D225 item 3's structural round): every test in the two copy files that walks or parses gets an explicit, explained timeout, the plant tests included; nothing cached, nothing moved out of `sourceFiles`; the plant stands. Round 4 on `slices/PL4h_ROUND4_TABLE.md`. **AD1c: round 11 on the conductor's table** (already ruled at about 16:20). Both wait for the owner's add-round lines.

## 25 November 2026, about 16:25 UTC: GR1a as an away round (the owner, in chat)

**GR1a runs as an away round on the server now**, on every proposal (a) of its draft (`slices/drafts_2026-11-25/GR1a.md`) and the owner's exception to start before GG2b. **The conductor does not start GR1 in the line:** it enters through its away branch, like GR4a, after the owner fetches it (its round 1 merges `away/GR1a`).

## 25 November 2026, about 16:20 UTC: AD1c round 11; SE7c, GG2a and the drafts (the owner, in chat)

**AD1c: yes, Superset's metadata database counts under "each database the render makes"**: it is on the same server, made by the deployment's own code. **Round 11 on the conductor's table:** one census of every database the deployment makes on that server, each closed the same way, so a new one cannot be missed; plus tests for the EXECUTE revoke's refusal words and for silence on a healthy run. His third add-round line today.
**Away rounds:** GR4a started (round 1 merges `away/GR4a`); **SE7c**, a security part for `away/access-fix` (his word extends D247's exception to it; its round 1 merges it; never accepted narrower; judged by the verifier, the server and the full gate); **GG2a**'s row and round-1 brief (round 1 merges `away/GG2a`; its merge waits for his Mac's own measurement, the 18 November ruling); **the drafts of `drafts/2026-11-25`** copied into `slices/drafts_2026-11-25/` for his rulings tonight; the away copy-tests job never started, PL4h covers it. **PL8a's merge need not wait for 19:30.**

## 25 November 2026, about 16:10 UTC: I21's rename approved; apply_53 tonight (the owner, in chat)

**`approved: ADR152_I21_ROW 2b32bafb`.** **apply_53 stopped at 14:19 on the early warning's suite** (`test_lists.py::test_the_lists_match_this_repository`, failing on main since PL7f merged: its new `test_page_addresses_caddy.py` is not in the early warning's lists; not 53's fault). The demo-server session is fixing the lists; **the owner retries apply_53 tonight once that is on main. The conductor keeps moving old tables aside until then.**

## 25 November 2026, about 13:55 UTC: GR4a's away round and its four questions (the owner, in chat)

**GR4a's away round is done** (its table green; its report in `away/GR4a_AWAY_REPORT.md` on the branch); the owner fetched it as the local branch `away/GR4a`. **His answers:** (1) keep `/packs/trends?case=…&pack=…`; (2) keep the one shared withheld sentence, never a placeholder (rule 3); (3) rename I21's test in the decision log (the conductor proposes the diff, `ADR152_I21_ROW`, for his approval); (4) confirmed: an Editor sees the working pack, everyone else the newest published version. **GR4a starts as D247 says (round 1 merges `away/GR4a`) first thing at 19:30, not before:** apply_53 is running and the Mac goes offline at 14:30.

## 25 November 2026, about 13:30 UTC: AD1c's PUBLIC defaults, option (a) (the owner, in chat)

**AD1c (a), one more round closing both:** each database the render makes takes CONNECT and TEMPORARY from PUBLIC and grants CONNECT to its own role(s) alone (`litellm` to the gateway's role and the reader); EXECUTE on functions taken from PUBLIC in `litellm`; planted faults refused by the database itself; on a managed server a revoke the login may not make is said in words and never stops the gateway; **and the reader's verifier command run in the pinned image on the server's container checks** (patch 52). Amendment 15 decision 1 stands as written. **Point 2, amended about 13:40 UTC:** do not wait on the server's container checks (patch 52's server half is installed tonight); **use D234's pattern**: exempt in `tests/local_docker_guard.py` exactly this test's one command (`docker run --rm --network none`, the pinned `postgres:16.4` image), named by the test, a planted second command refused; it moves to the server's checks when 52 is live and the exemption comes out. **Planted faults for every revoke.**

## 25 November 2026, about 12:40 UTC: GR3b's three questions; hand-back 53; GG2a's cut-off (the owner, in chat)

**GR3b:** (a) **one part per route**: the report route first (GR3b), then AD3b and RM1b as each page's next part; (b) **GR3a merges first**; (c) **the drift check** (goldens against what the route answers now) **runs in `make test` on every merge**; **regenerating the goldens is a separate target a builder runs on purpose, never automatic.** GR3b is cut after GR3a merges.
**The two line faults** (`round_table` returning a part's oldest table; the board showing a past-dated `resume.tsv` line as waiting) **are line-fix's hand-back 53**, which the owner applies tonight; **the conductor keeps its workaround** (superseded tables moved to `slices/aside/`) until then.
**GG2a's cut-off moves to 13:30** (the owner back at about 13:30): its away round runs only if PL7f has merged by then.

## 25 November 2026, about 12:25 UTC: every database role's password as a client-made verifier (the owner, in chat)

**Option (a): a small part of its own (AD1e):** a client-made SCRAM-SHA-256 verifier for **every role the render's database steps set** (the gateway's `litellm`, Keycloak's, and any other), so no plaintext password is ever in SQL text sent to PostgreSQL; **shown red first with `log_statement = 'all'`**, using AD1c's approach. **A security finding: never accepted narrower.** **It starts after AD1c merges.**

## 25 November 2026, about 11:45 UTC: GR3a back for I15's test (the owner, in chat)

**GR3a: sent back for the I15 test under its exact name** (`test_the_dashboard_page_answers_a_reader_without_read_reports_as_a_missing_report`); **an access rule is not accepted narrower**, even on the standing line. One row, no round beyond that one.

## 25 November 2026, about 08:10 UTC: PL8a round 13; apply_52 tonight (the owner, in chat)

**PL8a:** one more round on its structural table (his third add-round line today), the table renamed ROUND13 (round 12's builder was shown round 10's table by the line's `round_table` fault, so it did row 1 only). The stale `PL8a accept 2026-11-24` line deleted by the owner. **apply_52 (line-fix 52) is not applied in this gap: the conductor keeps merging; the owner applies it tonight.**

## 25 November 2026, morning: PL8a's structural round, PL7f's reserve, ruling 6 withdrawn (the owner, in chat, about 07:45 UTC)

1. **PL8a: option (a), one structural round 12** (D225 item 3): Home forgets the stored size; a size is written only when it is the size the analyst's own action asked for, never a clamped value; one test over every panel action × bound × starting state. Its add-round line is in.
2. **PL7f: two add-round lines are in resume.tsv in reserve**, so it has rounds to spare before GG2a's 13:00 cut-off; **the conductor uses them only if a verifier finds more** at its rounds limit.
3. **Ruling 6 (PL11b) is withdrawn:** the licence register is for what the code gate cannot see, and `make licence-check` already covers Sigma, graphology and MapLibre. **The conductor's correction to GG2a's item 4 and case 9 stands.**

## 25 November 2026: the away rounds, AD1c, GR4a, GG2a and the licence register (the owner, in chat, about 06:30 UTC)

1. **PL8a:** the add-round line for today; round 11 on its table.
2. **Away rounds (D246; GR4a and GG2a only): one exception to the 23 November rule.** A builder's round 1 may merge a branch `away/<ID>` that the owner fetches from server-backup into this checkout. **No other branch, and no other part.** The owner fetches it on his return.
3. **AD1c, option (c):** a small part (AD1d) teaches `test-file-coverage-check` that a test starting its own private database (`initdb` in a temporary folder) is not live-service, red first. **Then AD1c imports `asyncpg` plainly; no import is ever written to miss a check.**
4. **GR4a:** 1(a) read-only first; 2(a) the pack's snapshots with their counted-on date; 3(a) whoever may read the pack now, and 404 otherwise (the same as a pack that does not exist); 4(a) "Trends shown together" at `/packs/{pack_id}/trends`; 5 a new spec/08 scenario first. **ADR-152 decision 10's citation is corrected with GR4a's spec changes.**
5. **GG2a:** proposals 1(a) to 6(a) (a module of its own served only by the perf harness; the workspace's CI gate, §5's own numbers measured on the owner's Mac on his return; the fixture moved to `glass-shared`; the newest Sigma 4.x at least 14 days old, pinned exactly, with its register rows; stop and bring the figures if CI misses; the register's missing rows a separate part). **It runs as an away round only if PL7f has merged by 13:00.**
6. **The licence register:** a small part (PL11b) adds the missing rows (`sigma`, `@sigma/*`, `graphology`, `maplibre-gl`), before RL2. **Held, not cut (the conductor, 25 November 2026, about 06:35 UTC): the finding behind it was the conductor's error.** `spec/LICENCE_REGISTER.yaml` is only for what the code gate does not see (weights, map data, fonts, base images: its header and `spec/00` §7); the drawing libraries are code and pass `make licence-check`'s Node half (`license-checker` over the installed packages) against §7's allowlist (MIT, BSD-3-Clause). The owner was told and asked to confirm the ruling is withdrawn. GG2a's item 4 and case 9 were corrected the same way.

## 25 November 2026: GR3a's structural fix, (A)+(B) (the owner, in chat, about 05:30 UTC)

**GR3a was stopped under D225 item 3** (rounds 4, 5 and 6 found the same kind: the page drifting from what the real route sends, hidden by a hand-written fixture). **(A), GR3a's round 7:** a strict reader (a body missing a field the generated `MonitoringFigures`/`ReportFigures` types require is the page's "could not be read" answer, never a zero; a test case per required field, made from the type's own field list); a field census (a test walks every field of the generated type and fails unless the page draws it or spec/08 names it as left out); the fixture's team view counts `mine` and `older_than_week` from its world. **(B), a new part GR3b:** every GOV.UK page's fixture Conduit answers from the real route (a Python test runs the real routes in-process over the same synthetic worlds, stores at the conformance fakes, and writes golden JSON the page tests serve; a test fails when a golden drifts from the route). Its brief is drafted for the owner's rulings.

## 25 November 2026: IS6a's cycle through a hidden pipeline (the owner, in chat, about 05:00 UTC)

**Option (a).** The save refuses, naming them, every cycle among pipelines the saver can see; **a cycle that closes only through a pipeline hidden from the saver is stored, and refused at the run**, in words to whoever runs it or can see every pipeline in it. **This amends the owner's IS6 ruling 3 (24 November, "a cycle is refused on save, naming its pipelines") for that case only; access rule 3 stays whole:** the saver is never told, by refusal, wording, count or timing, that a hidden pipeline or a path through one exists. **Finding 2 (the import plan's pipeline count) is fixed in the same round.**

## 24 November 2026, night: PL7f's Docker exemption (D234) and AD1c's read-only role (the owner, in chat, about 23:50 to 23:55 UTC)

**PL7f (D234), option 1 of its report:** exempt in `tests/local_docker_guard.py` exactly the Caddy test's one command (`docker run --rm --network none`, the pinned `caddy:2.11.4-alpine` image, the three read-only mounts), named by the test; every other docker call stays refused under `no-local-stacks`, and a planted fault shows a second command refused. Sent back to its builder for that change; the conductor adds the scan-map row for `tests/harness/test_page_addresses.py` from the folders its report lists. **When 017-1 lands, this test moves to the server's container checks and the exemption comes out.** (The conductor's correction: PL7f's round-2 brief had said the switch was lifted; it is still on.)

**AD1c, option 1, as a new ADR-135 amendment written first (Amendment 15, a proposal for the owner's approval).** Conditions: (1) a read-only role on the gateway's database with `SELECT` on exactly two columns of the token table, `token` and `metadata`, nothing else; planted faults show any other column, any other table and any write refused by the database itself; (2) the builder first confirms from the gateway's own schema that the token column holds the stored hash, not a usable key; if not, it stops and brings it to the owner; (3) the role's password follows the owner's key rules: generated, never shown or printed, given to the Conduit alone, blanked for every other service in the render; (4) created by the gateway's own database setup; the sweep audited without any token value; (5) nothing changes on the demo. The builder gets the round it needs.

## 24 November 2026, night: IS6a's migration (the owner, in chat, about 23:45 UTC)

**IS6a's hold under D225 item 6 is lifted: the owner gives his word for its migration** (one new table, `dataset_run_orders`, created if absent, nothing altered or dropped). **It merges in turn.** The word covers that migration as described; a merge result whose migration alters or drops anything is not covered and comes back to him.

## 24 November 2026: the release is 0.7.0 (D227, the owner, in chat, about 05:40 UTC)

**One release at the end of this plan, numbered 0.7.0. No interim release.** (1) **Rename once, now: the product's `VERSION` and every text still to be written (the CHANGELOG heading, release notes, guides) say 0.7.0. Records already written that say v0.6.2 stay as they are; the lane folders (`v062`) are not renamed. Every slice brief from now is written with 0.7.0** (RL1b does the rename). (2) **RL2 is the release, in the plan after the last builds; its brief is drafted (`slices/RL2.md`, no row):** every release blocker in the backlog cleared, the owed live tests run, GitHub green on the release commit, an upgrade test from 0.6.1 (`start --build` and apply), release notes in the owner's wording rules, images signed, the maintainer's manifest. **Publishing is the owner's word.** (3) **The owed live tests: run as their parts land, under the stack lease, a batch at a time between merges; the count is reported each morning and must reach zero before RL2.** **The conductor's finding the same day: the count (325 distinct files on 24 November) falls only by the merge script's live step writing `live-paid.json`; a run by hand does not pay it (the records are written only by the line's own scripts).**

## 24 November 2026: the owner's rulings on the drafts; the adviser's standing rules (D225); the server (the owner, in chat, about 05:00 to 05:30 UTC)

**The server:** the owner cleared port 55434 (nothing listens; no model loaded) and told the conductor to resend PL12b, PL7c and SE8b (once its round is done); **if a run is refused for a port again, tell him at once with the port and the time.**

**PL7f:** the table of cases is approved with three changes (case 14 refuses IP and bracketed origins outright; a case for an HTTPS origin on the proxy's plain-HTTP port, refused; case 12 covers every port the proxy publishes). Row cut, builder started. Every finding that names sign-in, a certificate or a key is the owner's.

**IS6 (first slice: the stored order only):** (1) the existing right to edit pipelines, within the dataset; (2) edited on the dataset map page; (3) a cycle is refused on save, naming its pipelines; an undeployed pipeline may be in the order and is reported "not run: not deployed"; (4) the L08 cover is not in this slice and comes to the owner with options before its own; (5) the job file's schema is decided with the scheduler slice; (6) versioned = a number per save, with who and when, the expected number required on save, carried in a release export; (7) the dataset map's `FUNCTIONS.yaml` row moves to built.

**PL8:** (1) `spec/02` wins action by action; where today's workspace differs from it, the report names it for the owner; (2) the minimum side width is 300, correct `spec/02`; (3) scripts off: every panel open in its normal state, no controls; (4) `frame-scroll.spec.ts` is in scope; (5) start the first slice (logic and storage, no page) on PL9a; slices that mount it on a page wait for PL9's second half.

**AD3, RM1, GR2, GR3:** (1) GR2's first slice, the Help page, creates the GOV.UK tree, its switch, the gates' reach and the route list; a GOV.UK page may exist before its Default twin; keyboard tests in a folder per tree; (2) AD3 is Admin, RM1 is alerts, rules and watches; (3) a missing scenario is the first item of the part's brief, as ruled for IS2; (4) charts are plain SVG with classes, no library, no inline style, each with a table of the same figures; (5) no new Home path, the tree switch decides which tree serves `/`; split the reports row into figures (GR3) and dashboards (later); Help is GR2, the top bar stays R1; (6) add `govuk-frontend` (MIT) to the licence register, noting the crown, logotype and GDS Transport are used only under the identity switch on gov.uk addresses; (7) a non-viewer at the report route gets 404, the same as a missing report. **Order to start:** PL7f, GR2a, IS6's first slice, PL8's first slice, then GR3a, AD3a, RM1a as seats free (the last three are cut `after` GR2a).

**The adviser's review of the last 24 hours (the owner's word, 24 November; recorded as D225):** (1) **one records commit per merge, made at the moment the merge starts, never between merges; batch everything else into it.** (2) **Keep a ready queue of at least 6 ruled, cut parts ahead of the seats; bring every draft that needs the owner's rulings in one batch, twice a day: at 08:00 UTC and before he leaves; never let seats idle on a ruling the conductor could have asked for earlier.** (3) **If three rounds in a row of one part find new cases of the same kind of fault, stop and propose a structural fix (as PL7f), instead of another round.** (4) **Every brief's checks include the gate targets that read the files the part touches (design-check for anything under the sign-in page, the themes or `packages/design`).** (5) **Standing, every night until he says otherwise: when Docker has under 30 GB free and no merge is in its gate, run `docker builder prune -f`, at most twice a night, and report before and after; never `system prune`, `image prune -a` or `--volumes`; never his containers or airbyte.** (6) **The merge's live step will be turned on for parts whose change selects live tests (the line-fix session is building it). Until it lands, any part that changes a database adapter, the SQL connector, the reporting mart or a migration: tell him before its merge so he can decide whether to hold it** (IS6a adds a migration: it is held for his word). (7) **The server: once the demo-server session's read-only questions are installed, when a run is refused for a port, ask the runner what holds it and whether the shield would hold now, at once, before reporting; design the workaround (wait, resend, or what must change) and bring it to him; the conductor may only ask; anything that changes the server stays his.**

## 23 November 2026, evening: SE9b; the race test (PL4d3f); PL14a's rerun (the owner, in chat, about 21:00 to 21:15 UTC)

**SE9b (GitHub's conformance job has 80 live tests red on SE9's merge `2e13b10`: the parameter `:at` in three deletion statements):** the owner said yes. Rename the parameter in the three statements only; a live test against a throwaway ArcadeDB under the stack lease, red first; **prove the reserved-word reading on the live database first, and if the cause is something else, stop and tell the owner.** Track 4 (sol). **Its row is committed the moment AD1b's merge starts, not held for the whole stack: while main has 80 red on GitHub, a new failure from any other part would be hidden among them; if that costs PL12b's or PL7a2b's counted result, accept it. SE9b merges ahead of everything not yet in its gate.** The owner pushes main himself.

**PL4d3f (BACKLOG 21, the race test that depends on chance):** the owner said yes, cut it now on a sol track. It changes only `test_pl4d3d_declared_units.py` and what it needs to be deterministic; the test must still prove two builds in one tree collide; no case removed or loosened; red first by forcing the race, not by waiting for it. **Until it merges, a refusal by this test alone is rerun once without asking the owner.** (The conductor commits PL4d3f's row with SE9b's, at AD1b's merge start, so one commit costs the stack's counted green once.)

**PL14a:** the owner's send-back line was a misreading of the red-before block of `merge-d9ee38d9.log` (the test named failed only on the base, as required); **withdrawn and removed from `resume.tsv`.** PL14a's merge is rerun when the slot is free; the one failure in its gate was the race test above.

## 23 November 2026: a builder never merges another part's unmerged tip; a correction on the scan-row sections (the owner, in chat, about 19:40 UTC)

**Every builder: never merge another part's unmerged tip, or any branch but main, into your branch. Take main in when the line tells you to, and nothing else.** AD1b merged AD1a's tip and the hook then counted AD1a's tests as AD1b's. If a part needs another part's change that has not merged, it stops and tells the conductor. The sentence is in every live builder brief.

**Correction by the conductor.** The briefs for AD1b, PL12b and IS3 carried a section headed with the owner's name ("the owner, 22 November 2026, for the night" and "the owner's rule for the night") telling the builder to write its own scan row in `scan_rows/<ID>.tsv` and not stop on the hook's "has no row" line. **The owner never said that.** His word on 22 November (file 018, rule 3) was: *before any part starts, check that every test file it names or adds has its scan-map row, so no builder stops on a row you could have written.* The conductor turned that into a builder instruction and put the owner's name on it; it contradicts the README, the hook and the merge's first check (`scan_rows/` is a protected path) and is why AD1b and PL12b were refused. **The three sections are removed. A builder never writes into `scan_rows/`; the conductor writes a row on main first, from the verifier's or the builder's report.** (SE6c's brief has a different section, headed "the owner's rule for the night", which only records what the conductor checked on main: it asks the builder to do nothing, and it matches rule 3 of file 018.)

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

## 22 November 2026: the merge slot is held after IS5a's merge, for three patches (the owner, file 017)

**1. When IS5a's merge finishes, start no other merge until the owner says.** He has three patches to apply to main and needs the merge lock free for a few minutes. **Builders, verifiers and server runs carry on; only the merge slot is held.** **2. The conductor tells him in one line the moment IS5a's merge has ended and the lock is free, with its result.** **3. The three, in his order:** patch 22 (line fault 17: a refusal on the merge result is recorded, so `send-back` works; this frees SE6b); patch 23 (line fault 12: the git-identity test carries its own identity; after it a server run is no longer red on that test and the ruling that it counts as green is no longer needed); the log summary patch (demo-server 010). **4. When he says they are in: lift the hold; run SE6b's merge once more so its refusal is recorded, then send it back as a fix-up for the one test path; carry on by the algorithm (file 015).** **5. If IS5a's merge is refused, say why in the same line, and do not start it again until the patches are in.**

## 22 November 2026: file 018, the night; the trial of the server's green; two small rulings (the owner)

**File 018 (the night of 22 November): the algorithm of file 015 stands. Order: (1) AD1a then AD1b, merged back to back with nothing between; (2) what is left of PL7, so GG2 no longer waits on it (GG2 itself stops for the owner); (3) IS2 and IS3; (4) PL8, PL12, AD5. Not tonight: VA1, PL5 and anything demo-only; AD3, GR2, GR3, RM1, AD4. Parts in flight (SE9, PL7a2a, SE6b, RL1) carry on in their turn. Rules: a part that stops for the owner is parked, nothing waits on it, no question until morning; at most five new builds counting from 19:13; before any part starts, check that every test file it names or adds has its scan-map row, and say so in the morning report for each; server first, in stacks of three in merge order, verifiers do not count toward the seat limit; no commit to a path a merge reads while a merge is in its gate; the switch for the server's green stays as the owner leaves it, and every agreement and difference is recorded; stop everything, start nothing new and wait if main's gate is red on main, GitHub fails one of our tests twice (the tests the owner ruled on excepted), a finding names a key, a credential or a security rule, an account reaches 95%, the disk is short (under 8 GB free) or the Mac or the server cannot be reached; keep the Mac awake. The morning report goes at the top of `REPORTS_TO_OWNER.md`.**

**The disk (the owner, 19:30): cleared to 65 GB free; the 49 merged parts' working copies and test environments are gone, the unmerged ones are untouched.** **AD1a (the owner, 19:30): keep the `main.py` formatting in the branch, since AD1a edits that file itself; merge it as it is.**

**The trial of the server's green counting, on PL7a2a (the owner, about 19:35): when SE9's merge has landed, commit everything pending; then send PL7a2a to the server alone; from that moment make no commit to main at all, not even records, until PL7a2a's merge has started. Tell the owner the moment its server result is back, before the merge starts. After the merge, tell him exactly what the line said: counted, or not and why. Then carry on by file 018.** (A merge of another part is also a commit to main, so none runs in the trial's window.)

## 22 November 2026: the trial's result, and what the conductor did with the night (the conductor, 22:40; for the owner's morning)

**The trial on PL7a2a: the server's run `97dc976c7be6d175` was GREEN on an unmoved main `c593730`, and its candidate tree `06e6087fb5…` is the Mac's merge tree; the merge landed as `c200315` at 22:35:20; the line recorded `counted: false`, "the server's candidate tree None is not the Mac's 06e6087fb5". The server and the Mac agree; the line did not read the server's tree and verdict. Per the owner's rule for "not counted": the exact reason is at the top of the morning report and the night carries on by file 018 (the trial's commit habit is dropped; rule 5 stays: no commit while a merge is in its gate).** **Parked for the owner, with the reason: SE9 (an access-control test gap; no route to send a verified slice back), AD1b and PL12b (scan-map rows the line cannot take from a builder; AD1b's stop also names 'key' in test file names, a false positive the line will not clear), PL7a2b (the secrets contradiction with ADR-152 Amendment 3, and the GOV.UK demo), IS2 (no scenario in `spec/08`, open owner questions), PL7c (it takes the GOV.UK typeface out of the default build; the GOV.UK demo is protected, and its row cannot be written without choosing the acceptance test's name and commands).**

## 22 November 2026: the switch is on; the habit after the trial; SE9 parked (the owner, about 20:45 UTC; the conductor's reading, 21:12)

**The switch for the server's green to count (`server_counts`) is on (the owner, about 20:45). After the trial on PL7a2a: if the line said "counted" and the merge was clean, keep the habit for every merge tonight (commit what is pending, send the part, make no commit to main until its merge has started); if "not counted", record the exact reason at the top of the morning report and carry on by file 018.** **What the line had said about SE6b before the switch (its merge record, started 20:10, landed 21:11:29 as `9a680d5`): `counted: false`, `same: false`; why: "the owner's switch (server_counts) is off"; and the line's own test of sameness: "main has moved since the server's run (it ran on fd6b3c3e9a, main is fbe8e50e9b)". So the line counts a server run only if main has not moved since it ran: the reason for the trial's no-commit window.** **SE9 is parked for the owner (the conductor, 21:12): its round-5 verifier found a gap in a test on an access-control path (nothing run without a stack shows `count_deleted_visible` passes the caller's own principal into the query); a second verifier on the same tip passed it; the builder agreed the gap is real; a security finding is never accepted, so it is not merged tonight. It needs the owner's line to send it back (the assertion is in `slices/SE9_ROUND7_TABLE.md`) or his word to accept it narrower.**

## 22 November 2026: the trial starts after SE6b, not SE9; the race test is run again once (the owner, in chat, about 20:40 UTC)

**1. The trial of the server's green does not wait for SE9: it starts as soon as SE6b's merge has landed.** Commit what is pending, send PL7a2a to the server alone, no commit to main (not even records) until PL7a2a's merge has started, and tell the owner the moment its result is back, before the merge. **2. For tonight: if a merge is refused and the only red is the race test in `test_pl4d3d_declared_units.py` (backlog 21), run that merge again once. Do not send the part back for it, and no builder touches that test. If it is red twice running, park the part and tell the owner in the morning.** (SE9's round 4 broke this in advance: its builder edited that test and was sent back for it, round 5.)

## 22 November 2026: the series is in; SE8d retired; the hold lifted (the owner, in chat, about 18:30 UTC)

**The owner has put in and installed: the line-fix series (24 to 33), the 95% patch (34), the server patches (08, 09), SE8d's table entry (`7d63a90`) and the gate diff (`431bbbe`: the rights-table test runs in `make test`).** **SE8d is retired: its whole change is on main, applied by the owner (the line could not merge a slice with no code to be red without).** **The hold of 18:08 is lifted. Merge the verified parts in the conductor's order, SE9 first, and send the rest to the server as one stack in merge order.** The order: SE9, PL7a2a, SE6b, RL1, then AD1a (when its stop is cleared and verified), then AD1b. A green server result on an earlier main is enough for a part to take the slot (the Mac runs the whole gate anyway).

## 22 November 2026: verifiers do not count toward the merge-slot limit (the owner, in chat, about 16:41 UTC)

**Change to the merge-slot rule (file 004): verifiers do not count toward the two-seat limit and may start at any time, including while a merge is in its gate. The limit applies to builders only.** So while a merge is in its gate, at most two other builders run (the PL4 builder is one of the two and never held back); any number of verifiers may run. The conductor's own tightening (no seat in a merge's first stage) is withdrawn for verifiers.

## 22 November 2026: install.sh run; no waiting scan rows from now on; the scan-map line (the owner, in chat, about 16:33 UTC)

**The owner has run `install.sh`: the installed scan map now has PL4d3e's row. The conductor does not restore SE6b's waiting row and writes none for that test for any other part (the merge-hold for his patch ends here too).** The conductor deletes the two unneeded waiting rows still in `scan_rows/` (PL7a2a's, SE9's: each holds only that test's row). **SE6b's `clear-stop` is applied; its builder runs once to get the hook green, then verifier, server, merge.** **From now on, when a merge adds a row to the scan map (a merged slice's own `scan_rows/<ID>.tsv` row is appended to `scan_map.tsv`), the conductor tells the owner in one line and he runs `install.sh` again.** Rows now waiting that a merge adds: slice E's own (`test_glass_shared_canvas_logic.py`) and RL1's own (`test_maintainer_manifest.py`).

## 22 November 2026: the three patches are in; the merge hold is lifted (the owner, in chat)

**Patch 22 (line fault 17: a refusal on the merge result is recorded, so `send-back` works), patch 23 (line fault 12: the git-identity test carries its own identity) and the log summary patch are on main. The hold of file 017 is lifted.** **Order: run SE6b's merge once more so its refusal is recorded; then send it back as a fix-up for the one test path; then carry on by the algorithm (file 015).** **The ruling above (the git-identity test counts as green for the server-first rule) is no longer needed once a server run confirms that test passes; until a server run shows it passing, it stands.**

**A server run has now confirmed the git-identity test passes (22 November 15:13 UTC): DC1c's run (`early_warning/DC1c-404ebc75.md`, started 14:40:24, id `0e99deddb61c89cd`) is GREEN, with `slice-line-check` among the targets it ran. The ruling below that counts that one red as green is therefore no longer needed and ends here (the owner's own condition).**

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

## 23 November 2026: the owner's decisions of the morning (in chat; where one differs from an earlier word, this stands)

1. **SE6b stays on main; the revert is withdrawn.** On the conductor's own diagnosis (the SQL connector's read-only probe, `_WRITES` in `services/ingest/connectors/sql_connector.py`, asks `has_table_privilege` by name about every table of the database, and Postgres refuses a schema the login cannot use; SE6b's live tests leave `osprey_report_control` in the shared CI database). **SE6c is the connector fix alone**: steps 1, 2, 3, 5 and 6 of its brief, without step 4 (nothing to put back). **Step 1 first, on main as it is, with SE6b present:** on a throwaway Postgres run SE6b's live files, then the connector's live file, and show the twelve red. **If they are not red, stop at once and tell the owner: the diagnosis is then wrong and he reverts.** The probe stays exactly as strict as today, with the three no-weakening cases proved. (`SE6B_REVERT.diff` stays in the lane folder, unused.)
2. **The stop is lifted.** Until SE6c lands, the twelve failures of `tests/connectors/test_sql_connector_live.py` in GitHub's `conformance` job do not stop merging. **Any other failure in that job does, and the conductor compares the failing tests by name each time, not by count.** A release still needs every job green.
3. **"The GOV.UK demo is protected" means one thing: nothing changes the running deployment on the server, its settings or its data without the owner's word.** It does not stop any part from being built, verified or merged to main, because the demo runs the installed release and main does not reach it. **No part is parked for the demo unless the part itself would change the running deployment.**
4. **PL7c may start**; the conductor names its acceptance test as its brief describes.
5. **PL7a2b is not parked for the demo.** The one open question is the secrets contradiction with ADR-152 Amendment 3: the conductor gives it in full (both sentences, options, recommendation); if it can be settled within what Amendment 3 already says, the conductor does so, says how, and starts the part.
6. **IS2 is not parked for a missing scenario.** The ruling of 21 November stands: the scenario is the first item of the slice's brief, written by the builder from the decision records, the prototype and the owner's rulings, as IS3's was. IS2's first slice (the port, as it was cut) starts. The scenario covers at least: (a) a type record carries its class, identifiers, matching rule and properties with the indexed flag; (b) only the draft's creator can save into it, replace it or discard it, anyone else gets a refusal that tells them nothing; (c) a save or a delete carries the expected version, a stale one is refused and the person is told their copy is out of date without losing what they typed; (d) **the owner's message was cut off at "A person without the right, a dataset that is not": the rest is not recorded; the conductor asked for it.** *(The owner's later message gave (e) to (h): the step works with scripts off, lists as tables and actions as links or forms; a failure to read or save is said so in an alert, never shown as an empty model; the on-screen word is "Pipeline", never "recipe"; planted faults for each check. IS2's first slice is IS2a, `slices/IS2a.md`.)*

## 23 November 2026: file 020, fewer things wait for the owner (from the adviser, saved at the owner's request)

**Always the owner's, whatever else changes:** any finding that names a key, a credential or a security rule; the protected files; anything that removes or defers what a decision record requires; the server and the running demo; the switch for the server's green; anything public; a part that has failed the same way twice. **B (the conductor's from now): "I will do this unless you say otherwise"** for a decision that can be undone, is not in that list and needs no line in `resume.tsv`: say the question in one sentence, the recommendation and the time I will act (30 minutes from telling him when he is here; at once when he has said he is away or has not answered anything for two hours); then act; list it in the next report under "done without waiting", with what it would take to undo; if he answers otherwise before the time, do what he says. **D (the conductor's from now): ask in batches**, unless a part on the critical path is stopped by it: hold a question for the next report; each in the same shape (the question in one sentence; options lettered; my recommendation; what happens if he does not answer); **what needs his hand (a line in `resume.tsv`, a patch, an install) goes at the top with the exact line.** **A (being built by the line-fix session; until it is on main, ask as today):** one more round after a merge refusal, and a stop cleared whose cause is the line's and not the part's, without his line, within a budget of ten each a day; each report says how many were used and for what. **C:** each fix session gives him one script to apply what it has proved; nothing changes for the conductor. **Each report carries one line: how many times I waited for him since the last report, and for how long in all.**

**The owner is away two hours from about 10:57 UTC on 23 November: act on the conductor's recommendations as file 020 allows (at once, listed under "done without waiting"); hold only what is always his.** **PL7a2b case C (the owner, about 10:57): option A. The render refuses, in plain words, to turn the page service on for the cloud-platform shape, and says why; PL7a2b builds no cloud-platform sign-in; the chart's egress to the identity provider and the page service's own Entra registration (ADR-148 Amendment 23) are a part of their own, PL7e (backlog), before the page service is offered on cloud-platform.** **PL7a2b (the owner, 23 November, about 14:40): option A, accept it narrower, with two conditions: (1) the port-8080 case is a release blocker (BACKLOG.md, "RELEASE BLOCKERS"): until PL7f has merged no release ships, `pages.enabled` is not turned on for the demo or any deployment of his, and no guide or release note describes the setting as available; (2) PL7f is agreed, under PL7, after PL7a2b and before PL7d, and Caddy's own validation must run for real in at least one place every merge passes through; every PL7f finding that names sign-in, a certificate or a key is his. The conductor writes its brief and brings him the table of cases before a builder starts (`slices/PL7f.md`).** *The line refused the accept at 14:42: "a finding names a key, a credential or a security rule ('certificate'): the owner's accept never covers one, at any round" (the word is in the verifier's finding, which is about the own-certificate shape).* **PL12b: merge as soon as two builders have ended.** **D216 (PL14): the three answers are in `slices/PL14a.md`; the owner puts PL14 on the plan page.**
