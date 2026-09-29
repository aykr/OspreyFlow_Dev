# Upstream issues for the ArcadeDB tracker — drafted for the owner to file

**These are drafts, not filed issues.** This project's maker does not open issues, create
accounts, or post to any third-party tracker (`CLAUDE.md` rule 14's own boundary, applied here to
a different account than the project's own repository). The owner files these, or not, at their
own discretion.

**Search done first, and it found neither issue on file.** `firecrawl_search`/`firecrawl_scrape`
against `github.com/ArcadeData/arcadedb` (issues, releases, the `25.5.1` release notes page)
found no existing issue or changelog entry naming a per-database-lifecycle memory retention fix
between `24.11.1` and `25.5.1`, and none naming a readiness endpoint that answers while the
transaction manager is dead. `25.5.1`'s own release notes (fetched directly) list two bug fixes —
a Cypher/JDBC parametric-query fix and a Postgres-driver idle-CPU fix — neither of which matches.
This does not prove no such issue exists; it means this search, run once, did not surface one. If
the owner finds either already tracked, this draft should be closed as a duplicate in favour of
the real issue number, not filed alongside it.

---

## Issue 1 — Server memory is not released across a database's create → drop lifecycle (24.11.1; fixed by 25.5.1)

**Found:** 27 September 2026, this project's round 13bb, while investigating a closing-pass
finding that a rendered `local-lite` deployment's ArcadeDB climbed from 8.651 GiB to 9.396 GiB
across three identical fixture-load runs and never gave memory back.

**Versions:** leaks on `24.11.1` (`ghcr.io/arcadedata/arcadedb` / `arcadedata/arcadedb` Docker
image, tag `24.11.1`). Fixed — or at minimum, no longer reproduces at this scale — by `25.5.1`
(the same image, tag `25.5.1`), which is now this project's pinned version.

**Reproduction — isolated to its smallest form, writing no data and running no query.** Every
cycle is exactly:

```
create_database_if_absent()   # HTTP: POST /api/v1/server, {"command": "create database <name>"}
apply_schema(ontology)        # a fixed, small schema — vertex/edge type definitions only
drop_database()               # HTTP: POST /api/v1/server, {"command": "drop database <name>"}
```

against one running server, repeated with a fresh, uniquely-named database each cycle (never the
same database reused, and the database count on the server is zero at the start and end of every
cycle — `list databases` confirms this). This project's own harness is
`packages/adapters/graph_arcadedb/testing.py`'s per-test database context manager, exercised
`N` times in a loop by `tests/conformance/graph_port/test_suite.py`, one test per cycle.

**JVM options, both versions:** `-Xms1G -Xmx6G` (`24.11.1`, this project's setting at the time)
— the pinned `25.5.1` runs the same reproduction at `-Xms1G -Xmx8G` (this project's current
`local-lite` heap floor). Server RSS was read via `docker stats` on the ArcadeDB container.

**Results — server RSS after N cycles, database count zero throughout:**

| Cycles | `24.11.1` | `25.5.1` |
| --- | --- | --- |
| baseline (0 cycles) | 141.7 MiB | 141.5 MiB |
| 5 | **8.204 GiB** | **1.499 GiB** |
| 10 | 4.618 GiB | 1.512 GiB |
| 15 | 5.608 GiB | 1.514 GiB |
| 20 | 5.459 GiB | **1.516 GiB** |

`24.11.1` has no plateau across the range measured (the 10/15/20 figures are noisy but do not
trend back toward baseline — the server had already been forced through a heap-pressure GC cycle
by cycle 5, which the drop in the 10-cycle figure reflects, not recovery). `25.5.1` plateaus:
1.499 GiB at 5 cycles, 1.516 GiB at 20 — 17 MiB of drift across 15 further cycles, effectively
flat. A wider, real-workload measurement (six sustained-ingest cycles seeding real fixture data
against a rendered deployment, not bare create/drop) shows the same qualitative shape: growth per
cycle roughly halved (123.7 → 61.0 MiB/cycle) and continuing to flatten.

**Raising the heap was measured not to help** on `24.11.1`: the live set simply grew with it —
tested up to `-Xmx7G` on the same host. Bounding `arcadedb.dbPageCacheSize` was tried and also did
not help. Neither lever moved the failure meaningfully; only the version change did.

**What this project did, independent of whether this is filed:** pinned `arcadedata/arcadedb:25.5.1`
everywhere the image is referenced, and separately added `-XX:+ExitOnOutOfMemoryError` (issue 2,
below) so a real exhaustion event is visible rather than silent.

---

## Issue 2 — `/api/v1/ready` answers 204 (healthy) after a heap OutOfMemoryError, with the transaction manager and async flush threads dead

**Found:** the same investigation, immediately downstream of issue 1: raising the heap on
`24.11.1` moved the OOM later rather than preventing it, and observing that OOM directly is what
surfaced this second, independent problem.

**Reproduction:** drive the server to a heap `OutOfMemoryError` (the create/apply_schema/drop
cycle above, run past the point where the JVM exhausts its `-Xmx`, reproduces it) with no JVM
flag that exits or restarts the process on OOM. After the OOM:
- `docker inspect` reports the container `healthy`.
- `GET /api/v1/ready` answers `204 No Content`.
- The transaction manager and async flush threads for every database that was open at the time of
  the OOM are dead.
- Every subsequent write that needs a transaction (measured: `CREATE INDEX`) fails.

**Why this matters beyond the OOM itself:** a container orchestrator's own healthcheck
(`docker compose up --wait`, a rendered deployment's `depends_on: condition: service_healthy`)
is satisfied by a server that can no longer commit a transaction. The failure is invisible at
exactly the layer meant to catch it.

**What this project did about it, independent of whether this is filed:** added
`-XX:+ExitOnOutOfMemoryError` to the same JVM options `-Xmx` is set with
(`harness/profiles.py::arcadedb_java_memory_opts`). This turns the silent half-death into a
process exit, which `restart: unless-stopped` (or the equivalent orchestrator setting) then acts
on — the heap dump ArcadeDB writes before exiting is kept, since it is how this was diagnosed.
This is a mitigation at the deployment layer, not a fix to the readiness endpoint itself: the
underlying gap — a readiness probe that does not check whether transactions can still commit —
remains upstream's to fix or accept.

---

*Both issues are described from the outside — HTTP calls, container observations, JVM flags —
with nothing about ArcadeDB's own internals asserted beyond what the version comparison shows.
Neither issue text below names this project, an owner, a hostname, or any dataset; both are
written to stand alone if pasted into a new GitHub issue.*
