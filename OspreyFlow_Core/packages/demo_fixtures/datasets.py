"""The datasets the demo seeds load (`06_DECISIONS.md` ADR-099).

Each seed writes every node and link it loads into its own dataset, and the case it makes reads
that dataset. `source` is the provenance `document_id` the seed has always written, which is how
`scripts.stamp_datasets` finds, in a store loaded before ADR-099, what each seed loaded.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeedDataset:
    id: str
    name: str
    source: str
    #: The case the seed makes (`scripts/seed_internal.py`'s `DATASETS`), if it makes one.
    case_name: str | None = None


ENRON = SeedDataset(
    id="enron",
    name="Enron corpus",
    source="enron-corpus",
    case_name="Enron corpus (real data, this machine only)",
)
FIXTURE_CORP = SeedDataset(
    id="fixture-corp",
    name="Fixture Corp",
    source="fixture-corp",
    case_name="Fixture Corp (synthetic demo)",
)
HMP = SeedDataset(
    id="hmp", name="HMP fixture", source="hmp-fixture", case_name="HMP fixture (synthetic demo)"
)
PAYSIM = SeedDataset(
    id="paysim",
    name="PaySim",
    source="paysim-dataset",
    case_name="PaySim mobile money (internal)",
)
LEDGER = SeedDataset(
    id="ledger",
    name="Operation Ledger",
    source="ledger-fixture",
    case_name="Operation Ledger (synthetic demo)",
)
SCENARIOS = SeedDataset(id="scenarios", name="Acceptance scenarios", source="fixture")

SEED_DATASETS: tuple[SeedDataset, ...] = (ENRON, FIXTURE_CORP, HMP, LEDGER, PAYSIM, SCENARIOS)
