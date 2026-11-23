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

#: The two settings either of which tells the Conduit where OpenSearch is (`OPENSEARCH_URL` first).
ADDRESS_SETTINGS = ("OPENSEARCH_URL", "OPENSEARCH_HOST")

REBUILD = ["exec", "-T", "api", "python", "-m", "scripts.rebuild_search_index"]


def renders_opensearch(compose_file: Path) -> bool:
    services = (yaml.safe_load(compose_file.read_text(encoding="utf-8")) or {}).get("services")
    return isinstance(services, dict) and "opensearch" in services


def sets_no_address(env_file: Path) -> bool:
    """Whether the deployment's `deployment.env` sets neither `OPENSEARCH_URL` nor `OPENSEARCH_HOST`
    to anything but blanks, as the Conduit reads them (`services.search_index.run`'s `configured`):
    the rebuild then reaches for `localhost:9200`, where nothing answers, and running it again
    mends nothing, since the missing thing is the setting, which `ospreyflow apply` writes (D216).
    No value is returned. A file that cannot be read is not said to lack the setting."""
    try:
        text = env_file.read_text(encoding="utf-8")
    except OSError:
        return False
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() in ADDRESS_SETTINGS and value.strip().strip("'\""):
            return False
    return True


def rebuild_argv(compose: Sequence[str]) -> list[str]:
    """The rebuild in the Conduit's own container, by the deployment's own compose command."""
    return [*compose, *REBUILD]
