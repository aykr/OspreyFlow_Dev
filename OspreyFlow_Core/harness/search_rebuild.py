"""The search index rebuilt from the graph on a deployment that searches with OpenSearch (ADR-150
decision 4 and Amendment 2), after anything that brings the Conduit up: install (`harness.apply`),
update (`harness.update`), restore (`harness.restore`) and `ospreyflow start --build`
(`scripts/refresh.py`). An index whose mapping fingerprint is not this version's
(`MAPPING_FINGERPRINT`) is one the indexer writes nothing to, so search stays on the fallback, and a
fresh domain's index holds none of the graph; the rebuild makes a new one from the graph and moves
the alias to it. A deployment that renders no OpenSearch has nothing to rebuild."""

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
