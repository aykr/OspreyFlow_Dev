"""`ComputePort` over `graphology` — `spec/00_ARCHITECTURE.md` §2.3, Tier 1 (≤ 20k nodes, browser).

`spec/06_DECISIONS.md` ADR-028's own decision: this suite exercises Tier 1 as a plain Node
script, never a browser or a `Worker` — the correctness claim owed here is algorithmic
(`apps/workspace/compute-tier1/harness.mjs`'s numbers agree with `rustworkx`'s on the same input),
not a threading one. Every method shells out to that script: writes `{"method", "request"}` as
JSON on stdin, reads one JSON result object back from stdout, per invocation — no persistent
process, matching the ADR's own "a small Node script... headless" characterisation. `shortest_
paths`/`temporal_motifs` raise the same disclosed `NotImplementedError`s
`adapters/compute_rustworkx/adapter.py` does, for the same reason (no caller yet).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from schemas.compute import (
    CentralityRequest,
    CliqueMetricRequest,
    CommunityRequest,
    MotifMatch,
    MotifRequest,
    OwnershipRequest,
    OwnershipTooComplex,
    OwnershipTrace,
)
from schemas.domain import CliqueScore, CommunityId, NodeId, PathRequest
from schemas.domain import Path as GraphPath

#: `apps/workspace/compute-tier1/harness.mjs`, resolved from this file's own location rather than
#: assumed relative to the caller's working directory — this adapter is imported from `pytest`
#: (repo root) today, but nothing pins that.
_HARNESS_PATH = (
    Path(__file__).resolve().parents[3] / "apps" / "workspace" / "compute-tier1" / "harness.mjs"
)


async def _call_harness(method: str, request: dict[str, object]) -> dict[str, object]:
    process = await asyncio.create_subprocess_exec(
        "node",
        str(_HARNESS_PATH),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    payload = json.dumps({"method": method, "request": request}).encode()
    stdout, stderr = await process.communicate(payload)
    if process.returncode != 0:
        # The harness writes its own refusal to stdout as `{"error": ...}` before exiting 1.
        try:
            said = str(json.loads(stdout).get("error", ""))
        except ValueError:
            said = ""
        raise RuntimeError(
            f"Tier 1 harness ({method}) exited {process.returncode}: "
            f"{said or stderr.decode().strip()}"
        )
    result = json.loads(stdout)
    if "error" in result:
        raise RuntimeError(f"Tier 1 harness ({method}) reported: {result['error']}")
    return result["result"]  # type: ignore[no-any-return]


class ComputeGraphologyTier1Adapter:
    async def centrality(self, req: CentralityRequest) -> dict[NodeId, float]:
        result = await _call_harness(
            "centrality",
            {"subgraph": req.subgraph.model_dump(mode="json"), "metric": req.metric},
        )
        return {node_id: float(value) for node_id, value in result.items()}  # type: ignore[arg-type]

    async def communities(self, req: CommunityRequest) -> dict[NodeId, CommunityId]:
        # The harness reads `nodes[].id` and `edges[].source/target/weight` alone, which the
        # structure (ADR-100 Amendment 5) has in the same shape as the records.
        graph = req.subgraph if req.subgraph is not None else req.structure
        assert graph is not None
        result = await _call_harness("communities", {"subgraph": graph.model_dump(mode="json")})
        return {node_id: str(value) for node_id, value in result.items()}

    async def clique_metric(self, req: CliqueMetricRequest) -> dict[NodeId, CliqueScore]:
        result = await _call_harness(
            "clique_metric",
            {
                "subgraph": req.subgraph.model_dump(mode="json"),
                "k_min": req.k_min,
                "k_max": req.k_max,
            },
        )
        return {node_id: float(value) for node_id, value in result.items()}  # type: ignore[arg-type]

    async def shortest_paths(self, req: PathRequest) -> list[GraphPath]:
        raise NotImplementedError(
            "ComputePort.shortest_paths has no caller yet (Phase 7 Stage 5, the pathfinder) — "
            "the interactive pathfinder is built on GraphPort.paths directly "
            "(01_DOMAIN_MODEL.md §6.3's own implementation note), not this method"
        )

    async def temporal_motifs(self, req: MotifRequest) -> list[MotifMatch]:
        raise NotImplementedError(
            "convoy/relay/burst detection is unclaimed by any phase's own bullet list "
            "(a disclosed gap) — MotifRequest/MotifMatch exist as real "
            "schemas because _pending_port_placeholders.py's retirement needed them, not because "
            "the algorithm has an owning phase yet"
        )

    async def ownership(self, req: OwnershipRequest) -> OwnershipTrace:
        """ADR-109 phase C: the harness's `ownership`, the same walk and order as Tier 2's. Its
        refusal (too deep, too many chains) comes back as the harness's error; said as
        `OwnershipTooComplex`, the port's own word for it."""
        try:
            result = await _call_harness("ownership", req.model_dump(mode="json"))
        except RuntimeError as exc:
            if "not traced in part" in str(exc):
                raise OwnershipTooComplex(str(exc)) from exc
            raise
        return OwnershipTrace.model_validate(result)

