"""Stage 2's exit test #1: back up a seeded deployment, destroy it, restore it, prove nothing moved.

`05_DEPLOYMENT.md` §6's last line is the whole reason this file exists — **"A backup nobody has
restored is a hypothesis."** ADR-049's Stage 2 §4 then rewrote the comparison, because the obvious
version of it *"passes while the restore has lost everything that matters"*.

**A live-service test, deliberately.** It needs a real deployment, because every defect it is
written to catch lives in the gap between what a store is documented to do and what it does. Two
already surfaced building it, both of which a mocked store would have hidden: ArcadeDB has no
`V`/`E` supertypes, so the emptiness refusal's first draft returned "empty" for a store holding
1,109 vertices; and record ids are storage addresses reassigned on restore, so a fingerprint that
included them would fail for a perfectly correct restore.

Set-up: point `OSPREY_TEST_COMPOSE_FILE` at a rendered, applied, **seeded** deployment —

    OSPREY_API_PORT=8010 PYTHONPATH=.:packages .venv/bin/python -m harness.apply \\
        --profile local-lite --seed hmp,fixture-corp
    OSPREY_TEST_COMPOSE_FILE=deploy/generated/local-lite/compose.yaml \\
        PYTHONPATH=.:packages .venv/bin/python -m pytest tests/harness/test_restore_exit_test.py

**It destroys that deployment's volumes.** That is the test. Do not point it at anything you want
to keep.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from harness.backup import run_backup
from harness.compare import GraphSnapshot, server_is_ready, take_snapshot, total_records
from harness.restore import RestoreRefused, run_restore

COMPOSE_FILE = os.environ.get("OSPREY_TEST_COMPOSE_FILE")

requires_deployment = pytest.mark.skipif(
    not COMPOSE_FILE,
    reason=(
        "OSPREY_TEST_COMPOSE_FILE is not set. This test needs a real seeded deployment by design — "
        "see the module docstring — and it destroys that deployment's volumes."
    ),
)

DATABASE = "ospreyflow"
ANALYTICS_PATH = "/var/lib/osprey/data/analytics.duckdb"


def _compose_file() -> Path:
    assert COMPOSE_FILE is not None
    return Path(COMPOSE_FILE).resolve()


def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    compose_file = _compose_file()
    return subprocess.run(  # noqa: S603
        [
            "docker",
            "compose",
            "--env-file",
            str(compose_file.parent / "deployment.env"),
            "-f",
            str(compose_file),
            *args,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def _wait_for_arcadedb(timeout_seconds: float = 180.0) -> None:
    """Wait for the *server*, not for the database.

    The first version of this waited for `ospreyflow` to become queryable, which after a
    `down -v` never happens: the database does not exist until something creates it, and on this
    path that something is the restore. Waiting for the thing you are about to create is a wait
    that can only time out.
    """
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if server_is_ready(_compose_file()):
            return
        time.sleep(3)
    raise AssertionError(f"the ArcadeDB server did not answer within {timeout_seconds}s")


@pytest.fixture(scope="module")
def before(tmp_path_factory: pytest.TempPathFactory) -> tuple[GraphSnapshot, Path]:
    """The snapshot of the seeded deployment, and the backup taken from it.

    Module-scoped because taking it is the expensive part and every case below reads the same
    "before". The destroy-and-restore happens in the one case that needs it, not here, so a failure
    in a cheap case does not cost a full rebuild.
    """
    # **The Conduit is stopped first, and the backup is taken with `require_quiesced=True`.**
    # Not a convenience: with it running, the snapshot and the backup are two reads of a moving
    # store, and any difference the comparison later finds cannot be attributed to the restore.
    # That is the whole measurement. A test of a backup has to take the backup the way the backup
    # is meant to be taken.
    stopped = _compose("stop", "api")
    assert stopped.returncode == 0, stopped.stderr

    snapshot = take_snapshot(_compose_file(), database=DATABASE)
    assert snapshot.total_records > 0, (
        "the deployment this test was pointed at holds no records. It must be seeded first — "
        "`python -m harness.apply --profile local-lite --seed hmp,fixture-corp` — or the whole "
        "comparison below is a comparison of two empty stores, which passes and proves nothing"
    )
    directory = run_backup(
        compose_file=_compose_file(),
        out_root=tmp_path_factory.mktemp("backups"),
        profile="local-lite",
        database=DATABASE,
        analytics_container_path=ANALYTICS_PATH,
        require_quiesced=True,
    )
    return snapshot, directory


@requires_deployment
def test_the_seeded_deployment_has_something_worth_restoring(
    before: tuple[GraphSnapshot, Path],
) -> None:
    """**The test that makes every other case non-vacuous**, and the first thing to read when one of
    them fails.

    An empty store restores perfectly into an empty store. Every comparison below would pass. So
    this asserts the fixture actually seeded: both fixtures present, `SAME_AS` edges scored, and —
    ADR-035 §C5 — the three thresholds producing *visibly different* projections. If τ 0.99 and
    τ 0.80 ever collapse to the same partition, the projection comparison stops being able to
    detect a lost score and this is where that shows up.
    """
    snapshot, _ = before

    assert snapshot.type_counts.get("mx_Person", 0) > 400, "the HMP fixture's Person nodes"
    assert snapshot.type_counts.get("mx_SAME_AS", 0) > 0, "Fixture Corp's scored SAME_AS edges"
    assert snapshot.type_counts.get("mx_PRESENT_AT", 0) > 0, "the HMP fixture's sighting edges"

    strict = snapshot.projections["0.99"]
    loose = snapshot.projections["0.80"]
    assert strict != loose, (
        "τ=0.99 and τ=0.80 produce the same resolution projection, so a restore that lost every "
        "SAME_AS score would still compare equal at every threshold. ADR-035 §C5 requires Fixture "
        "Corp to separate these three; it no longer does"
    )
    assert len(loose) >= len(strict), (
        "a lower threshold admits at least as many edges, so it cannot produce fewer clusters — "
        "the projection is computed wrongly"
    )


@requires_deployment
def test_a_corrupt_set_is_refused_before_anything_is_written(
    before: tuple[GraphSnapshot, Path], tmp_path: Path
) -> None:
    """Refusal 1, shown red-then-green in the only way that counts: against a real set.

    **The planted violation takes the shape a real one does** — a file truncated in place, with the
    manifest untouched, which is what a half-finished copy or a full disk leaves behind. Not a
    deleted file, which any code path that opens it would notice anyway.
    """
    _, source = before
    corrupt = tmp_path / "corrupt-set"
    shutil.copytree(source, corrupt)
    manifest = json.loads((corrupt / "manifest.json").read_text(encoding="utf-8"))
    victim = corrupt / next(e["path"] for e in manifest["files"] if e["item"] == "graph")
    data = victim.read_bytes()
    victim.write_bytes(data[: len(data) // 2])

    with pytest.raises(RestoreRefused) as refused:
        run_restore(
            directory=corrupt,
            compose_file=_compose_file(),
            database=DATABASE,
            analytics_container_path=ANALYTICS_PATH,
            acknowledged=True,
        )
    assert "checksum mismatch" in str(refused.value)


@requires_deployment
def test_restoring_into_a_populated_store_is_refused(
    before: tuple[GraphSnapshot, Path],
) -> None:
    """Refusal 2, and ADR-049's third named hole: *"nothing in the stated test distinguishes a
    restore into an empty store from a no-op against the source store."*

    Run before the destroy, so the store this refuses against is the real populated one.
    """
    _, directory = before

    with pytest.raises(RestoreRefused) as refused:
        run_restore(
            directory=directory,
            compose_file=_compose_file(),
            database=DATABASE,
            analytics_container_path=ANALYTICS_PATH,
            acknowledged=True,
        )
    assert "not empty" in str(refused.value)


@requires_deployment
def test_the_dry_run_writes_nothing_and_must_be_acknowledged(
    before: tuple[GraphSnapshot, Path],
) -> None:
    """Amendment 11. `acknowledged=False` returns the plan and touches the deployment not at all —
    asserted by taking a snapshot either side of it, not by trusting the code path."""
    _, directory = before
    was = take_snapshot(_compose_file(), database=DATABASE)

    plan = run_restore(
        directory=directory,
        compose_file=_compose_file(),
        database=DATABASE,
        analytics_container_path=ANALYTICS_PATH,
        acknowledged=False,
    )
    assert plan.total_bytes > 0
    assert plan.projected_seconds > 0
    # §6's audit exception has to reach the operator's eyes at the moment they decide, not only
    # the manifest. The dry run is that moment.
    assert "not" in plan.audit_statement and "audit_log" in plan.audit_statement

    now = take_snapshot(_compose_file(), database=DATABASE)
    assert not was.differences_from(now), "a dry run changed the deployment"


@requires_deployment
def test_backup_destroy_restore_preserves_everything_that_matters(
    before: tuple[GraphSnapshot, Path],
) -> None:
    """**Exit test #1.** The one that destroys the deployment.

    The comparison is `GraphSnapshot.differences_from`, which is deep by construction: per-type
    record counts, whole-record fingerprints for every node and edge (handling markings, provenance
    states, audit blocks and `SAME_AS` scores included), the resolution projection at each of
    ADR-035 §C5's three thresholds, and a fixed query sample. ADR-049 named three holes in the
    original test and each maps to one of those.
    """
    expected, directory = before

    destroyed = _compose("down", "-v", "--remove-orphans")
    assert destroyed.returncode == 0, destroyed.stderr

    started = _compose("up", "-d", "--wait", "arcadedb", "postgres", "objectstore")
    assert started.returncode == 0, started.stderr
    # **The Conduit's container has to exist, and must not be running.** Exist, because the restored
    # analytics DuckDB is copied into its data volume and `docker compose cp` addresses a container,
    # not a volume — without this the restore fails with `no container found for service "api"`,
    # which is the shape of the deployment a restore is always run against. Not running, because the
    # Conduit's own `AnalyticsPort` holds an exclusive lock on that file: the same constraint that
    # makes the seed stop it, for the same reason.
    created = _compose("create", "--no-recreate", "api")
    assert created.returncode == 0, created.stderr
    _wait_for_arcadedb()

    # The store must be empty *before* the restore, or this test cannot tell a restore from a no-op.
    assert total_records(_compose_file(), DATABASE) == 0, (
        "the destroyed deployment came back with records in it, so whatever this test measures "
        "afterwards is not evidence that the restore did anything"
    )

    began = time.monotonic()
    run_restore(
        directory=directory,
        compose_file=_compose_file(),
        database=DATABASE,
        analytics_container_path=ANALYTICS_PATH,
        acknowledged=True,
    )
    elapsed = time.monotonic() - began

    restored = take_snapshot(_compose_file(), database=DATABASE)
    differences = restored.differences_from(expected)
    assert not differences, "the restored deployment differs:\n  " + "\n  ".join(differences)
    assert restored.total_records == expected.total_records
    print(f"\nexit test #1: {expected.total_records} record(s) restored in {elapsed:.0f}s")


@requires_deployment
@pytest.mark.parametrize(
    ("mutation", "expected_signal"),
    [
        ("drop-handling", "node multiset differs"),
        ("alter-same-as-score", "resolution projection"),
        ("drop-one-edge", "edge multiset differs"),
        ("drop-one-node", "type mx_Person"),
    ],
)
def test_the_comparison_detects_each_class_of_loss(
    before: tuple[GraphSnapshot, Path], mutation: str, expected_signal: str
) -> None:
    """`CLAUDE.md` rule 15, four times over, against the snapshot the exit test actually compares.

    Each mutation is applied to a **copy of the real snapshot**, in the shape the corresponding loss
    would leave behind, and each must produce its own signal. Two of the four exist because ADR-049
    said the original test would pass through them:

    - `drop-handling` — a restore that lost every marking. Multiset-of-identities: unchanged.
      Access on the restored deployment: silently widened. This is hole 1.
    - `alter-same-as-score` — a restore that kept every edge and lost its score. Multiset of
      node/edge *pairs*: unchanged. Every resolution projection: different. This is hole 2.
    - `drop-one-edge` and `drop-one-node` are the ordinary losses, here because a test that caught
      only the subtle ones would be a strange test to trust.

    Run after the restore, against the restored snapshot, so the thing being mutated is the thing
    the exit test passed on.
    """
    expected, _ = before
    restored = take_snapshot(_compose_file(), database=DATABASE)
    assert not restored.differences_from(expected), (
        "this case runs after the restore and assumes it succeeded; it did not"
    )

    if mutation == "drop-handling":
        damaged = GraphSnapshot(
            type_counts=dict(restored.type_counts),
            node_fingerprints=[
                json.dumps(
                    {
                        k: v
                        for k, v in json.loads(f.split("|", 1)[1]).items()
                        if not k.startswith("handling")
                    },
                    sort_keys=True,
                )
                for f in restored.node_fingerprints
            ],
            edge_fingerprints=list(restored.edge_fingerprints),
            projections=dict(restored.projections),
            query_sample=dict(restored.query_sample),
        )
    elif mutation == "alter-same-as-score":
        # Every score pushed below the strictest threshold: the edges all survive, and the
        # projection at τ=0.99 empties.
        damaged = GraphSnapshot(
            type_counts=dict(restored.type_counts),
            node_fingerprints=list(restored.node_fingerprints),
            edge_fingerprints=list(restored.edge_fingerprints),
            projections={**restored.projections, "0.99": []},
            query_sample=dict(restored.query_sample),
        )
    elif mutation == "drop-one-edge":
        damaged = GraphSnapshot(
            type_counts=dict(restored.type_counts),
            node_fingerprints=list(restored.node_fingerprints),
            edge_fingerprints=restored.edge_fingerprints[1:],
            projections=dict(restored.projections),
            query_sample=dict(restored.query_sample),
        )
    else:
        counts = dict(restored.type_counts)
        counts["mx_Person"] = counts["mx_Person"] - 1
        damaged = GraphSnapshot(
            type_counts=counts,
            node_fingerprints=list(restored.node_fingerprints),
            edge_fingerprints=list(restored.edge_fingerprints),
            projections=dict(restored.projections),
            query_sample=dict(restored.query_sample),
        )

    differences = restored.differences_from(damaged)
    assert differences, f"the comparison did not notice {mutation}"
    assert any(expected_signal in problem for problem in differences), (
        f"{mutation} was noticed, but not as {expected_signal!r}: {differences}"
    )
