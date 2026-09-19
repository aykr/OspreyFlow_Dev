# MantisNexus — naming and brand brief

*Prepared as background for renaming research. Scope note at the end marks what's genuinely open
versus what would be expensive to change.*

## What MantisNexus is

An open-source intelligence analysis and network discovery platform. It ingests structured
records and unstructured material (text, audio, imagery), resolves entities across sources,
persists them in a property graph, and gives analysts a single workspace where network,
social-network, pattern, temporal and geospatial analysis are five views of one working set
rather than five separate tools. Primary users are law-enforcement/intelligence analysts; the
domain vocabulary is POLE (Person, Object, Location, Event).

## Current naming — brand-facing

These are presentation-layer names, not code structure. Changing them touches documentation,
UI copy and marketing surfaces, not the codebase's internal contracts.

- **MantisNexus** — the umbrella/product name.
- **Mantis** — the sub-mark shown to analysts inside the workspace itself, and on every
  export manifest ("the Mantis mark, the investigation reference, the export timestamp...").
- **Nexus** — the sub-mark shown on the administrative console (`/admin`) — provider
  registration, gazetteer loading, upgrades, verification. Deliberately a separate mark from
  Mantis: "from inside the workspace the data layer is plumbing, not a brand."

## Current naming — visual identity

Extracted from a separate brand-foundations document (not itself in the research scope; this
is what's downstream of it):

- Dark theme is the working default; light is a separately tuned palette for screenshots/print,
  not a simple inversion.
- One accent colour ("brass") carries every primary action, focus ring and selection state, and
  is excluded from the data palette so it's never confused with an entity-type colour.
- Nine hue channels for entity types, each paired with a distinct shape — colour is never the
  sole carrier of a distinction (an accessibility requirement, not a style choice).
- Provenance is encoded as stroke style (solid/dashed/dotted), not colour.
- Typography: a humanist sans for interface text, a monospace face for every identifier, hash,
  timestamp and numeric value — chosen for legibility of easily-confused characters (`1 l I`,
  `0 O`), not aesthetics.

## Current naming — architecture layers (structural, load-bearing)

These names are used as a deliberate metaphor across the specification, and by now are load-bearing
in code, tests and decision records — not just documentation. Included here for completeness and
so any brand-name research doesn't accidentally recommend touching them, but the working
assumption is these stay as they are:

- **The Glass** — the presentation tier (analyst workspace: canvas, timeline, map, query).
- **The Conduit** — the stateless middleware tier (API, working-set orchestration, access
  control, audit).
- **The Vault** — the persistence/compute tier (graph store, analytics engine, model serving).
- Four **ports** (named interfaces between tiers): `GraphPort`, `AnalyticsPort`, `ComputePort`,
  `ModelPort`.
- Supporting terms-of-art in the same category: the **Working-Set Service**, **POLE**, **recipe**
  / **row template** (data-ingestion mapping artifacts), **Knowledge Adapters**, `AuditStub`.

## Scope for this research

Open to reconsideration: the **MantisNexus / Mantis / Nexus** naming scheme itself — is the name
distinctive, memorable, and clear about what the product does; does the Mantis/Nexus split read
as intentional or confusing; are there conflicts (trademark, naming collisions with existing
products) worth knowing about before further investment in this name.

Out of scope: the Glass/Conduit/Vault tier metaphor and the port names — these are structural
and referenced throughout the codebase, ADRs and test suite; changing them is a large, separate
engineering exercise regardless of any branding conclusion, so the recommendation is to keep
research focused on the product/company name and its public-facing marks.

## My own notes

*(space for your own thoughts before sending this along)*

-
-
-
