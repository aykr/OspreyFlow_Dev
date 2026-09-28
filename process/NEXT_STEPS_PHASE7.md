# OspreyFlow — framing the next Claude Code sessions

Written 18 September 2026, at the close of Phase 6. Read against the Phase 6 → Phase 7 handover,
`process/07_BUILD_PLAN.md`, `spec/08_ACCEPTANCE_SCENARIOS.md`, `process/DESIGN_PROVENANCE.md` and the
repository as it stands at `b8b9207`.

Every claim below was checked against the working tree, not inferred from the documents. Where the
handover or `docs/` already names a gap, that is said; where a finding is new, that is said too.

---

## 1. Where the build is

The handover's phase table is correct and matches the tree: 0–6 closed, Phase 7 next, Phase 8
scoped only. Verified alongside it:

- `ComputePort` is the only port with no adapter. `packages/adapters/` holds `analytics_duckdb`,
  `graph_arcadedb`, `model_litellm` — no `compute_rustworkx`.
- `services/compute/` contains `__init__.py` and nothing else.
- `tests/conformance/compute_port/` has its suite and guard, with `COMPUTE_PORT_ADAPTERS` still
  empty. `tests/conformance/registry.py`'s own docstring says Phase 7 populating it flips that
  guard red as the designed handover.
- packages/schemas/_pending_port_placeholders.py still exists, and `ComputePort`'s five names are
  the **only** things left in it. `tests/schemas/test_placeholder_lifecycle.py` deletes the module
  once the last registry goes non-empty (since done — the module is removed). Phase 7 is the phase
  that removes the last of Phase 0's scaffolding.
- `apps/workspace/src/dossier/` is an empty directory. There is no document view.
- No hotlist, alert or monitor code exists anywhere in `services/` or `packages/`.

---

## 2. The finding that should shape the next session

The handover says Scenario B is "B1–7 ready, B8+ and B19–20 blocked on Phase 6/7 (Phase 6 now
closed, so B8+ should be re-checked)". That re-check is the right instinct, and it should be wider
than the handover assumes in two directions.

**First: B1–B7 is not ready.** B6 requires a document view rendering message content with entity
spans highlighted in place. `apps/workspace/src/dossier/` is empty; there is no such screen. Phase 6
built the extraction and span machinery and disclosed, correctly and in its own gaps list, that it
shipped "no Glass/frontend screens — backend/API only, consistent with every other Phase 6 stage".
Nothing after it picked the Glass half up.

**Second: the same is true of most of the resolution steps, and Phase 7's bullet list does not claim
them either.** Phase 7's exit criterion reads "Acceptance scenario B passes end to end". Its bullet
list covers B12–B14, B19, B20 and the compute work carrying A12's re-proof. It does not cover:

| Step | What it needs | Who was meant to build it |
| --- | --- | --- |
| B6 | Document view with entity spans in place | Nobody. `dossier/` is empty |
| B9 | Resolution threshold slider with change summary | Phase 6's bullet list named it; Phase 6 shipped `/v1/resolution/threshold` and no control |
| B10 | `explain` rendered for an analyst | `explain_cluster` exists as an endpoint only |
| B11 | Manual link from the interface | `manual_link` exists as a service method only |
| B14 | The alert opening into a pre-populated investigation, linked to the originating one | Cross-case linking has no owning phase |
| B16 | Cross-case timeline overlay on distinct tracks | No phase's bullet list claims it |

This is the same class of defect ADR-019 already corrected once, for Phase 5 and A12: a scenario
attributed to a phase whose scope does not build everything the scenario exercises. It is worth
fixing the same way — as a recorded decision, before the phase, rather than as a discovery at the
exit gate.

### Three blockers the handover does not name

All three are load-bearing for Scenario B and all three are already written down elsewhere in
`docs/` — they simply have not been read together against Scenario B.

- **The ingest load path does not write the analytics store.** Phase 2's stated gap; confirmed in
  `services/ingest/engine.py`, which imports `EventRecord` as a type and never calls
  `AnalyticsPort`. The analytics store is populated only via test-harness wiring. B16, B17 and B18
  — timeline overlay, temporal brush, snail trail — read events from the analytics store. An
  end-to-end Scenario B that ingests through the real path and then opens the timeline finds it
  empty.
- **Only the CSV connector exists.** `services/ingest/connectors/` holds `csv_connector.py` and a
  `geo/` directory; JSON and generic-delimited are stubbed. Scenario B's fixture is two CDR files
  *in different carrier formats* plus two device extractions.
