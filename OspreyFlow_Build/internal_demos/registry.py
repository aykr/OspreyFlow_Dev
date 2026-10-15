"""The internal demos' registry entries, kept beside their code (`spec/06_DECISIONS.md` ADR-114
Amendment 2). The product's own registry (`scripts/demo_registry.py`) holds only what may ship;
`ALL` is what the packaging gate and the publish step judge an artefact against, so an internal
demo's data and code are refused wherever they turn up."""

from __future__ import annotations

from scripts.demo_registry import REGISTRY, DemoManifest

#: None today. The Enron corpus was the one internal demo until ADR-114 Amendment 23 made it an
#: optional download in the product (`scripts.demo_registry`); an internal demo registered here again
#: has its data and code refused by the gates wherever they turn up.
INTERNAL: tuple[DemoManifest, ...] = ()

#: Every demo the gates know: what may ship, and what never may.
ALL: tuple[DemoManifest, ...] = (*REGISTRY, *INTERNAL)
