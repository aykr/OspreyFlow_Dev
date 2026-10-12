"""The internal demos' registry entries, kept beside their code (`spec/06_DECISIONS.md` ADR-114
Amendment 2). The product's own registry (`scripts/demo_registry.py`) holds only what may ship;
`ALL` is what the packaging gate and the publish step judge an artefact against, so an internal
demo's data and code are refused wherever they turn up."""

from __future__ import annotations

from scripts.demo_registry import DELIVERY_SEED, DISTRIBUTION_INTERNAL, REGISTRY, DemoManifest

#: ADR-053. REAL data, admitted for the owner's own machine only through the local exceptions list,
#: never committed, never shipped. Its data folder and its code are both refused by the gate.
ENRON = DemoManifest(
    id="enron",
    distribution=DISTRIBUTION_INTERNAL,
    delivery=DELIVERY_SEED,
    seed_module="internal_demos.seed_enron",
    paths=(
        "OspreyFlow_Data/Enron_Mails",
        "internal_demos/enron.py",
        "internal_demos/seed_enron.py",
        "packages/demo_fixtures/enron.py",
        "scripts/seed_enron.py",
    ),
)

INTERNAL: tuple[DemoManifest, ...] = (ENRON,)

#: Every demo the gates know: what may ship, and what never may.
ALL: tuple[DemoManifest, ...] = (*REGISTRY, *INTERNAL)
