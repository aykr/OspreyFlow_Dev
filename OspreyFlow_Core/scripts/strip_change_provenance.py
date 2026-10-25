"""Removes the old link's id from the provenance of links written before ADR-124 U10 (decision 11).

A link changed through the link-change route, or a picture removed, was written as a successor
whose provenance named the link it replaced: `manual:change:<old id>`, `manual:remove-picture:<old
id>`. Every reader of the successor was sent that id, naming a link they may not be able to read
(rule 3). From U10 a successor names no id; this script cleans what was written before. Run it once
per deployment, inside the network where ArcadeDB and Valkey are reachable; the Conduit may keep
running:

    python -m scripts.strip_change_provenance

What it does, in order:

1. **The Vault.** Calls `GraphPort.strip_provenance_references` once for each prefix, which removes
   the entries from every link, superseded ones included.
2. **Every working set.** Rewrites each case's stored copies of its links in Valkey to remove the
   same entries, by a conditional replace (`rewrite_edges_if_unchanged`): a link is replaced only
   if its stored body is still the one read, in one step with the write, so a link the running
   Conduit removed or replaced in between is not brought back or overwritten. A body's provenance
   is not part of its access signature (handling and datasets), so the counted access index is not
   touched by the rewrite, and a replacement that would change it is refused.
3. **Every delta stream that names one of them.** Deletes `ws:<case>:deltas` where a stored delta
   carries such an entry, so `deltas_after` finds a gap and every client of the case is sent a full
   projected snapshot from the rewritten copies on its next catch-up. A stream that names none is
   left alone, which is also what makes a second run change nothing.

Idempotent: the second run changes nothing and reports 0. The in-place rewrite is the named
exception to ADR-080's "every change is a supersede": it changes no claim, only a reference. History
bodies in Postgres are left as they are, because restore reads the Vault and never serves them.
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass, field
from typing import Any

from services.api.change_provenance import ID_BEARING_PREFIXES
from services.api.config import ValkeyConfig
from services.api.working_set.store import ValkeyWorkingSetStore, WorkingSetStorage
from valkey.asyncio import Valkey

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from ontology.handling import load_uk_le_scheme
from ports.graph import GraphPort
from schemas.domain import Edge

#: A stored delta that carries one of the entries: `model_dump_json` writes compact JSON.
_NAMES_A_LINK = re.compile(
    r'"document_id"\s*:\s*"(?:' + "|".join(re.escape(p) for p in ID_BEARING_PREFIXES) + ")"
)


@dataclass
class StripReport:
    """What a run changed. `total` is what a second run must report as 0."""

    vault: dict[str, int] = field(default_factory=dict)
    working_set_links: int = 0
    working_set_cases: int = 0
    #: Links that changed under the run and were left as the Conduit made them.
    working_set_skipped: int = 0
    streams_deleted: int = 0

    @property
    def total(self) -> int:
        return sum(self.vault.values()) + self.working_set_links + self.streams_deleted


def _stripped(edge: Edge) -> Edge | None:
    """`edge` without any entry that names an earlier link, or `None` if it has none."""
    sources = edge.provenance.sources
    kept = [s for s in sources if not s.document_id.startswith(ID_BEARING_PREFIXES)]
    if len(kept) == len(sources):
        return None
    return edge.model_copy(
        update={"provenance": edge.provenance.model_copy(update={"sources": kept})}
    )


async def _case_ids(valkey: Any) -> list[str]:
    """Every case with a working set in Valkey, from its `ws:<case>:edges` key."""
    cases: set[str] = set()
    async for raw in valkey.scan_iter(match="ws:*:edges", count=500):
        key = raw.decode() if isinstance(raw, bytes) else str(raw)
        cases.add(key[len("ws:") : -len(":edges")])
    return sorted(cases)


async def _stream_names_a_link(valkey: Any, key: str) -> bool:
    for _stream_id, fields in await valkey.xrange(key):
        for value in fields.values():
            text = value.decode() if isinstance(value, bytes) else str(value)
            if _NAMES_A_LINK.search(text):
                return True
    return False


async def strip(graph: GraphPort, valkey: Any, working_sets: WorkingSetStorage) -> StripReport:
    """The whole run, in the order the docstring gives."""
    report = StripReport()
    for prefix in ID_BEARING_PREFIXES:
        report.vault[prefix] = await graph.strip_provenance_references(prefix)

    cases = await _case_ids(valkey)
    for case in cases:
        # Conditional: a link the running Conduit removed or replaced since it was read is left as
        # it now is, never brought back. Its current body was written after U10a and names no id;
        # if one still does, the next run picks it up.
        outcome = await working_sets.rewrite_edges_if_unchanged(case, _stripped)
        if outcome.rewritten:
            report.working_set_links += outcome.rewritten
            report.working_set_cases += 1
        report.working_set_skipped += outcome.skipped

    # After the copies are clean: a stream that still names an id would send it on a catch-up.
    for case in cases:
        key = f"ws:{case}:deltas"
        if await _stream_names_a_link(valkey, key):
            await valkey.delete(key)
            report.streams_deleted += 1
    return report


async def _main() -> int:
    database = os.environ.get("ARCADEDB_DATABASE", "ospreyflow")
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database))
    valkey_config = ValkeyConfig.from_env()
    valkey = Valkey(host=valkey_config.host, port=valkey_config.port, db=valkey_config.db)
    try:
        report = await strip(
            GraphArcadeDBAdapter(client, load_uk_le_scheme()),
            valkey,
            ValkeyWorkingSetStore(valkey),
        )
    finally:
        await client.aclose()
        await valkey.aclose()
    for prefix, count in report.vault.items():
        print(f"Vault: {count} link(s) had a '{prefix}' entry removed.")
    print(
        f"Working sets: {report.working_set_links} link(s) rewritten in "
        f"{report.working_set_cases} case(s); {report.streams_deleted} delta stream(s) deleted."
    )
    if report.working_set_skipped:
        print(
            f"{report.working_set_skipped} link(s) changed under the run and were left as the "
            "Conduit made them; run it again if any still names an old link."
        )
    print("Nothing needed changing." if report.total == 0 else "Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