- **Nothing triggers resolution or alerting against the live corpus.** Phase 6's gaps list states
  it plainly: `resolve_entity_type`, `write_same_as_edges`, `detect_conflicts` and
  `record_conflicts` are real and tested, with no ingest hook, no cron and no manual endpoint —
  every test calls them directly. B13 ("ingest the seizure record → an alert fires") and B20
  ("subsequent matching ingest raises an alert") both need exactly that post-ingest hook, and
  B8–B9 presume resolution has already run corpus-wide.

### And the orphaned gap is in Scenario B's path

The handover records the OpenSearch consumer gap as *resolved* — meaning correctly written down in
the new "Gaps with no owning phase" section, not built. That section itself asks for a scoping
decision "before a future phase assumes `/v1/search`'s document and index legs already work because
the graph leg does." Phase 7 is that future phase: B4 seeds a working set by search, B6 renders
document content. The decision is now due.

---

## 3. What to settle before any Phase 7 code is written

Four questions, all plan-mode material. The project's own process conclusion applies: answer each by
editing `docs/`, not in the chat.

**3.1 — How is Scenario B split?** Either Phase 7 absorbs the Glass work for B6, B9–B11, B14 and
B16, or Scenario B splits across Phase 7 and Phase 8 the way ADR-019 split Scenario A. The second is
probably right and definitely cheaper, but it needs to be a recorded decision.

**3.2 — What does "ComputePort conformance across all three tiers" mean in practice?** The handover
itself writes the third tier as "whichever third tier the build plan names", which is the tell. Two
unresolved mechanisms sit under one sentence:

- Tier 1 is graphology in a browser Web Worker — a TypeScript implementation. Every conformance
  suite in this repo is a Python `pytest` parametrisation over an adapter registry. How a Python
  suite exercises a Web Worker has no precedent in the repo and no answer in `docs/`.
- Tier 3 is GraphFrames on Spark, or HugeGraph Vermeer, specified for >2M nodes
  (`00_ARCHITECTURE.md` §2.3). The exit criterion asks all three tiers to agree on a 5,000-node
  fixture, which means standing Spark up on this host. Given the ArcadeDB/Ollama contention on a
  ~7.6GB VM that the handover lists among its open gaps, this is an environment decision, not a
  coding one.

**3.3 — Does `§8.1`'s pattern-binding rule survive the visual query builder?** The previous handover
flagged this for exactly this phase: `PatternQuery` admits no pattern where a node is reachable only
via a later edge. Fine while patterns are constructed in code; Phase 7 puts an analyst in front of a
canvas drawing arbitrary ones. Either the restriction is enforced in the builder and explained at
the point of drawing, or `PatternQuery` and its Gremlin builders change. `01_DOMAIN_MODEL.md` §8.1
is the text to amend.

**3.4 — Where does the OpenSearch index land?** Its own phase, or folded in. The natural producer is
Phase 2's ingest pipeline; the natural consumer is Phase 4's Glass search box. Neither is reopening.

---

## 4. Suggested session sequence

Sessions 1–4 are prologue: none is Phase 7, all are things Phase 7's exit criterion stands on.

| # | Session | Output |
| --- | --- | --- |
| 1 | Scenario B reconciliation audit | Edits to `07_BUILD_PLAN.md` and a new ADR. No code |
| 2 | Close the Phase 2 gaps Scenario B stands on | Analytics write in the load path; JSON and generic-delimited connectors |
| 3 | Scope the corpus-wide resolution and alerting trigger | Plan, then build |
| 4 | Scope the OpenSearch/search gap | ADR plus a build-plan edit |
| 5 | Phase 7 schemas and conformance suite | Real models for the five placeholder types; `_pending_port_placeholders.py` deleted; suite written before any adapter |
| 6 | The pattern-binding decision | Amendment to `01_DOMAIN_MODEL.md` §8.1 |
| 7+ | Phase 7 stages | rustworkx adapter, browser worker tier, metrics panel, visual query builder, hotlists and alerting, pathfinder |
| — | After Phase 7 closes | Refresh the Developer & Operator Guide; unblock Scenario C's C9–C16; scope the Panama Papers fixture |

Session 5 is a natural single unit and a satisfying one: real Pydantic models, the last of Phase 0's
scaffolding removed, the TypeScript drift gate tripped deliberately, and the conformance suite
written before the adapter exactly as standing rule 1 requires.

