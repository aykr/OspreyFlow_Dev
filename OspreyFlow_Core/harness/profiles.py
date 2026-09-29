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

#: `05_DEPLOYMENT.md` §1 ("One laptop, 16 GB") and §3 ("If Preflight finds less than 16 GB").
LOCAL_LITE_FLOOR_BYTES = 16 * 1024**3

#: Every profile's own memory floor. `small` and `cluster` share `local-lite`'s number because the
#: specification gives no larger one for them, not because it has been checked against either.
PROFILE_FLOORS: dict[str, int] = {
    "local-lite": LOCAL_LITE_FLOOR_BYTES,
    "small": 16 * 1024**3,
    "cluster": 16 * 1024**3,
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
