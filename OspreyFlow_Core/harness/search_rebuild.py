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

from harness.preflight.ports import read_env_file

#: The two settings either of which tells the Conduit where OpenSearch is (`OPENSEARCH_URL` first).
ADDRESS_SETTINGS = ("OPENSEARCH_URL", "OPENSEARCH_HOST")

REBUILD = ["exec", "-T", "api", "python", "-m", "scripts.rebuild_search_index"]


def renders_opensearch(compose_file: Path) -> bool:
    services = (yaml.safe_load(compose_file.read_text(encoding="utf-8")) or {}).get("services")
    return isinstance(services, dict) and "opensearch" in services


def sets_no_address(env_file: Path) -> bool:
    """Whether the deployment's `deployment.env` sets neither `OPENSEARCH_URL` nor `OPENSEARCH_HOST`
    to anything but blanks, as Compose reads the file the Conduit's environment is made from
    (`harness.preflight.ports.read_env_file`: an `export ` prefix, quotes and a trailing ` #`
    comment are not part of a value; `services.search_index.run`'s `configured` then reads it):
    the rebuild then reaches for `localhost:9200`, where nothing answers, and running it again
    mends nothing, since the missing thing is the setting, which `ospreyflow apply` writes (D216).
    No value is returned. A file that cannot be read is not said to lack the setting."""
    try:
        held = read_env_file(env_file)
    except OSError:
        return False
    return not any(held.get(name, "").strip() for name in ADDRESS_SETTINGS)


def rebuild_argv(compose: Sequence[str]) -> list[str]:
    """The rebuild in the Conduit's own container, by the deployment's own compose command."""
    return [*compose, *REBUILD]