The stage-review discipline the handover describes should carry unchanged — the executing session
reports a stage done, the reviewing session cross-checks code, tests and CI output against the
exit-criterion text and either signs off or returns a numbered list. It found four open items in
Phase 6 Stage 1 and three more in Stage 4.

---

## 5. Handover and provenance consolidation — resolved 19 September 2026

`docs/` briefly held three overlapping handover-shaped documents that disagreed with each other.
Closed: the Phase 6 → Phase 7 handover now occupies `SESSION_HANDOVER.md` at one path, the Phase 3
original is in `process/archive/`, every live citation was repointed (eleven of them, across four
pieces of content, not the three first counted), three durable facts were lifted into `CLAUDE.md`
as rules 11, 12 and a Conventions line rather than left in a snapshot document, and
`DESIGN_PROVENANCE.md`'s §4 defect table and §6 untested list were brought current to the close of
Phase 6.

Retained here only so a reader of the original sequencing knows this item closed rather than
lapsed.

## 6. The two deliverables outside the repository

Both are Claude Docs artifacts and both assume a completed platform, so both carry claims that are
not yet true. Worth a note in `docs/` so they are findable from the repository rather than only from
a handover.

- **Developer & Operator Guide.** Its Phase 8 deployment-harness section documents a harness that
  does not exist, and its port/adapter table has a `adapters/compute_rustworkx` row reading
  "Phase 7" as a placeholder. The handover flags the caveat as needing to be more explicit. The
  refresh is a post-Phase-7 task, and the handover is right that it is easy to forget.
- **Scenario C demo script** (Fixture Corp — ~150 fabricated employees, structural stats modelled
  on published Enron research, zero real identifiers). Steps C9–C16 are the analytics-dependent
  portion and become runnable when Phase 7 lands.
- **Panama Papers scenario** — backlog only. No fixture design, no draft. Same synthetic-fixture
  discipline as Fixture Corp when it is picked up: structural stats modelled on a real published
  case, nothing real in the repository.

---

## 7. Session prompts

Paste-ready, in the style of `docs/handoff/PROMPTS.md`. Each assumes plan mode first where the
project's own process calls for it.

### Session 1 — Scenario B reconciliation (plan mode, no code)

> Plan mode. No code this session; the output is edits to `docs/`.
>
> Phase 6 is closed. Phase 7's exit criterion is "Acceptance scenario B passes end to end", and the
> Phase 6 → Phase 7 handover says B1–B7 are ready with B8+ needing a re-check. I want the whole
> scenario re-checked, not just B8 onwards.
>
> Walk `spec/08_ACCEPTANCE_SCENARIOS.md` Scenario B, B1 to B20, one step at a time. For each step
> state which of these it is: (a) built and tested today, (b) claimed by Phase 7's own bullet list
> in `process/07_BUILD_PLAN.md`, (c) claimed by Phase 8's, or (d) claimed by no phase's bullet list at
> all. Cite the module or the bullet for each answer. Where a step is partly built — an endpoint
> with no screen — say so rather than rounding it to either side.
>
> I believe the following are (d) and want them confirmed or corrected rather than assumed: B6's
> document view with entity spans (`apps/workspace/src/dossier/` is an empty directory), B9's
> threshold slider and change summary, B10's explain rendering, B11's manual link from the
> interface, B14's link to the originating investigation, and B16's cross-case timeline overlay.
> Phase 6 disclosed in its own gaps list that it shipped backend and API only; my reading is that
> no later phase picked the Glass half up.
>
> Then propose the fix as a decision record in the mould of ADR-019, which did this once already for
> Scenario A and A12: either Phase 7's bullet list grows to cover the Glass work, or Scenario B
> splits across Phases 7 and 8 with each phase's exit criterion naming the steps it actually proves.
> Give me the trade-off, recommend one, and write it as an ADR with a "revisit if" clause plus the
> corresponding `07_BUILD_PLAN.md` edits. Targeted edits with exact old and new text — never a
> replacement file.

### Session 2 — Phase 2's two open gaps

