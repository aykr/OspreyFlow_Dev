# MantisNexus — design provenance

How the architecture in `docs/` was arrived at: what was proposed, what was challenged, what
changed, and why. The specification states the decisions; this records the reasoning behind them
and the order in which it happened.

Written 14 September 2026, covering the period from the initial brief to the start of Phase 3.

---

## 1. The inputs, and what each was worth

Five documents were supplied at the outset, and a sixth arrived during authoring.

| Input | What it contributed | What was set aside |
| --- | --- | --- |
| Open-Source Multimodal Graph Analysis Tool — Research Brief | The three-tier shape, the open-source constraint, the TinkerPop direction | Cytoscape.js as renderer, LlamaIndex/LangChain as the orchestration core |
| `advanced_crime_analytics_ai_spec_v2.docx` | The feature set, restated as requirements | Its grounding in vendor demo videos, and its node colour scheme |
| `CoLP_Demo_Presentation_V017.pptx` | The mobile-device and CDR analytical journey; hotlist alerting; identifier standardisation | — |
| `HMP_Hollywood_Report_v1_0.pdf` | Handling codes, source evaluation, the probability yardstick, intelligence gaps, assumptions | — |
| `MantisNexus_Brand_Foundations.html` | The complete design system: nine data channels, provenance strokes, type, motion | — |
| `Intelligence_Platform_Architecture_Specs.docx` (Gemini), arrived mid-authoring | The Glass/Conduit/Vault naming, LiteLLM, Splink, ArcadeDB→JanusGraph, DuckDB→ClickHouse, the harness concept | Five specific choices, corrected below |

The HMP report turned out to be the most consequential input and the one the other documents
most neglected. It is not a graph — it is an *assessment*: judgements stated against a
probability yardstick, each resting on named evidence, with intelligence gaps and assumptions
listed explicitly, and handling, action and sanitisation codes on its face. None of the other
inputs modelled any of that. It became ADR-010 and the assessment objects in `01_DOMAIN_MODEL.md`
§5, and it is the clearest answer to what distinguishes this from a graph viewer.

---

## 2. The seven overrides

The Gemini specification was adopted as the spine. Seven things in the supplied documents were
overturned, each recorded as an ADR rather than silently changed.

**ADR-002 — Sigma.js as the only renderer.** Both the brief and the Gemini spec nominated
Cytoscape.js; the latter added a WebGL fallback above 10,000 nodes. Shipping two renderers means
implementing every node state twice — nine channels, three provenance strokes, six interaction
states — and keeping them pixel-identical, or the picture changes when an analyst crosses a
threshold they cannot see. One renderer, and the one with the higher ceiling.

**ADR-004 — Valkey not Redis, OpenSearch not Elasticsearch.** The Gemini spec correctly rejected
FalkorDB for SSPL, then specified Redis for the cache and Elasticsearch as the JanusGraph index.
Both are under licences that fail the open-source constraint the same document sets. An internal
inconsistency rather than a judgement call.

**ADR-005 — No orchestration framework in the extraction core.** The brief nominated LlamaIndex
or LangChain. Both carry large transitive dependency trees and a history of breaking changes,
which puts the extraction pipeline's upgrade cadence under someone else's control — against the
stated maintainability requirement. The actual need is a hundred lines: send a document and a
JSON Schema, get conforming structured output. What is genuinely hard — prompt quality, schema
design, evaluation — no framework solves.

**ADR-006 — Entity resolution is a projection, never a merge.** The Gemini spec stated that
records are merged into golden records before insertion, while separately requiring an
analyst-adjustable matching threshold. The two cannot both hold: merging at ingest fixes the
threshold at ingest. The deeper problem is that a merge cannot be undone, and a wrong merge in an
intelligence system silently attributes one person's activity to another with no signal that it
happened. This is the decision that most shaped the data model.

**ADR-009 — The design system governs colour.** The v2 spec assigned orange, red and purple to
source type and threat level, and the Gemini spec carried it forward. The scheme puts two
orthogonal dimensions on one channel, so a structured-source node that is also peripheral has no
valid colour — it fails on the first real dataset. It also leaves entity type unencoded, which is
what an analyst most needs at a glance across ten thousand nodes.

**ADR-011 — Three profiles, and the cluster profile is not Compose.** Compose profiles are the
right mechanism on one host and not an orchestrator: no scheduling, no rolling update, no
autoscaling. Separately, the gap between one laptop and ten machines is too wide to cross in one
step, so a `small` profile was added — three machines in a room is usually the first real
deployment.

**ADR-014 — MapLibre GL JS, not Leaflet.** Surfaced by a question about how maps render. The
binding constraint is that the graph canvas must draw *over* the map in the same projection, with
one camera. `@sigma/layer-maplibre` gives that because both are WebGL; Leaflet would mean
reconciling two camera models by hand in the interaction analysts use most.

---

## 3. What the review pass added

Eighteen decision records were reviewed and accepted in sequence. Four of them changed during
that review rather than being accepted as written.

