"""A deep snapshot of a deployment's graph store, for the restore exit test.

ADR-049's Stage 2 §4 rewrote the exit test because the original one *"passes while the restore has
lost everything that matters"*. Its three named holes are the three reasons this module exists
rather than a `count(*)` comparison:

1. **Handling, provenance and assessment objects are first-class (ADR-010) and are what the adapter
   filters on (`CLAUDE.md` rule 3).** A restore that dropped every `handling` marking would pass a
   multiset comparison unchanged — and would silently widen access on the restored deployment. So
   the node and edge fingerprints carry the whole marking, not the identity.
2. **`SAME_AS` edges are scored and resolution is a query-time projection over those scores
   (ADR-006).** A multiset of node/edge *pairs* that ignores edge properties passes while every
   projection changes. So this compares the **projections** at τ 0.99, 0.95 and 0.80 — the three
   ADR-035 §C5 already requires Fixture Corp to make visibly different — as well as the edges.
3. **The target store must be asserted empty.** Handled in `harness/restore.py`'s own refusal 2;
   `type_record_counts` is what that refusal is measured with, and what makes "the restore was a
   no-op against the source store" distinguishable from a real restore.

## Why this talks to ArcadeDB directly rather than through `GraphPort`

Deliberately, and it is the only place in this repository that does. `GraphPort`'s implementations
apply access control (rule 3) and collapse `SAME_AS` at query time (rule 6) — both correct, and both
of them things that would hide exactly the losses this comparison exists to detect. A restore that
dropped a `SECRET` node would be invisible through a port that was already filtering it out for the
comparing principal. The snapshot has to see the store as it is, which means below the port.

That is also why nothing here belongs in the Conduit: this is an operator tool reading an operator's
own store during a rehearsal, not a read path an analyst reaches. It is not wired into any route.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from harness.backup import BackupFailed, _compose, _env_value

#: ADR-035 §C5's own three. Not a range and not a parameter: these are the values Fixture Corp is
#: built to separate, so a projection that stopped differing between them would itself be a finding.
RESOLUTION_THRESHOLDS: tuple[float, ...] = (0.99, 0.95, 0.80)

#: Dropped from every fingerprint. ArcadeDB record ids are storage addresses, not identity — they
#: are assigned by the engine as records land in buckets, and comparing them would make this test
#: fail for a restore that was perfectly correct. Every other field is compared, timestamps
#: included: the same data restored is the same data, and a differing `created_at` means something
#: rewrote it.
VOLATILE_FIELDS = frozenset({"@rid", "@in", "@out", "@cat", "@bucket"})


class SnapshotFailed(RuntimeError):
    pass


def _query(compose_file: Path, database: str, sql: str) -> list[dict[str, Any]]:
    """One SQL query against the store, through the container's own loopback.

    `curl` inside the container rather than a published port, for the same reason the seed runs
    there: `05_DEPLOYMENT.md` §7 puts the graph store on an internal network and a comparison tool
    is not a reason to publish it.
    """
    password = _env_value(compose_file.parent / "deployment.env", "OSPREY_ARCADEDB_PASSWORD")
    body = json.dumps({"language": "sql", "command": sql})
    completed = subprocess.run(  # noqa: S603
        _compose(compose_file)
        + [
            "exec",
            "-T",
            "arcadedb",
            "sh",
            "-c",
            f"curl -s -u root:'{password}' -X POST "
            f"http://127.0.0.1:2480/api/v1/query/{database} "
            f"-H 'Content-Type: application/json' --data-binary @-",
        ],
        input=body,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise BackupFailed("snapshot", (completed.stderr or completed.stdout).strip()[:400])
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise SnapshotFailed(
            f"ArcadeDB returned no JSON for {sql!r}: {completed.stdout[:300]}"
        ) from error
    if "result" not in payload:
        raise SnapshotFailed(f"ArcadeDB refused {sql!r}: {completed.stdout[:300]}")
    result: list[dict[str, Any]] = payload["result"]
    return result


def server_is_ready(compose_file: Path) -> bool:
    """The *server*, not a database.

    After `docker compose down -v` the store comes back with no `ospreyflow` database at all — it is
    created by whatever opens it first, and on a restore that is the restore. So waiting for a
    database to become queryable is waiting for something that will never happen, which is what the
    exit test's first wait did. This asks the server's own database listing instead, which answers
    as soon as it is up and says nothing about what is in it.
    """
    password = _env_value(compose_file.parent / "deployment.env", "OSPREY_ARCADEDB_PASSWORD")
    completed = subprocess.run(  # noqa: S603
        _compose(compose_file)
        + [
            "exec",
            "-T",
            "arcadedb",
            "sh",
            "-c",
            f"curl -sf -u root:'{password}' http://127.0.0.1:2480/api/v1/databases",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode == 0 and "result" in completed.stdout


def total_records(compose_file: Path, database: str) -> int:
    """Records across every type, with "no such database" counted as zero.

    An absent database is the legitimate empty state immediately after a destroy, and every caller
    that asks "is there anything in here" means to treat it that way. Collapsing it here rather than
    at each call site is what stops one of them getting it wrong — `harness/restore.py`'s emptiness
    refusal already did, in the other direction.
    """
    try:
        return sum(type_record_counts(compose_file, database).values())
    except (BackupFailed, SnapshotFailed):
        return 0


def type_record_counts(compose_file: Path, database: str) -> dict[str, int]:
    """Per-type record counts, from `count(*)` per type rather than from the schema's own figure.

    **Two wrong ways to do this, both found against a real store.**

    The first was `SELECT count(*) FROM V`. ArcadeDB has no `V`/`E` supertypes unless something
    creates them, and this ontology's adapter does not: it fails with `SchemaException: Type with
    name 'V' was not found`. Read as "no such database", that returns "empty" against a store
    holding 1,109 vertices — which is what `harness/restore.py`'s emptiness refusal did in its first
    draft, a refusal that could never fire.

    The second was `SELECT FROM schema:types` and its `records` field, which is what replaced it.
    That field **lags a bulk write**. Measured: immediately after the seed it reported 606
    `mx_PRESENT_AT` records where `count(*)` returned 614, and the figure caught up some minutes
    later with no write in between. The exit test duly failed — and failed by blaming the restore,
    reporting "614 before, 606 after" for data that was byte-identical either side. A comparison
    whose own instrument drifts produces false accusations, which is worse than producing nothing.

    So the schema is asked only for the *names* of the types, which it is authoritative about, and
    each count comes from the engine.
    """
    rows = _query(compose_file, database, "SELECT FROM schema:types")
    names = [row["name"] for row in rows if row.get("type") in {"vertex", "edge"}]
    counts: dict[str, int] = {}
    for name in names:
        result = _query(compose_file, database, f"SELECT count(*) AS n FROM {name}")
        counts[name] = int(result[0]["n"]) if result else 0
    return counts


def _fingerprint(record: dict[str, Any]) -> str:
    """One record as a stable string. Sorted keys so field order never decides equality."""
    return json.dumps(
        {key: value for key, value in record.items() if key not in VOLATILE_FIELDS},
        sort_keys=True,
        default=str,
    )


def _clusters_at(edges: list[dict[str, Any]], threshold: float) -> list[list[str]]:
    """The resolution projection at one τ: union-find over `SAME_AS` edges scoring at or above it.

    ADR-006 and `CLAUDE.md` rule 6 — entities are never merged in storage, so what a restore has to
    preserve is not a merged record but the *scores that produce this partition*. Singletons are
    dropped: a node that joins nothing is not a cluster, and including them would drown the
    difference between thresholds in a thousand one-element sets.
    """
    parent: dict[str, str] = {}

    def find(node: str) -> str:
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for edge in edges:
        score = (edge.get("properties") or {}).get("score")
        if score is None or float(score) < threshold:
            continue
        source, target = edge.get("source"), edge.get("target")
        if not source or not target:
            continue
        a, b = find(str(source)), find(str(target))
        if a != b:
            parent[a] = b

    grouped: dict[str, list[str]] = {}
    for node in list(parent):
        grouped.setdefault(find(node), []).append(node)
    return sorted(sorted(members) for members in grouped.values() if len(members) > 1)


@dataclass(frozen=True)
class GraphSnapshot:
    """Everything the exit test compares. Equality of two of these is the test."""

    type_counts: dict[str, int]
    node_fingerprints: list[str]
    edge_fingerprints: list[str]
    projections: dict[str, list[list[str]]]
    query_sample: dict[str, list[str]] = field(default_factory=dict)

    @property
    def total_records(self) -> int:
        return sum(self.type_counts.values())

    def differences_from(self, other: GraphSnapshot) -> list[str]:
        """Every difference, not the first. An operator comparing a restore wants the whole list —
        "the counts match and the handling markings do not" means something entirely different from
        either alone."""
        problems: list[str] = []
        if self.type_counts != other.type_counts:
            for name in sorted(set(self.type_counts) | set(other.type_counts)):
                mine, theirs = self.type_counts.get(name, 0), other.type_counts.get(name, 0)
                if mine != theirs:
                    problems.append(f"type {name}: {mine} record(s) before, {theirs} after")
        for label, mine_list, theirs_list in (
            ("node", self.node_fingerprints, other.node_fingerprints),
            ("edge", self.edge_fingerprints, other.edge_fingerprints),
        ):
            if mine_list != theirs_list:
                lost = sorted(set(mine_list) - set(theirs_list))
                gained = sorted(set(theirs_list) - set(mine_list))
                problems.append(
                    f"{label} multiset differs: {len(lost)} lost, {len(gained)} gained "
                    f"(first lost: {lost[0][:200] if lost else '—'})"
                )
        for tau in sorted(set(self.projections) | set(other.projections)):
            if self.projections.get(tau) != other.projections.get(tau):
                problems.append(
                    f"resolution projection at τ={tau} differs: "
                    f"{len(self.projections.get(tau, []))} cluster(s) before, "
                    f"{len(other.projections.get(tau, []))} after"
                )
        for name in sorted(set(self.query_sample) | set(other.query_sample)):
            if self.query_sample.get(name) != other.query_sample.get(name):
                problems.append(f"fixed query {name!r} returns different rows")
        return problems


#: The fixed query sample. Each one reads something a multiset comparison would not: a handling
#: marking the adapter filters on, a provenance state that decides whether a node is `inferred`, and
#: a degree distribution that changes if any edge is lost even when the totals happen to match.
FIXED_QUERIES: dict[str, str] = {
    "handling-classification-histogram": (
        "SELECT handling_classification AS k, count(*) AS n FROM mx_Person "
        "GROUP BY handling_classification ORDER BY k"
    ),
    "same-as-score-distribution": (
        "SELECT properties.score AS score FROM mx_SAME_AS ORDER BY properties.score DESC"
    ),
    "person-owning-units": (
        "SELECT owning_unit AS k, count(*) AS n FROM mx_Person GROUP BY owning_unit ORDER BY k"
    ),
    "document-count-by-handling-code": (
        "SELECT handling_code AS k, count(*) AS n FROM mx_Document "
        "GROUP BY handling_code ORDER BY k"
    ),
}


def take_snapshot(compose_file: Path, *, database: str = "ospreyflow") -> GraphSnapshot:
    counts = type_record_counts(compose_file, database)

    nodes: list[str] = []
    edges: list[str] = []
    same_as: list[dict[str, Any]] = []
    for name, records in sorted(counts.items()):
        if records == 0:
            continue
        rows = _query(compose_file, database, f"SELECT FROM {name}")
        target = edges if name.endswith("SAME_AS") or _is_edge_type(rows) else nodes
        target.extend(f"{name}|{_fingerprint(row)}" for row in rows)
        if name.endswith("SAME_AS"):
            same_as = rows

    projections = {f"{tau:.2f}": _clusters_at(same_as, tau) for tau in RESOLUTION_THRESHOLDS}
    sample = {
        name: [_fingerprint(row) for row in _query(compose_file, database, sql)]
        for name, sql in FIXED_QUERIES.items()
    }
    return GraphSnapshot(
        type_counts=counts,
        node_fingerprints=sorted(nodes),
        edge_fingerprints=sorted(edges),
        projections=projections,
        query_sample=sample,
    )


def _is_edge_type(rows: list[dict[str, Any]]) -> bool:
    """`@cat` is `"e"` for an edge record. Read off the data rather than off the type name, because
    an ontology is free to name an edge type without a recognisable suffix."""
    return bool(rows) and rows[0].get("@cat") == "e"
