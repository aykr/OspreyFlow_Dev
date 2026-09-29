# OspreyFlow

OspreyFlow is an open-source intelligence analysis and network discovery platform. It ingests
structured records and unstructured material (text, audio, imagery), resolves entities across
sources, persists them in a property graph, and gives an analyst a single workspace in which
network, social-network, pattern, temporal and geospatial analysis are five views of one working
set rather than five separate tools.

Three tiers, separated by four typed ports so any one of them can be swapped without touching the
others:

- **The Glass** — the analyst workspace: canvas, timeline, map, dossier, query.
- **The Conduit** — stateless middleware: API, working-set service, extraction orchestration,
  entity resolution, model routing, access control.
- **The Vault** — persistence and compute: graph store, columnar analytics engine, graph compute
  engine, model servers, object store.

A port is a narrow interface (a Python `Protocol`) that everything above it is allowed to call and
nothing else. Swapping the engine behind a port — a laptop's ArcadeDB for JanusGraph on a cluster,
say — means writing one adapter and changing one line of configuration; nothing above the port
changes, and the adapter is only supported once it passes the same conformance suite every other
adapter behind that port passes. `spec/00_ARCHITECTURE.md` has the full definitions.

## Running it

One command, from a checkout with Docker running:

```
python -m harness.apply
```

This reads `osprey.yaml` at the repository root (the demo/CI configuration — the `local-lite`
profile, tier 1 map providers only) and brings the whole stack up: preflight checks, container
build and start, and a verification pass. `spec/05_DEPLOYMENT.md` has every profile from a laptop
to a cluster and what each one needs.

After that first apply, one screen starts and opens each interface — the Glass, the Ingest Studio
and the Admin console — and shows which are running:

```
make launch
```

It asks you to sign in first and then shows only what your account's roles allow. If OspreyFlow
was set up before the admin account existed, run `make register-sign-in` once.

Once it is up, `DEMO_GUIDE.md` walks through seeding a fixture investigation and the analyst
journey through the Glass.

## Where things are

- **`spec/`** — the binding specification: architecture, domain model, the Glass and Conduit and
  Vault, deployment, the accepted decision log, acceptance scenarios, the Ingest Studio, and the
  design tokens the Glass is built against. This is the product's own documentation, licensed the
  same way the code is.
- **`process/`** — this build's own record: the phased build plan, session handovers, and
  superseded material. Not part of the product; kept for anyone continuing the build, not for
  running or extending OspreyFlow itself.
- **`apps/`, `services/`, `packages/`, `harness/`** — the Glass, the Conduit, the shared schemas
  and port definitions, and the deployment harness `python -m harness.apply` runs.

## Licence

Apache License 2.0 — see `LICENSE`. Copyright 2026 The OspreyFlow Authors; see `NOTICE`.
