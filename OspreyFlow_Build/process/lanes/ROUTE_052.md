# The route to v0.5.2 · every lane's brief (the owner, 13 November 2026)

**Aim (the owner's words): build each thing once, check each thing once.** Target **Thu 26 Nov**. The dated steps
are in `route.tsv`, which the heartbeat reads. **v0.5.1 is cut with no new work and no new checks**, from commit
9197ea6: its upgrade rehearsal and its publish (`make publish-user-repo COMMIT=9197ea6`) name that commit, so v0.5.2's
branches merge to main as soon as they are ready (the owner lifted the earlier hold on 13 Nov, about 23:00).

## Scope: nothing else joins v0.5.2

- Superset and report sync on cloud-platform poc, with Entra sign-in.
- Search on OpenSearch, with OpenSearch staying in poc.
- The poc manifest, with the command that prints the client page's tables.
- Fixes the owner rules in from the ADR-148 audit, once they are ruled.

White-label work, the backlog features and search by meaning stay outside.

## Search scope (the owner's)

1. **Names:** tolerant of typos, spelling variants and sounds-like matches, across every entity type.
2. **Full text** of documents and reports, with the matching passage highlighted.
3. **Ranking:** exact identifier first, then close names, then mentions.
4. **Results** grouped by type with counts; filters by dataset and date.
5. **Suggestions** at typing speed, with one type in the tens of millions.

## Search requirements (the owner's)

a. Dataset access and handling codes are enforced **inside the query**. Counts and snippets obey the same rules. **One
   test proves an analyst cannot see, count or infer a record they are not cleared for.**
b. The graph stays the source of truth.
c. If OpenSearch is unreachable, the bar falls back to today's search and **says so on screen**.
d. Searches are audited as today.
e. Both looks (light and dark), and the accessibility checks.
f. Every shape that runs an OpenSearch container (Lite, Small, cloud-platform) gets OpenSearch-backed search;
   wherever it is unreachable, c applies.

**The access design comes first.** The orchestrator sends the owner one page by Mon 16 Nov, covering:
- how dataset access and handling codes are held in the index;
- how a merged entity built from datasets with different access is indexed and shown;
- how counts, suggestions and snippets are limited;
- what the leak test asserts.

Step 3d's access parts don't go further until the owner has read it. Studio drafts it by Sun 15 Nov, and rules
contributes the index side.

## Rules for every lane

- **The manifest is the one source** for images, containers, sizing and the install test. There is no hand-kept copy
  anywhere.
- **Lanes run their own tests as they build; the full suite runs once, at step 6.**
- **Synthetic data only.** Protected files (`.github/`, the Makefile) go to the orchestrator as diffs.
- **Nothing on osprey-small** until the owner releases it.
- **Ask the orchestrator for ADR reservations.** Any cut or deferral of something an ADR or the client page requires
  goes to the owner first, through the orchestrator.
- **Keep the heartbeat's stages current** under your step's id below.

## Per lane

**platform:**
- **step 2 now, `v052-manifest`:** a new file, poc_manifest.yaml, in the cloud-platform harness folder, holding:
  - the containers, with their counts, images, requests, limits and readiness probes;
  - the Jobs and CronJobs;
  - the images and ECR repositories, ours and upstream;
  - the managed services: RDS (class, `max_connections` 1000, databases ospreyflow, litellm, superset), ElastiCache,
    S3, and **OpenSearch** (2 data nodes);
  - Entra's registrations;
  - the egress hosts.

  Superset and report sync go in at one copy each. Add a render test that fails **both ways** (rendered but not
  listed; listed but not rendered), and counts and requests checked. Red first on each side. Add a command that
  prints the client page's tables from the manifest.
- **then step 3a, `v052-opensearch`:**
  - remove the poc refusal;
  - the Terraform with 2 data nodes;
  - how the product signs in (IRSA with SigV4, or the domain's fine-grained auth: propose before building);
  - egress, and what the client must provide;
  - the decommission and backups (the index rebuilds from the graph, so say whether it is backed up at all).
- **then** v0.5.2's Entra stand-in signs (`v052-standin`), and step 4's measurement, `v052-measure`.

**platform-b:** step 3b, `v052-superset` (as planned), and you lead step 6, `v052-r1`: the install test on the
candidate.
- It is driven from the manifest: install v0.5.1, upgrade to the candidate, verify every manifest entry, run the
  spec's acceptance scenarios (08_ACCEPTANCE_SCENARIOS.md) that apply to the shape, then decommission.
- The decommission makes the operator choose keep or destroy, if audit ruling 3 is in.

**rules:**
- **step 3c, `v052-index`:** every load, merge (SAME_AS), new version, promotion and deletion reaches the index. Add
  one rebuild command from the graph, and one drift check that reports the difference between graph and index.
  Red first, each event type.
- **then B, `v052-load`:** generate the client-size synthetic data:
  - tens of GB in all;
  - around 10–15 sources;
  - one in the tens of millions of rows;
  - documents with narrative text.

  Load it **once** on the test server by **Wed 18 Nov**, in a lane stack kept up under a long lease the orchestrator
  grants, and leave it loaded. Step 4 measures on that same load.

**studio** (reopened): **step 3d, `v052-search`:** the search service.
- **Draft the access design page (A) by Sun 15 Nov**, with rules, to the orchestrator.
- Then the query side:
  - names tolerant of typos, variants and sound-alikes, under the owner's strict-ranking ruling (13 Nov, page A):
    three-letter fragments, stored prefixes and a Double Metaphone key computed by the Conduit; no word-rarity
    scoring, no fuzzy or prefix expansion, no plugin relied on;
  - full text with highlighting;
  - ranking;
  - grouped counts and filters;
  - suggestions;
  - the fallback, and the audit.
- Access stays in the query, with the leak test.

**case** (reopened):
- **step 3e, `v052-fixes`:** the owner's screen fixes, seen on the GOV.UK look:
  - the Cases panel: Open covers the Private tag and the buttons wrap to four lines. Lay each view out so name, tag
    and actions fit;
  - the Cases panel covers the top navigation;
  - the strip says "Graph: the case's data" while the page shows Alert monitoring, and two rail items are marked at
    once. One place, one marker;
  - the dataset is named three times in one row: once.
- **Don't build the search results layout** (step 3e′) until the owner's navigation decision arrives (by Wed 18
  Nov).

**docs:** step 5, `v052-sweep`, after the freeze: one sweep of every claim about search and OpenSearch in the product,
the guides and both websites, plus the ADR-148 audit's findings. The websites keep today's search wording until then.
The site fact-check is already done and is not repeated (the owner, 13 Nov).

**admin:** first `v052-heartbeat`: the heartbeat's route view (below). Then 3b's `v052-identities`, which has slack
to Thu 19.

## The heartbeat's route view (admin)

The default view and `watch` show this and nothing else needs reading. One screen, no scrolling on a normal terminal.

1. **Headline:** the target (Thu 26 Nov), days left, and one word: on track, at risk or late. If at risk or late,
   one line saying which step and why.
2. **The route:** one row per `route.tsv` step, with:
   - its lane and planned dates;
   - its state, from the lane's own progress row and beat: not started, running, done, or blocked. **"Done" only
     when its tests passed**, i.e. merged with its gates;
   - days ahead or behind against its planned end;
   - what it waits on (its `after`);
   - critical-path rows marked.
3. **Waiting on the owner:** from `owner_due.tsv` (who = owner), soonest first.
4. **Waiting on the orchestrator:** from `owner_due.tsv` (who = orchestrator), soonest first.
5. **Audit rulings:** from `audit.tsv`, each with its state and whether it is in v0.5.2.
6. **Outside this route:** each lane step not on the route, one line each (the websites, Part 3, D1, and so on).
7. **Finished work:** one line with a count.

The old views stay behind their commands (`--lanes`, `--full`, `summary`). Tests red first for each part, including:
- "at risk" when a critical step's planned end has passed undone;
- a step shown done only when its progress row is done;
- the one-screen line limit.
