"""`osprey bundle` — `docs/00_ARCHITECTURE.md` §1.2's "Licensing across
multiple clients": "the bundle step refuses to package tiles or
gazetteers whose profile says `redistributable: false`, and names them."

No `osprey` CLI yet (`docs/SESSION_HANDOVER.md`'s standing note, reconfirmed
for Phase 5) — a plain, directly-runnable script now, the same pattern as
`scripts/build_local_basemap.py`/`scripts/seed_hmp_fixture.py`. The real
`osprey bundle` command wraps `bundle_map_providers` below in Phase 8.

**A named refusal of the whole bundle, not a silent partial one.** A
deployment bundling tiles/gazetteers for offline/air-gapped shipping
expects every basemap provider it configured to actually be there —
quietly dropping a non-redistributable one would ship a working-looking
bundle missing a layer nobody asked to remove. This mirrors `tests/
test_demo_osprey_config_is_tier_1_only.py`'s existing "every provider in
this config must be open" philosophy for the demo/CI config, generalised
to any config a deployment might bundle.

Run as `PYTHONPATH=.:packages python -m scripts.osprey_bundle <osprey.yaml path>`
from the repo root — the same `PYTHONPATH` requirement `scripts/
seed_hmp_fixture.py`'s own docstring already explains (neither pytest's
`pythonpath` config nor a bare `python -m` invocation puts the repo root
and `packages/` on `sys.path` by itself).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from services.api.mapconfig_loader import load_map_config

from schemas.mapconfig import MapConfig


@dataclass(frozen=True)
class BundleResult:
    bundled_provider_ids: tuple[str, ...]


class NonRedistributableProviderError(RuntimeError):
    """Names every refused provider — `00_ARCHITECTURE.md` §1.2's "and
    names them", not a bare boolean failure a deployer has to go hunting
    for in the config themselves."""

    def __init__(self, refused_provider_ids: list[str]) -> None:
        self.refused_provider_ids = tuple(refused_provider_ids)
        super().__init__(
            "refusing to bundle non-redistributable provider(s): "
            + ", ".join(refused_provider_ids)
        )


def bundle_map_providers(config: MapConfig) -> BundleResult:
    """Raises `NonRedistributableProviderError` naming every provider whose
    `licence.redistributable` is false; otherwise bundles all of them."""
    refused = [p.id for p in config.providers if not p.licence.redistributable]
    if refused:
        raise NonRedistributableProviderError(refused)
    return BundleResult(bundled_provider_ids=tuple(p.id for p in config.providers))


# --- CLI entrypoint, mirroring scripts/seed_hmp_fixture.py's shape -----------


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.osprey_bundle",
        description=(
            "Refuses, by name, to bundle an osprey.yaml config containing a "
            "non-redistributable provider."
        ),
    )
    parser.add_argument("config_path", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    config = load_map_config(args.config_path)
    result = bundle_map_providers(config)
    print(
        f"Bundled {len(result.bundled_provider_ids)} provider(s): "
        f"{', '.join(result.bundled_provider_ids)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
