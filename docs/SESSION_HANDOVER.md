# OspreyFlow — Session Handover

2026-09-18 · @Ayan

## Where things stand

Repo: `/Users/ayankar/Documents/MyProjects/IntelAnalysis_and_NetworkDiscovery_Platform/ospreyflow` (git, remote `origin/main`, on Ayan's Mac). Docs live under `docs/`: 01\_DOMAIN\_MODEL.md, 02\_GLASS\_FRONTEND.md, 03\_CONDUIT\_MIDDLEWARE.md, 04\_VAULT\_BACKEND.md, 05\_DEPLOYMENT.md, 06\_DECISIONS.md (ADR log), 07\_BUILD\_PLAN.md (phase-by-phase plan, plus a "Gaps with no owning phase" section), 08\_ACCEPTANCE\_SCENARIOS.md, 09\_INGEST\_STUDIO.md.

| Phase | Status |
| --- | --- |
| 0–4 | Complete |
| 5 / 5a — Ingest Studio | Closed. Known gaps logged in 07\_BUILD\_PLAN.md \~L312–343 |
| 6 — Extraction and resolution | Closed this session |
| 7 — Analytics, patterns, alerting | Not started — agreed next phase |
| 8 — Assessment, export, second profile, deployment harness | Not started, scoped only |

Phase 6 exit criterion (met): "Ingest a witness statement. Extracted entities appear as inferred with correct source spans. Moving τ from Strict to Broad merges the expected clusters and reports the delta. A manual split survives a subsequent resolution run that would have merged the pair, and the conflict is recorded for review." Scoped to entities only — edge/relationship extraction from unstructured material was never promised and stays out of scope.

Phase 7 exit criterion (target): Acceptance Scenario B passes end to end; the Clique Metric ranks the insular-cluster fixture node above the broad-hub node; all three compute tiers (rustworkx / browser worker / whichever third tier the build plan names) agree within tolerance; A12 (deferred from Phase 5 per ADR-019) is re-proven on the HMP fixture.

## Working discipline established

**Stage reviews.** Each build stage (and phase) closes only after the reviewing session checks the actual code, tests and CI output against the exit-criterion text — never on a summary alone. The recurring pattern: the executing session reports a stage done, the reviewer cross-checks it and either signs off or sends back a numbered list of open items before the next stage starts. Example: Phase 6 Stage 1 needed 4 follow-up items closed (witness-statement fixture, placeholder retirement, conformance-assertion content, ModelPort.embed() ownership) before it counted as genuinely closed; Stage 4 needed 3 more (SAME\_AS field citation, an ADR for "no EM training," a hand-labelled resolution-accuracy check), re-checked again before Stage 5 could open.

**ADRs.** Live in 06\_DECISIONS.md, numbered (ADR-005, 006, 007, 015, 018, 019, 020, 021 so far). Convention: any revisit-worthy decision — a model pin, a scope narrowing, a tradeoff like "no EM training" — gets its own ADR or an addendum to an existing one, with a named "revisit if" clause, rather than living only in a code comment. Precedent: ADR-015 (CI must never depend on a third party's availability), ADR-019 (why Phase 5's exit criterion split across three phases), ADR-020 (model-pinning doctrine — pin by digest not tag; later got a Stage 2 addendum for the digest-pull limitation and a LiteLLM healthcheck fix).

**Gap disclosure.** Known incompleteness gets written down where a future reader will actually look — either inline under the relevant phase/stage in 07\_BUILD\_PLAN.md, or, for gaps with no natural owning phase, in a dedicated "Gaps with no owning phase" section (added this session, between Phase 8 and the standing rules). House rule, stated repeatedly: "the OpenSearch consumer and the witness-statement fixture both drifted by living only in a message rather than a file." Standing rules referenced throughout (numbered 1–5): no real data ever enters the repo (fixtures are synthetic, seeded, deterministic, in-repo, with shape-correctness tests of their own); every new write path needs an access-control test; CI must not depend on third-party availability. CLAUDE.md also requires flagging any inference or scope addition as a proposal *before* writing code, rather than folding it in silently.

## Existing deliverables

| Deliverable | Link / location | Status |
| --- | --- | --- |
| Developer & Operator Guide | [Claude Docs artifact](https://claude.ai/code/artifact/0d214245-8c15-4da5-901c-220b15d25fc6) | Drafted — Overview, Getting the platform running, Onboarding data, Working in the Glass, Entity resolution, Assessment and export, Deploying for real, Administration, Reference. Written assuming full completion; the Phase 8 deployment-harness section (`docker run ghcr.io/ospreyflow/harness:latest`, six setup screens) documents something not built yet — flagged to make that caveat more explicit |
| Scenario C demo script | [Claude Docs artifact](https://claude.ai/code/artifact/b11fca43-af93-41e4-ace5-dd51520351f3) — "OspreyFlow Full-Platform Demo Script — Scenario C (Corporate Communications Network)" | Planning document, assumes all 8 phases complete (they aren't). Fixture: "Fixture Corp," \~150 fabricated employees, 5-level hierarchy, 4 departments, structural stats modelled on published Enron corpus research (156 nodes, 500k+ edges, zero real identifiers). Steps C9–C16 (the analytics-dependent portion) are blocked on Phase 7 |
| Acceptance scenarios | 08\_ACCEPTANCE\_SCENARIOS.md | Scenario A (HMP fixture) fully buildable today; Scenario B (CDR/comms fixture) B1–7 ready, B8+ and B19–20 blocked on Phase 6/7 (Phase 6 now closed, so B8+ should be re-checked) |
| Panama Papers scenario | — | Not started. Only requested as a "for later" idea alongside Enron — no fixture design, no draft, pure backlog |

## Immediate next steps for the incoming session

1. **Scope Phase 7** the same way Phase 6 was scoped: propose a stage breakdown before writing any code, and flag anything in the exit criterion that needs a decision up front. Read 07\_BUILD\_PLAN.md's Phase 7 section, 01\_DOMAIN\_MODEL.md, and 02\_GLASS\_FRONTEND.md's sections on the metrics panel and visual query builder first — mirror how Phase 6 cross-checked the domain model and Conduit docs rather than working from the build plan alone. Phase 7 covers: `adapters/compute_rustworkx` plus a browser worker tier; degree/betweenness/eigenvector/clustering-coefficient/Leiden/Clique Metric; ComputePort conformance across all three compute tiers on a 5,000-node fixture; the metrics panel (two-metric comparison, size encoding, community hull overlay); a visual query builder compiling to Gremlin with result estimation; hotlists, saved-pattern monitors, an alert inbox; and an access-filtered k-shortest-paths pathfinder.
2. **Refresh the Developer & Operator Guide** once Phase 7 lands — the port/adapter reference table currently has a `adapters/compute_rustworkx` row reading "Phase 7" as a placeholder; update it once that phase closes. Called out explicitly as "small thing, easy to forget."
3. **Build out the demo suite.** Revisit the Scenario C script once Phase 7 lands and ComputePort/`compute_rustworkx` exists — its steps C9–C16 become runnable then. Separately, scope and draft a second scenario modelled on the Panama Papers, requested by Ayan alongside the Enron-modelled Scenario C; nothing exists for it yet (no fixture design, no draft) — start from scratch, following the same synthetic-fixture discipline used for Fixture Corp (structural stats modelled on a real published case, zero real identifiers or content).

## Outstanding known gaps

Two gaps were almost silently dropped this build — both caught only by insistent follow-up questioning, both now resolved, kept here as a cautionary pattern:

- **Witness-statement fixture** — promised at Stage 1 scoping, silently never built ("no good reason for the drop; it was an oversight"). Caught only because the reviewer asked directly where it went. Now built: `tests/scenarios/fixtures/witness_statement.py` (wholly synthetic — invented names, invented prison) and `tests/scenarios/test_witness_statement_extraction.py`. Building it surfaced a real bug: an exact-output assertion was flaky against the live pinned model (3 runs, 3 different entity sets) — fixed to shape-only assertions.
- **OpenSearch-indexing consumer for `ModelPort.embed()`** (spec'd in 03\_CONDUIT\_MIDDLEWARE.md §5.1) — `embed()` got an owner (Phase 6 Stage 1), but the downstream consumer that indexes those embeddings into OpenSearch was only ever "flagged," never assigned. Resolved this session: confirmed no phase claims it, added a new "Gaps with no owning phase" section to 07\_BUILD\_PLAN.md recording it, and distinguished it explicitly from Phase 8's unrelated JanusGraph mixed-index use of OpenSearch (04\_VAULT\_BACKEND.md §1.4) so the two don't get conflated later.

Other disclosed, still-open gaps to keep visible:

- Phase 6 covers entities only — edge/relationship extraction from unstructured material is out of scope by design, not an oversight.
- Ingest Studio's review queue has tested access control (investigation-level and candidate-level `owning_unit` checks) but no studio-specific role layer (source author / source approver / loader) gating who may accept or reject candidates — 09\_INGEST\_STUDIO.md §8 is silent on this; a legitimate spec gap, not a security hole.
- No proactive surface for discovering resolution conflicts — `ResolutionConflict` plus a per-cluster `explain` endpoint make conflicts retrievable, but nothing surfaces which clusters have one unless you already know to check. Left this way deliberately, to avoid building a second review-queue UI the spec never asked for.
- ArcadeDB / Ollama memory contention: reproducible OOM (including at container startup) under heavy concurrent load on a \~7.6GB host VM. Documented as a third dated note in `deploy/compose/dev.yaml`'s arcadedb service, alongside two earlier Phase 5 notes, with a pointer from 07\_BUILD\_PLAN.md's Stage 6 gap list.
- Diarisation (speaker separation) is explicitly out of scope for Phase 6 Stage 2 (raises `NotImplementedError`, disclosed in the build plan).
- Ingest Studio Map stage (Phase 5a) gaps still open in 07\_BUILD\_PLAN.md \~L312–343: the row-template canvas's keyboard-binding path isn't fully wired end to end; Map never proposes a starting template; no synthetic financial fixture built; no second tester review performed.
- CI-cadence note (not a gap, worth re-checking): text/audio conformance runs every PR, vision conformance only on push/merge-to-main — documented in ADR-020's Stage 2 addendum. Worth confirming nothing has quietly widened that gating.