> Plan mode first.
>
> Two gaps from Phase 2 are load-bearing for Scenario B and both are already named in
> `process/07_BUILD_PLAN.md`'s Phase 2 section, but neither is currently tracked as a Scenario B
> blocker.
>
> First: the ingest load path does not write the analytics store transactionally alongside the graph
> store. `services/ingest/engine.py` imports `EventRecord` as a type and never calls
> `AnalyticsPort`; the analytics store is populated only via test-harness wiring, per the ingest
> entrypoint's own docstring. Scenario B's B16, B17 and B18 read events from the analytics store, so
> an end-to-end run that ingests through the real path finds it empty.
>
> Second: only the CSV connector is implemented — `services/ingest/connectors/` holds
> `csv_connector.py` and `geo/`. Scenario B's fixture is two CDR files in different carrier formats
> plus two device extractions; the Phase 2 bullet promises CSV, JSON and generic delimited.
>
> Plan both. For the analytics write I want the transactional story explicit: what happens when the
> graph write succeeds and the analytics write fails, and which test proves it. State what the spec
> says about that and, if it is silent, say so and propose rather than filling the gap quietly.

### Session 3 — The resolution and alerting trigger

> Plan mode. No code until I have seen the plan.
>
> `process/07_BUILD_PLAN.md`'s Phase 6 known-gaps list records that no corpus-wide resolution job
> trigger exists: `resolve_entity_type`, `write_same_as_edges`, `detect_conflicts` and
> `record_conflicts` are real and tested, but nothing schedules or triggers a run against the live
> corpus — no ingest hook, no cron, no manual endpoint. Every test in `tests/resolve/` calls them
> directly.
>
> Scenario B's B13 and B20 both depend on a post-ingest hook: ingesting a seizure record must raise a
> hotlist alert, and subsequent matching ingest must raise a saved-pattern alert of the same shape.
> B8 and B9 also presume resolution has run corpus-wide before the analyst moves τ.
>
> Plan the trigger: what runs it, on what event, against which population, with what access control,
> and what happens when a run overlaps the previous one. This is undesigned work, so tell me which
> parts `docs/` already constrains and which parts you are proposing — flag every inference as a
> proposal before writing code, per CLAUDE.md. The same gaps list notes there is no proactive
> conflict-discovery surface, deliberately; say whether that belongs in this work or stays separate.

### Session 4 — The unowned search index

> Plan mode. The output is an ADR and a build-plan edit; no implementation this session.
>
> `process/07_BUILD_PLAN.md`'s "Gaps with no owning phase" section — added at Phase 6 close — names the
> OpenSearch full-text-and-embeddings index and explicitly asks for a scoping decision before a
> future phase assumes `/v1/search`'s document and index legs work because the graph leg does.
> Phase 7 is that future phase: Scenario B's B4 seeds a working set by search and B6 renders
> document content.
>
> Give me the decision. Its own phase, or folded into an existing one? The gaps entry suggests
> Phase 2's ingest pipeline as the natural producer and Phase 4's Glass search box as the natural
> consumer, but neither phase is reopening. Include what Scenario B actually needs from it as
> against the full federated-search surface `03_CONDUIT_MIDDLEWARE.md` §3.3 specifies — if B4 and B6
> can be satisfied by less, say so and scope the rest separately. The ADR should also restate that
> `04_VAULT_BACKEND.md` §1.4 ties OpenSearch to JanusGraph in Phase 8 as a different consumer of the
> same store, so Phase 8 closing does not close this gap.

### Session 5 — Phase 7 schemas and the ComputePort conformance suite