**ADR-003 gained a GQL amendment.** The question "can this also support Graph Query Language?"
produced the honest answer: architecturally yes, practically not yet — GQL is ISO/IEC 39075:2024
but has no open-source implementation in the candidate set, and openCypher is the on-ramp the
industry is actually using. The cheap insurance was taken immediately: adapters declare a
`dialects` capability and the query builders stay dialect-agnostic, so a second dialect becomes a
`render()` method rather than a project.

**ADR-011 gained the harness-controlled switch.** A question about minimising CLI error produced
five guards: target confirmation, drift detection, change preview, enforced backup-before-switch,
and a downgrade capacity check against the existing data volume.

**ADR-002 was accepted conditionally on zoom behaviour**, which produced `02_GLASS_FRONTEND.md`
§1.1 — four zoom bands driven by `nodeReducer`/`edgeReducer`, and the rule that zoom never
changes what exists, only what is drawn.

**ADR-018 was accepted provisionally on an interface review**, which produced an explicit split
between what that review can change freely (layout, binding interaction, whether the row template
is a canvas at all) and what it cannot (the recipe as a versioned file, one record mapping to a
graph of elements, POLE-first, no scripting language).

Four capabilities were added during the review that were not in any input document:

- **Geospatial provider tiers and profiles** (ADR-015, ADR-016), prompted by asking whether the
  mapping engine could be swapped. This produced the tier model with OpenStreetMap as a shipped
  default that needs no procurement, and the recognition that licensing across a client base is a
  technical constraint on the product rather than a procurement matter.
- **UK and US targeting** (ADR-017), which made reprojection mandatory rather than an edge case —
  neither country's authoritative data arrives in the projection the tiles use. It also surfaced
  that the US has no AddressBase equivalent, which is why `Location` is keyed on a ULID with
  UPRN, GNIS and TIGER identifiers held as aliases.
- **The Ingest Studio** (ADR-018), prompted by noticing ingestion had no visual harness. This
  produced the row-template model — one record becomes a graph of elements, not a flat field set —
  and POLE as an upper ontology over the nine concrete entity types.
- **The browser-based harness**, replacing a CLI, which then made the admin console the natural
  home for provider registration, upgrades and verification for the life of a deployment.

---

## 4. What the build found

Three phases in, the pattern has been consistent: the end-of-phase audit finds a real defect every
time, and roughly half are specification defects rather than implementation ones.

| Found in | Defect | Whose |
| --- | --- | --- |
| Phase 0 plan | Phase 0's exit criterion ("CI green") contradicted its own scope bullet ("suites fail loudly") | Specification |
| Phase 0 plan | `LGPL-3.0 (dynamic linking only)` cannot be enforced by the named tooling | Specification |
| Phase 1 build | `neighbourhood_stats` had no `Principal`, so degree counts could not be access-filtered | Specification |
| Phase 1 audit | `upsert_edges` never merged same-pair edges; the conformance suite passed anyway | Implementation |
| Phase 1 audit | Round-trip test checked only `node.type`, hiding every property-level defect | Implementation |
| Phase 2 plan | `AnalyticsPort.raw_sql` took no `Principal` — an unfilterable hole through the handling model | Specification |
| Phase 2 audit | `dayfirst=True` default in the datetime normaliser, with both the UK and US in scope | Specification gap |
| Phase 2 audit | Deduplication hashed raw strings rather than canonicalised values | Implementation |
| Phase 2 audit | Geometry stored on the `Location` node rather than the analytics store | Implementation |
| Phase 2 audit | Staging ran *after* normalisation, defeating its own stated purpose | Specification |
| Masking fix | A justification sentence survived a change to the mechanism it justified | Specification |

Two of these deserve note. The **staging order** defect would have surfaced in Phase 6, when
someone tried to re-extract and found only normalised values staged — by which point months of
data would have been staged the wrong way. The **`upsert_edges`** defect is the clearest argument
for the audit habit: a green conformance suite proved nothing because no test wrote the same pair
twice, and the prose invariant was never exercised.

---

## 5. Process conclusions

**Plan mode before code, every phase.** Most of the value has come from reviewing plans rather
than reviewing code. Three defects were caught before a line was written.

**Answer ambiguity by fixing the specification, not the conversation.** When Claude Code surfaces
a gap, an answer given only in chat is lost by the next phase. Every such answer became an edit to
`docs/`.

**The repository is the source of truth, and a reviewing session must not hold a copy.** Two
regressions came from applying whole-file replacements that reverted corrections made repo-side.
The rule now in `CLAUDE.md` catches it; the reliable fix is targeted edits.

**Documentation drifts from mechanism.** The recurring failure is prose written to justify one
design surviving an amendment to that design, so it now argues for something the code no longer
does. Worth checking explicitly whenever a mechanism changes.

---

## 6. What has not been tested

Recorded so it is not mistaken for settled.

- **No analyst has used any of it.** The Ingest Studio prototype was built in Phase 2 precisely so
  an analyst could react to it early, and that review has not happened. Everything about the
  interface remains a well-reasoned guess.
- **No real data has passed through.** All fixtures are synthetic and seeded, by design, but the
  normalisers in particular will meet cases the golden files do not anticipate.
- **The swap boundary has one adapter per port.** "Swappable" is proved by conformance suites that
  have so far been run against a single implementation. The claim is not tested until JanusGraph
  and ClickHouse adapters exist in Phase 8.
