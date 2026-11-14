"""The search index rebuilt from the graph on a deployment that searches with OpenSearch (ADR-150
decision 4), after anything that brings v0.5.2's Conduit up: install (`harness.apply`), update
(`harness.update`) and restore (`harness.restore`). An index made before v0.5.2 has no mapping
fingerprint, so the indexer writes nothing to it and search stays on the fallback, and a fresh
domain's index holds none of the graph; the rebuild makes a new one from the graph and moves the
alias to it. A deployment that renders no OpenSearch has nothing to rebuild."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import yaml

REBUILD = ["exec", "-T", "api", "python", "-m", "scripts.rebuild_search_index"]


def renders_opensearch(compose_file: Path) -> bool:
    services = (yaml.safe_load(compose_file.read_text(encoding="utf-8")) or {}).get("services")
    return isinstance(services, dict) and "opensearch" in services


def rebuild_argv(compose: Sequence[str]) -> list[str]:
    """The rebuild in the Conduit's own container, by the deployment's own compose command."""
    return [*compose, *REBUILD]