> Plan mode first, then build continuously once I approve.
>
> Opening Phase 7. Scope it the way Phase 6 was scoped: propose a stage breakdown before writing any
> code, and flag anything in the exit criterion needing a decision up front. Read
> `07_BUILD_PLAN.md`'s Phase 7 section, `01_DOMAIN_MODEL.md`, and `02_GLASS_FRONTEND.md`'s sections
> on the metrics panel and the visual query builder before proposing — cross-check the domain model
> and Conduit docs rather than working from the build plan alone.
>
> This first session is schemas and the conformance suite only — no adapter, per standing rule 1.
>
> packages/schemas/_pending_port_placeholders.py (since removed) now holds only `ComputePort`'s five names:
> `CentralityRequest`, `CommunityRequest`, `CliqueMetricRequest`, `MotifRequest` and `MotifMatch`.
> Design them for real against `00_ARCHITECTURE.md` §2.3 and Phase 7's bullet list — degree,
> betweenness, eigenvector, clustering coefficient, Leiden, the Clique Metric — then delete the
> module. `tests/schemas/test_placeholder_lifecycle.py` guards that deletion; the TypeScript drift
> gate will fire, which is expected, and the generated types should be regenerated in the same
> change.
>
> Then write the `ComputePort` conformance suite. Two things in the exit criterion need answering
> before you write a line of it, and I want the answers in the plan:
>
> 1. The exit criterion says all three tiers return identical values within tolerance on the
>    5,000-node fixture. Tier 1 is graphology in a browser Web Worker — a TypeScript implementation
>    — and every conformance suite in this repo is a Python pytest parametrisation over an adapter
>    registry. How does the suite exercise the browser tier? There is no precedent in the repo and
>    `docs/` does not say.
> 2. Tier 3 is GraphFrames on Spark or HugeGraph Vermeer, specified for over 2M nodes. Running it
>    against a 5,000-node fixture means standing Spark up on this host, whose ~7.6GB Docker VM
>    budget already has three dated OOM notes in `deploy/compose/dev.yaml` from ArcadeDB and Ollama
>    contention. Tell me whether that is feasible; if it is not, propose the honest alternative and
>    record it — deferring tier 3 to Phase 8's cluster profile is a legitimate answer if it is
>    written down as one, with its own ADR and a "revisit if" clause.
>
> `tests/conformance/registry.py`'s docstring says populating `COMPUTE_PORT_ADAPTERS` flips
> `compute_port/test_guard.py` red as the expected handover. Confirm that happens as designed.

### Session 6 — The pattern-binding rule before the query builder

> Plan mode, and this is a specification question before it is a coding one.
>
> `01_DOMAIN_MODEL.md` §8.1 constrains `PatternQuery` so that no pattern can have a node reachable
> only via a later edge. The Phase 3 handover flagged that as more restrictive than Phase 7 would
> want and marked it "revisit at Phase 7". Phase 7 builds the visual query builder, which puts an
> analyst in front of a canvas drawing arbitrary patterns.
>
> Tell me which patterns an analyst would plausibly draw that the current rule rejects. Then give me
> the two options honestly: enforce the restriction in the builder and explain it at the point of
> drawing, or change `PatternQuery` and its Gremlin builders to admit the wider shape. For the
> second, state what it costs — ADR-003's bounded-query guarantee is what makes accepting a pattern
> from above the Vault boundary safe, and I want to know whether widening it weakens that.
> Recommend one, and write the outcome into §8.1 rather than answering only here.

### Housekeeping — completed 19 September 2026 (see §5)

No longer to be issued; the work it describes is done.

### After Phase 7 closes

> Phase 7 is closed. Three follow-ups that were parked on it.
>
> First, refresh the Developer & Operator Guide: its port/adapter reference table has an
> `adapters/compute_rustworkx` row reading "Phase 7" as a placeholder, and its Phase 8
> deployment-harness section documents a harness that still does not exist — make that caveat
> explicit rather than leaving the guide reading as though the platform were complete.
>
> Second, the Scenario C demo script's steps C9 to C16 are the analytics-dependent portion and
> become runnable now. Walk them against what Phase 7 actually landed and report which run clean,
> which need the script amended, and which are still blocked.
>
> Third, scope the Panama Papers scenario. Nothing exists for it — no fixture design, no draft.
> Follow the same discipline as Fixture Corp: structural statistics modelled on a real published
> case, wholly synthetic content, zero real identifiers, seeded and deterministic, in-repo, with
> shape-correctness tests of its own. Propose the fixture design before drafting the scenario.

### Standing — the end-of-phase audit

Unchanged, and it has found a real defect every time:

> Where does this diverge from `docs/`, and what did you assume that the spec does not state? List
> the assumptions explicitly — I care more about those than about the code.

---

## 8. One thing not in any document

Every phase since Phase 1 has recorded a memory-contention incident on this host: ArcadeDB OOM under
concurrent DDL (Phase 1), the heavy sequential HMP build (Phase 5), cross-container contention with
Ollama's resting footprint (Phase 6) — three dated notes now in `deploy/compose/dev.yaml`. Each was
diagnosed correctly and each cost real time.

Phase 7 adds compute workers to that same budget, and its exit criterion asks for a Spark tier on
top. This is the one item that is an environment decision rather than a build decision, and it is
worth taking before Phase 7 rather than during it — whether that means raising the Docker VM
ceiling, moving the heavy conformance work to CI only, or scoping tier 3 out of Phase 7
deliberately.
