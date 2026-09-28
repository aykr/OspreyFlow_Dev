# OspreyFlow — System Specification Pack

Version 1.1 · Architecture baseline for implementation by Claude Code. Supersedes the v1.0 draft,
which predated the Gemini architecture specification and was folded into this folder at the start
of the project. This pack is the only copy; there is no separate v1.0 to consult.

OspreyFlow is an open-source intelligence analysis and network discovery platform. It ingests
structured records and unstructured material (text, audio, imagery), resolves entities across
sources, persists them in a property graph, and gives analysts a single workspace in which
network, social-network, pattern, temporal and geospatial analysis are five views of one working
set rather than five separate tools.

## Tier naming

The three-tier naming from the Gemini specification is adopted verbatim and used throughout:

- **The Glass** — presentation. The analyst workspace: canvas, timeline, map, dossier, query.
- **The Conduit** — orchestration. Stateless middleware: API, working-set service, extraction
  orchestration, entity resolution, model routing, access control.
- **The Vault** — persistence and compute. Graph store, columnar analytics engine, graph compute
  engine, model servers, object store.

### What "separated by four named ports" means

A port is a narrow interface — a Python `Protocol` in `packages/ports/` — that everything above
it is allowed to call, and nothing else. There are four: `GraphPort` (persist and traverse the
graph), `AnalyticsPort` (columnar aggregation over events), `ComputePort` (graph algorithms) and
`ModelPort` (language, speech and vision inference). Full definitions are in
`00_ARCHITECTURE.md` §2.

The consequence, worked through on a real case. Suppose you start on a laptop with ArcadeDB and
two years later need JanusGraph on a Scylla cluster.

- The Conduit never calls ArcadeDB. It calls `GraphPort.expand(request, principal)`.
- Switching engines means writing `adapters/graph_janusgraph`, a class implementing those same
  method signatures, and changing one line in `osprey.yaml`.
- Nothing in the Conduit changes. Nothing in the Glass changes. The API contracts, the working
  set, the access filter, the UI — all untouched, because none of them ever knew which engine
  was behind the port.
- The new adapter is only *supported* once `tests/conformance/graph_port/` passes against it.
  That suite is the same set of tests ArcadeDB passes, so "swappable" is a property the build
  verifies rather than a claim in a document.

The counter-example is what this prevents. If the Conduit built Gremlin strings inline, or the
Glass held a node identifier that happened to be an ArcadeDB RID, the same migration would touch
hundreds of call sites and the frontend, and you would discover the breakages during an
investigation rather than in CI.

"The ports are the architecture; everything else is a current default" means the commitments
worth defending are the four interfaces and their conformance suites. ArcadeDB, JanusGraph,
DuckDB, ClickHouse, rustworkx, Ollama and vLLM are today's best answers behind those interfaces,
and each is expected to be replaced at some point without that being a re-architecture.

## Reading order

| File | Purpose |
| --- | --- |
| `00_ARCHITECTURE.md` | Tier model, the four swap ports, quality attributes, licence register |
| `01_DOMAIN_MODEL.md` | Ontology, graph schema, provenance, confidence, handling markings, audit |
| `02_GLASS_FRONTEND.md` | Workspace layout, the five analytical capabilities, design-system binding |
| `03_CONDUIT_MIDDLEWARE.md` | API contracts, working-set service, extraction and resolution pipelines |
| `04_VAULT_BACKEND.md` | Graph store, analytics engines, model gateway, port conformance suites |
| `05_DEPLOYMENT.md` | Deployment profiles from laptop to cluster, the setup harness, plain-English runbook |
| `06_DECISIONS.md` | Architecture decision records, including those that overturn the input documents |
| `07_BUILD_PLAN.md` | Phased milestones with acceptance criteria |
| `08_ACCEPTANCE_SCENARIOS.md` | Two end-to-end analyst journeys used as the functional test |
| `09_INGEST_STUDIO.md` | The visual POLE mapping harness, connector catalogue, review queue |
| `design/tokens.css` | Design tokens extracted verbatim from the brand foundations |
| `DEMO_GUIDE.md` | Bringing up a demo environment, the analyst walkthrough, and what is not yet demonstrable |
| `NEXT_STEPS_PHASE7.md` | Sequencing and session prompts for the work after Phase 6 |
| `SESSION_HANDOVER.md` | The current handover (Phase 6 → Phase 7). The 14 September original is `archive/SESSION_HANDOVER.md` |
| `DESIGN_PROVENANCE.md` | How the decisions in this pack were arrived at, and what remains untested |
| `archive/` | Superseded documents, retained for reference only. See `archive/README.md` |

## Source documents reconciled by this pack

Five inputs were supplied. They do not fully agree. This pack takes a position where they
conflict, and every override is recorded as an ADR in `06_DECISIONS.md` rather than applied
silently.

1. **Open-Source Multimodal Graph Analysis Tool — Research Brief.** The three-tier stack
   proposal. Adopted in shape. Two component choices overturned: ADR-002 (renderer),
   ADR-005 (extraction framework).
2. **Intelligence_Platform_Architecture_Specs.docx (Gemini).** The detailed architecture.
   Adopted as the spine, including the Glass/Conduit/Vault naming, LiteLLM, Splink,
   ArcadeDB/JanusGraph, DuckDB/ClickHouse and Compose profiles. Five corrections applied:
   ADR-002, ADR-004 (Redis licence), ADR-006 (entity resolution timing), ADR-009 (node
   colour), ADR-011 (cluster profile delivery).
3. **advanced_crime_analytics_ai_spec_v2.docx.** A prior feature specification. Its
   capabilities are adopted and restated as requirements. Its grounding — vendor demo videos
   and the named individuals in them — is dropped. Its node colour scheme is overruled by the
   OspreyFlow design system (ADR-009).
4. **CoLP_Demo_Presentation_V017.pptx.** The mobile-device and CDR analytical journey. Source
   of acceptance scenario B, and of the hotlist alerting, identifier standardisation and
   duplicate-CDR requirements.
5. **HMP_Hollywood_Report_v1_0.pdf.** A worked intelligence product. Source of acceptance
   scenario A, and of the handling-marking, source-evaluation and probability-yardstick
   requirements that none of the other inputs model.

## Non-negotiable constraints

Every recommendation is tested against these five. A component that fails one is not in the
pack, whatever its technical merit.

- **Open source, no licence trap.** OSI-approved licences only. Nothing under BSL, SSPL, RSAL,
  the Elastic Licence, or an open-core split that puts a needed capability behind a paid tier.
- **Scalable at both ends.** The Glass serves a large concurrent user base and holds a working
  set in memory for interactive analysis; the Vault scales with data volume independently.
- **Maintainable.** Every runtime component patchable on its own cadence. No component may pin
  another's major version.
- **Flexible on models.** Changing the language, speech or vision model is a configuration edit.
- **Transportable.** One command on a laptop; the same images and configuration model on a
  multi-machine cluster, with no foreclosed migration paths.
