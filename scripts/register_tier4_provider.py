"""`osprey map add` for a tier-4 WMTS endpoint — `spec/00_ARCHITECTURE.md`
§1.2 ("Capabilities documents are parsed at registration"). No `osprey`
CLI yet (`CLAUDE.md`'s own Conventions) — a plain,
directly-runnable script now, the same pattern as `scripts/
build_local_basemap.py`/`tools/osprey_bundle.py`. Fetches a WMTS
service's own `GetCapabilities` document, parses it, and prints the
discovered layers/projection/zoom range — a deployer pastes the result
into a new `osprey.yaml` provider entry by hand; this does not write the
config file itself (Checkpoint 3b's own scope: registration *discovery*,
not a config-editing tool).

Run as `PYTHONPATH=.:packages python -m scripts.register_tier4_provider <endpoint>`
from the repo root.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from services.api.tier4_registration import UnsupportedProjectionError, register_tier4_provider


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.register_tier4_provider",
        description="Discovers a tier-4 WMTS service's layers/projection/zoom range.",
    )
    parser.add_argument("endpoint", help="The WMTS service's base endpoint URL.")
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    try:
        capabilities = await register_tier4_provider(args.endpoint)
    except UnsupportedProjectionError as exc:
        print(f"Refusing to register: {exc}", file=sys.stderr)
        return 1
    print(f"Projection: {capabilities.projection}")
    print(f"Zoom range: {capabilities.zoom_min}-{capabilities.zoom_max}")
    print(f"Layers: {', '.join(capabilities.layers)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
