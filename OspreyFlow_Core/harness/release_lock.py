"""The release's `versions.lock`: every image any deployment of the release can run (build order
step 20a, ADR-114 Amendment 34; Amendment 8 point 4).

`update` reads a release's lock and never computes one, and `update --make-bundle` carries exactly
the images the lock names. Rendered from the committed `osprey.yaml` alone (dashboards off),
v0.4.4's lock named no Superset and no ClickHouse, so a deployment that turned either on could not
take it from a release or a bundle. This renders the lock with every optional image on: each graph
store that can run, each analytics engine, each search backend, the stores a cloud would otherwise
provide, and Superset. A deployment still runs only what its own `osprey.yaml` asks for.

    OSPREY_IMAGE_REGISTRY=ghcr.io/<owner> python -m harness.release_lock --config osprey.yaml \
        --out versions.lock
"""

from __future__ import annotations

import argparse
import itertools
import sys
from collections.abc import Sequence
from pathlib import Path

from harness.images import DigestResolver, ServiceImage, daemon_then_registry_digest_resolver
from harness.render import (
    DEFAULT_CONFIG_PATH,
    UnpinnedImagesError,
    _render_versions_lock,
    load_config,
    service_images,
)
from harness.reporting import superset_image
from schemas.deployment import (
    AnalyticsEngine,
    ExternalConfig,
    GraphStore,
    OspreyConfig,
    SearchBackend,
)

#: Declarable, but with no adapter yet (`GraphStore`'s own note): a deployment that chose it could
#: not run, so no release carries its image. `test_release_lock.py` fails the day its adapter lands.
NOT_YET_RUNNABLE = (GraphStore.JANUSGRAPH,)


def _every_option(config: OspreyConfig) -> list[OspreyConfig]:
    """`config` with each combination of the options that add an image, all of them pulled."""
    variants = []
    graph_stores = [g for g in GraphStore if g not in NOT_YET_RUNNABLE]
    for graph, analytics, search in itertools.product(graph_stores, AnalyticsEngine, SearchBackend):
        components = config.components.model_copy(update={
            "graph_store": graph, "analytics_engine": analytics, "search": search,
            "source_path": None,
        })  # fmt: skip
        reporting = config.reporting.model_copy(update={"sync": True, "superset": True})
        variants.append(config.model_copy(update={
            "components": components, "reporting": reporting, "external": ExternalConfig(),
        }))  # fmt: skip
    return variants


def release_images(config: OspreyConfig) -> list[ServiceImage]:
    """Every image any option renders, each once, the committed answers' own images first."""
    seen: dict[str, ServiceImage] = {}
    for variant in [config, *_every_option(config)]:
        images = service_images(variant)
        if variant is not config:
            api = next(image for image in images if image.service == "api")
            images.append(ServiceImage("superset", superset_image(api.image),
                                       dockerfile="deploy/superset/Dockerfile"))  # fmt: skip
        for image in images:
            seen.setdefault(image.image, image)
    return list(seen.values())


def render_release_lock(config: OspreyConfig, resolver: DigestResolver | None = None) -> str:
    """The lock, every image by digest; refuses (`UnpinnedImagesError`) naming any it cannot pin."""
    return _render_versions_lock(
        release_images(config),
        resolver or daemon_then_registry_digest_resolver,
        allow_unpinned=False,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="release_lock", description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        text = render_release_lock(load_config(args.config))
    except UnpinnedImagesError as unpinned:
        print(f"release_lock: {unpinned}", file=sys.stderr)
        return 1
    args.out.write_text(text, encoding="utf-8")
    print(f"release_lock: {text.count('- service:')} image(s) locked in {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
