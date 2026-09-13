# Graph Report - mantisnexus  (2026-09-13)

## Corpus Check
- 7 files · ~4,054 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 3 file(s) not represented in the graph (top: (none) 3)

## Summary
- 37 nodes · 31 edges · 6 communities
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `9a213dcc`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Handing the pack to Claude Code
- MantisNexus
- MantisNexus — System Specification Pack
- MantisNexus
- Prompts

## God Nodes (most connected - your core abstractions)
1. `Handing the pack to Claude Code` - 9 edges
2. `MantisNexus` - 6 edges
3. `MantisNexus` - 5 edges
4. `Prompts` - 5 edges
5. `MantisNexus — System Specification Pack` - 5 edges
6. `Tier naming` - 2 edges
7. `The specification is in `docs/` and it is binding` - 1 edges
8. `Rules that hold in every session` - 1 edges
9. `Conventions` - 1 edges
10. `Before you write code` - 1 edges

## Surprising Connections (you probably didn't know these)
- None detected - all connections are within the same source files.

## Communities (6 total, 0 thin omitted)

### Community 0 - "Handing the pack to Claude Code"
Cohesion: 0.20
Nodes (9): Handing the pack to Claude Code, Order of work, Session hygiene that matters for this project specifically, Step 1 — Create the repository and drop the pack in, Step 2 — Add `CLAUDE.md` at the repository root, Step 3 — Add the phase commands, Step 4 — Start in plan mode, one phase per session, Step 5 — Clear between phases (+1 more)

### Community 1 - "MantisNexus"
Cohesion: 0.29
Nodes (6): Before you write code, Conventions, graphify, MantisNexus, Rules that hold in every session, The specification is in `docs/` and it is binding

### Community 2 - "MantisNexus — System Specification Pack"
Cohesion: 0.29
Nodes (6): MantisNexus — System Specification Pack, Non-negotiable constraints, Reading order, Source documents reconciled by this pack, Tier naming, What "separated by four named ports" means

### Community 3 - "MantisNexus"
Cohesion: 0.33
Nodes (5): Before you write code, Conventions, MantisNexus, Rules that hold in every session, The specification is in `docs/` and it is binding

### Community 4 - "Prompts"
Cohesion: 0.33
Nodes (5): 1. Kickoff — run once, in plan mode, 2. The `/phase` command, 3. Prompts worth having ready, 4. Two things not to do, Prompts

## Knowledge Gaps
- **25 isolated node(s):** `The specification is in `docs/` and it is binding`, `Rules that hold in every session`, `Conventions`, `Before you write code`, `graphify` (+20 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 31 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What connects `The specification is in `docs/` and it is binding`, `Rules that hold in every session`, `Conventions` to the rest of the system?**
  _25 weakly-connected nodes found - possible documentation gaps or missing edges._