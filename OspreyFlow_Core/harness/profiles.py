"""Profile-level resource facts, in one place because two paths need them and they had drifted.

**Why this module exists** (round 13bb, 27 September 2026). Two things derive from a profile's own
memory floor, and until now neither derived from it at all — both carried a hand-written number:

- `harness/preflight/memory.py`'s floor check, which owned `LOCAL_LITE_FLOOR_BYTES` privately;
- ArcadeDB's JVM heap, written as the literal `-Xms1G -Xmx6G` in **two** unconnected places,
  `harness/render.py`'s rendered `compose.yaml` and `deploy/compose/dev.yaml`, each with its own
  comment explaining its own history. The renderer's comment says so itself: `dev.yaml` raised its
  heap in Phase 5 "and the renderer did not carry it over, so a rendered deployment was strictly
  worse-configured than the dev stack it replaces, on a value this repository had already paid to
  learn."

The 6 GB in both came from a 10 GiB Docker VM era. The daemon now has 19.5 GiB and the documented
floor is 16 GB, so 6 GB was neither derived from anything current nor large enough — measured
directly on 27 September 2026, and this is the finding that produced this module:

```
ArcadeDB Server started in 'development' mode (CPUs=12 MAXRAM=6.00GB)
java.lang.OutOfMemoryError: Java heap space
Dumping heap to java_pid1.hprof ...
Heap dump file created [3064364881 bytes in 1.375 secs]
Exception in thread "ArcadeDB TransactionManager ospreyflow"
  java.lang.OutOfMemoryError: Java heap space
SEVER [PostCommandHandler] Error on creating index on type 'mx_COMMUNICATED_WITH',
  properties [owning_unit]
```

`07_BUILD_PLAN.md`'s Stage 2a had recorded that last line — the `IndexException` — as the failure
for two rounds. It is the symptom, about twelve seconds downstream; the cause is the line above it,
and nobody had read the server's own log.

**The fraction, and why it is a fraction rather than another literal.** `local-lite` is specified
to run on a 16 GB machine (`05_DEPLOYMENT.md` §1, §3), and ArcadeDB is the largest single consumer
in the stack by a wide margin. Measured at rest on this host, the rest of the dev stack together is
well under a gigabyte (litellm 451MiB, speaches 173MiB, minio 85MiB, postgres 24MiB, valkey
12MiB), with Ollama the one other heavyweight at ~3.5GiB with a model loaded. Half the floor
leaves that comfortably covered and is a number that moves correctly if the floor ever does, which
a literal cannot.

This is **arithmetic from measurements, not a specification quoted from anywhere** — the same
thing `harness/preflight/memory.py`'s own docstring says about its floor, and it is said again here
rather than allowed to read as a requirement.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from schemas.deployment import ResourcesConfig

#: `05_DEPLOYMENT.md` §1 ("One laptop, 16 GB") and §3 ("If Preflight finds less than 16 GB").
LOCAL_LITE_FLOOR_BYTES = 16 * 1024**3

#: Every profile's own memory floor. `cluster` shares `local-lite`'s number because the
#: specification gives no larger one for it, not because it has been checked against it. `small` is
#: a nominal 32 GB server, 30 GiB as Docker reports it (ADR-114 Amendment 33 decision 6 and the
#: owner's answer 16; cloud Small starts at 32 GB, Amendment 10) — the doctor's floor too.
PROFILE_FLOORS: dict[str, int] = {
    "local-lite": LOCAL_LITE_FLOOR_BYTES,
    "small": 30 * 1024**3,
    "cluster": 16 * 1024**3,
    # ADR-148: the same as a cluster's, for the same reason.
    "cloud-platform": 16 * 1024**3,
}

#: ArcadeDB's maximum heap, as a fraction of the profile floor — see this module's own docstring
#: for the measurements behind it.
ARCADEDB_HEAP_FRACTION_OF_FLOOR = 0.5

#: The initial heap. Deliberately not a fraction: `-Xms` only decides how much the JVM commits up
#: front, and a large one makes every container's resting memory look alarming for no benefit. 1G
#: is what both paths already used and there is no measurement asking to change it.
ARCADEDB_INITIAL_HEAP_GIB = 1


def arcadedb_heap_gib(profile: str = "local-lite") -> int:
    """The `-Xmx` value in whole gibibytes. Whole GiB because that is the only unit a human reads
    off a `docker inspect` or a `ps` line without arithmetic, and the fraction is not so finely
    tuned that a rounding would mean anything."""
    return int(PROFILE_FLOORS[profile] * ARCADEDB_HEAP_FRACTION_OF_FLOOR / 1024**3)


def arcadedb_java_memory_opts(profile: str = "local-lite") -> str:
    """The exact `ARCADEDB_OPTS_MEMORY` string both the renderer and `deploy/compose/dev.yaml` use.

    **`-XX:+ExitOnOutOfMemoryError` is not tuning, it is the other half of the round-13bb
    finding.** Measured directly, after the OOM above: `docker inspect` reported the container
    `healthy` and `GET /api/v1/ready` answered `204`, while the transaction manager and async
    flush threads for both open databases were dead and every subsequent `CREATE INDEX` failed.
    ArcadeDB's readiness endpoint is served by a thread that survives a heap OOM, so the
    healthcheck cannot see one. That is what let `docker compose up --wait` and a rendered
    deployment's own `depends_on: service_healthy` both be satisfied by a server that could no
    longer commit a transaction, and it is why `07_BUILD_PLAN.md` Stage 2a recorded "7.22 GiB with
    the container reporting healthy" as a puzzle rather than a dead JVM.

    Exiting on OOM turns an invisible half-death into a container exit, which `restart:
    unless-stopped` then acts on. The heap dump is deliberately kept — it is how this was
    diagnosed — and is written before the exit.
    """
    return (
        f"-Xms{ARCADEDB_INITIAL_HEAP_GIB}G "
        f"-Xmx{arcadedb_heap_gib(profile)}G "
        "-XX:+ExitOnOutOfMemoryError"
    )


# ---- the stores sized to the server (ADR-114 Amendment 33 decision 6) ---------------------------
#
# **Arithmetic, not measurement** — the caveat this module gives its own figures above. The rule
# is the amendment's table: from the memory `M` GiB the server has (as Docker reports it, measured
# once at install and written to `resources.memory_gib`), the graph store's heap 0.4 × M (8 to 31:
# above 31 the JVM loses compressed object pointers), OpenSearch's heap M ÷ 16 (0.5 to 8, `-Xms` =
# `-Xmx`), PostgreSQL's shared buffers M ÷ 32 (0.25 to 4) and its effective cache three times that.
# Each override in `resources` wins. ArcadeDB's page cache is not set: on 26.10.1 it is a quarter of
# the maximum heap unless set (`arcadedb.maxPageRAM`, read from the engine), so it follows.


@dataclass(frozen=True)
class StoreMemory:
    """What the render gives the three stores."""

    graph_heap_gib: int
    search_heap_mib: int
    #: None: the image's own settings (an unsized deployment, as before).
    postgres_shared_buffers_mib: int | None
    postgres_effective_cache_mib: int | None

    @property
    def graph_java_opts(self) -> str:
        return (
            f"-Xms{ARCADEDB_INITIAL_HEAP_GIB}G -Xmx{self.graph_heap_gib}G "
            "-XX:+ExitOnOutOfMemoryError"
        )

    @property
    def search_java_opts(self) -> str:
        return f"-Xms{self.search_heap_mib}m -Xmx{self.search_heap_mib}m"


#: Every store as it was before sizing (decision 6: "Lite is unchanged").
LITE_STORE_MEMORY = StoreMemory(
    graph_heap_gib=int(LOCAL_LITE_FLOOR_BYTES * ARCADEDB_HEAP_FRACTION_OF_FLOOR / 1024**3),
    search_heap_mib=512,
    postgres_shared_buffers_mib=None,
    postgres_effective_cache_mib=None,
)


def _between(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


def store_memory(resources: ResourcesConfig) -> StoreMemory:
    """The stores' memory for `resources`: the rule from `memory_gib`, each override winning, and
    today's values for anything neither names."""
    memory = resources.memory_gib
    graph = (
        resources.graph_heap_gib
        if resources.graph_heap_gib is not None
        else int(_between(math.floor(0.4 * memory), 8, 31))
        if memory is not None
        else LITE_STORE_MEMORY.graph_heap_gib
    )
    search_gib = (
        resources.search_heap_gib
        if resources.search_heap_gib is not None
        else _between(memory / 16, 0.5, 8)
        if memory is not None
        else LITE_STORE_MEMORY.search_heap_mib / 1024
    )
    shared_gib = (
        resources.postgres_shared_buffers_gib
        if resources.postgres_shared_buffers_gib is not None
        else _between(memory / 32, 0.25, 4)
        if memory is not None
        else None
    )
    shared = int(shared_gib * 1024) if shared_gib is not None else None
    return StoreMemory(
        graph_heap_gib=graph,
        search_heap_mib=int(search_gib * 1024),
        postgres_shared_buffers_mib=shared,
        postgres_effective_cache_mib=3 * shared if shared is not None else None,
    )


