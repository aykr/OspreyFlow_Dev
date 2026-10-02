"""Compares two vaults' graphs, read-only: did the bulk load leave what the upsert load left?

    python -m scripts.seed_internal paysim --compare-vaults paysim paysim-bulk

(ADR-058 D9.) Reads nodes and edges from both vaults' graph databases with `SELECT` only and
reports, for the edges and the nodes: the ids each has that the other lacks; any field that differs
(endpoints, occurrences, handling, properties, provenance sources, interval, audit apart from its
timestamps, `load_id` and recipe); the ids a scan finds stored twice in each (the stray-record
defect, ADR-056 Amendment 19), so the bulk path's rate can be read against the upsert path's on the
same data (D7); and the weight components.

Weights are not expected to match edge for edge: the upsert path weighs each edge against the
corpus as it stood when that edge was written, the bulk path against the corpus at the end of the
load (D4). So the check is on the right-hand vault alone: every stored component is recomputed
from the edges the vault holds, and the stored weight from the components, and both must agree.
Under it, the same count is reported for the left-hand vault as information, since a vault
loaded by upsert is expected to differ.

Exit status 0 when the two vaults agree on everything that must agree, 1 when they do not.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from scripts.seed_support import vault_locations

from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from adapters.graph_arcadedb.gremlin_literals import groovy_identifier
from adapters.graph_arcadedb.naming import physical_type_name
from adapters.graph_arcadedb.weight import compute_weight
from schemas.domain import WeightComponents

PAGE = 2000
WEIGHT_TOLERANCE = 1e-9
#: Written by the store or the load clock, so they differ between two loads of the same data.
_NOT_COMPARED = {"@rid", "@in", "@out", "@type", "@cat", "weight", "weight_components"}


@dataclass(frozen=True)
class Graph:
    """What a scan of one graph database found. Lists, not dicts: a stray copy must stay visible."""

    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


def _strip_times(value: Any) -> Any:
    """Drops every key ending `_at` (the call's own clock) from a nested record."""
    if isinstance(value, dict):
        return {k: _strip_times(v) for k, v in value.items() if not str(k).endswith("_at")}
    if isinstance(value, list):
        return [_strip_times(v) for v in value]
    return value


def comparable(record: Mapping[str, Any]) -> dict[str, Any]:
    """The part of a stored element two correct loads must agree on."""
    out: dict[str, Any] = {}
    for key, value in record.items():
        if key in _NOT_COMPARED or key.startswith("@"):
            continue
        if key == "provenance" and isinstance(value, dict):
            sources = [(s.get("document_id"), s.get("locator")) for s in value.get("sources", [])]
            out[key] = {"state": value.get("state"), "sources": sources}
            continue
        out[key] = _strip_times(value)
    return out


def stored_twice(records: Sequence[Mapping[str, Any]]) -> list[str]:
    counts = Counter(str(r["id"]) for r in records)
    return sorted(i for i, n in counts.items() if n > 1)


def compare_records(
    kind: str, left: Sequence[Mapping[str, Any]], right: Sequence[Mapping[str, Any]]
) -> list[str]:
    """Every disagreement between two sets of stored elements, one line each."""
    a = {str(r["id"]): comparable(r) for r in left}
    b = {str(r["id"]): comparable(r) for r in right}
    lines = [f"{kind} {i}: only in the left vault" for i in sorted(set(a) - set(b))]
    lines += [f"{kind} {i}: only in the right vault" for i in sorted(set(b) - set(a))]
    for i in sorted(set(a) & set(b)):
        for key in sorted(set(a[i]) | set(b[i])):
            if a[i].get(key) != b[i].get(key):
                lines.append(
                    f"{kind} {i}: {key} is {a[i].get(key)!r} on the left, "
                    f"{b[i].get(key)!r} on the right"
                )
    return lines


def recomputed_components(edges: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    """Per edge id, the counts the weight formula takes, worked out from the edges the vault holds
    (those not reverted): the pair's occurrences, each endpoint's total occurrences, and the total
    over the edge type. A self-loop counts once for its node."""
    live = [e for e in edges if not e.get("reverted")]
    degree: Counter[str] = Counter()
    for e in live:
        degree[str(e["source"])] += int(e["occurrences"])
        if e["target"] != e["source"]:
            degree[str(e["target"])] += int(e["occurrences"])
    total = sum(int(e["occurrences"]) for e in live)
    return {
        str(e["id"]): {
            "corpus_pair_count": int(e["occurrences"]),
            "corpus_source_degree": degree[str(e["source"])],
            "corpus_target_degree": degree[str(e["target"])],
            "corpus_total_occurrences": total,
        }
        for e in live
    }


def component_mismatches(edges: Sequence[Mapping[str, Any]]) -> list[str]:
    """Edges whose stored weight components, or stored weight from them, are not what the vault's
    own contents give."""
    # One record per id: a stray copy is seen by a scan and not by a traversal, which is how the
    # product reads the corpus (ADR-056 Amendment 19), so it must not count twice here.
    edges = list({str(e["id"]): e for e in edges}.values())
    expected = recomputed_components(edges)
    lines: list[str] = []
    for e in edges:
        wanted = expected.get(str(e["id"]))
        stored = e.get("weight_components")
        if wanted is None:
            continue
        if not isinstance(stored, dict):
            lines.append(f"edge {e['id']}: no stored weight components")
            continue
        for key, value in wanted.items():
            if stored.get(key) != value:
                lines.append(
                    f"edge {e['id']}: {key} stored {stored.get(key)!r}, vault holds {value}"
                )
        valid_to = e.get("valid_to")
        components = WeightComponents(
            occurrences=int(e["occurrences"]),
            computed_at=_when(stored.get("computed_at")),
            **wanted,
        )
        weight = compute_weight(
            components,
            valid_to=None
            if valid_to is None
            else datetime.fromtimestamp(int(valid_to) / 1000, UTC),
            now=components.computed_at,
        )
        if abs(weight - float(e.get("weight", 0.0))) > WEIGHT_TOLERANCE:
            lines.append(
                f"edge {e['id']}: weight stored {e.get('weight')!r}, components give {weight!r}"
            )
    return lines


def _when(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def report(left: Graph, right: Graph, *, say: Callable[[str], None] = print, show: int = 10) -> int:
    """Say what the graphs agree and disagree on; return 1 if anything that must agree differs."""
    problems = 0

    def section(title: str, lines: list[str]) -> None:
        nonlocal problems
        say(f"{title}: {'none' if not lines else len(lines)}")
        for line in lines[:show]:
            say(f"    {line}")
        if len(lines) > show:
            say(f"    ... and {len(lines) - show} more")
        problems += bool(lines)

    say(
        f"left: {len(left.nodes):,} nodes, {len(left.edges):,} edge records; "
        f"right: {len(right.nodes):,} nodes, {len(right.edges):,} edge records"
    )
    section("node differences", compare_records("node", left.nodes, right.nodes))
    section("edge differences", compare_records("edge", left.edges, right.edges))
    left_twice, right_twice = stored_twice(left.edges), stored_twice(right.edges)
    say(
        f"ids stored twice by scan (ArcadeDB defect, not a difference to fix): "
        f"left {len(left_twice)}, right {len(right_twice)} of {len(right.edges):,}"
    )
    section(
        "right vault: weight components or weight not matching its own contents",
        component_mismatches(right.edges),
    )
    informational = component_mismatches(left.edges)
    say(
        f"left vault (information only, it is weighed edge by edge): {len(informational):,} "
        "component or weight value(s) differ from the end-of-load counts"
    )
    say("result: " + ("the vaults agree" if not problems else "the vaults DO NOT agree"))
    return int(bool(problems))


async def _scan(database: str) -> Graph:
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database))
    try:
        found: dict[str, list[dict[str, Any]]] = {}
        for kind, type_name in (("nodes", "Endpoint"), ("edges", "TRANSACTED")):
            label = groovy_identifier(physical_type_name(type_name))
            rows: list[dict[str, Any]] = []
            while True:
                page = await client.sql(
                    f"SELECT FROM {label} ORDER BY id SKIP {len(rows)} LIMIT {PAGE}"
                )
                rows += page
                if len(page) < PAGE:
                    break
            found[kind] = rows
        return Graph(nodes=found["nodes"], edges=found["edges"])
    finally:
        await client.aclose()


async def _run(left_vault: str, right_vault: str) -> int:
    analytics = os.environ.get("ANALYTICS_DB_PATH", "analytics.duckdb")
    databases = [vault_locations(v, analytics).database for v in (left_vault, right_vault)]
    print(f"comparing {left_vault} ({databases[0]}) with {right_vault} ({databases[1]}); read only")
    return report(await _scan(databases[0]), await _scan(databases[1]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("left")
    parser.add_argument("right")
    args = parser.parse_args(argv)
    return asyncio.run(_run(args.left, args.right))


if __name__ == "__main__":
    sys.exit(main())