#: ADR-114 Amendment 43: what a deployment's own PostgreSQL allows at once, from the product's own
#: numbers. Its image's default (100) was rendered until 13 November 2026, and one Conduit holds 49
#: connections at rest (its 48 stores' asyncpg pools at `min_size`) and up to 197 under load (at
#: `max_size`), beside Keycloak, the gateway, Superset and the report sync: a second Conduit was
#: refused (`TooManyConnectionsError`; platform-b's stateless finding).
#:
#: The Conduit's stores' pools at their `max_size`, summed: 197 on 13 November 2026, measured
#: by `tests/harness/test_postgres_connections.py`, which fails when a pool added or grown takes
#: the sum past this, so the number below never silently falls short.
CONDUIT_POOL_CEILING = 200
#: Conduits allowed at their ceiling at once: the one a deployment runs, and a second (a replica,
#: or a worker opening the same stores; a restart's old and new processes overlapping).
CONDUITS_ALLOWED = 2
#: Keycloak 26's own `db-pool-max-size` default, which the render does not change.
KEYCLOAK_POOL_MAX = 100
#: LiteLLM's `database_connection_pool_limit` (10 a worker) for its two, and Superset's
#: SQLAlchemy pool (5 and 10 overflow) for two processes, with the report sync's mart pool (4):
#: allowances, each the client's own default, not measurements.
GATEWAY_POOL_MAX = 20
SUPERSET_AND_REPORT_SYNC_MAX = 40
#: For the owner's `psql`, a backup, and PostgreSQL's own three superuser slots.
OPERATOR_RESERVE = 20
POSTGRES_MAX_CONNECTIONS = (
    CONDUITS_ALLOWED * CONDUIT_POOL_CEILING
    + KEYCLOAK_POOL_MAX
    + GATEWAY_POOL_MAX
    + SUPERSET_AND_REPORT_SYNC_MAX
    + OPERATOR_RESERVE
)


def postgres_command(memory: StoreMemory | None = None) -> list[str]:
    """PostgreSQL's server command: `max_connections` always (ADR-114 Amendment 43), with the sized
    memory settings when the deployment is sized (Amendment 33 decision 6)."""
    command = ["postgres", "-c", f"max_connections={POSTGRES_MAX_CONNECTIONS}"]
    if memory is None or memory.postgres_shared_buffers_mib is None:
        return command
    return [
        *command,
        "-c",
        f"shared_buffers={memory.postgres_shared_buffers_mib}MB",
        "-c",
        f"effective_cache_size={memory.postgres_effective_cache_mib}MB",
    ]
