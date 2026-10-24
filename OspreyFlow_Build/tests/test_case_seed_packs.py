"""ADR-126 decision 2 (unit D1), the pure half: what each seed says its case's domain packs are, and
how `ensure_case` and `case_from_arguments` carry that into the case without ever overwriting a
choice. The SQL that makes the setting atomic is `test_case_seed.py`'s, against Postgres.

What each test would catch if it failed:

- a seed whose packs drifted from the record (`test_each_seed_names_the_packs_the_record_gives`):
  Operation Ledger would draw no KYC card, or Fixture Corp would draw the empty one the record
  removes;
- `ensure_case` overwriting on reuse (`test_a_reused_case_keeps_what_anyone_chose`): an Author's
  change would be undone by the next reseed;
- `case_from_arguments` not passing the seed's packs (`test_the_seeds_packs_reach_ensure_case`):
  every seeded case would stay NULL, read as POLE;
- the harness's union missing a pack (`test_the_harness_union_is_every_seeded_datasets_packs`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, get_args

import pytest
from scripts import case_seed
from scripts.case_seed import case_from_arguments, ensure_case
from services.api.investigations import AccessLevel, Investigation, InvestigationStore

from demo_fixtures import datasets as seed_datasets
from demo_fixtures.datasets import (
    ENRON,
    FIXTURE_CORP,
    HMP,
    LEDGER,
    PAYSIM,
    PID,
    PID_SCALE,
    SCENARIOS,
    SEED_DATASETS,
    domains_for,
)
from ontology.packs import PACK_NAMES
from schemas.domain import DomainPack, Principal

SEEDER = Principal(id="seed-worker", clearance="OFFICIAL", org_unit="verify")


def test_each_seed_names_the_packs_the_record_gives() -> None:
    assert {s.id: s.domains for s in SEED_DATASETS} == {
        "enron": (),
        "fixture-corp": (),
        "hmp": ("fibo", "niem"),
        "ledger": ("fibo",),
        "paysim": (),
        "scenarios": (),
        "prison-intelligence": ("niem",),
        "prison-intelligence-scale": ("niem",),
    }
    assert LEDGER.domains == ("fibo",)
    assert HMP.domains == ("fibo", "niem")
    assert PID.domains == PID_SCALE.domains == ("niem",)
    assert FIXTURE_CORP.domains == PAYSIM.domains == ENRON.domains == SCENARIOS.domains == ()


def test_every_seeds_packs_are_packs_the_deployment_knows_sorted_and_without_repeats() -> None:
    for seed in SEED_DATASETS:
        assert list(seed.domains) == sorted(set(seed.domains)), seed.id
        assert set(seed.domains) <= set(PACK_NAMES), seed.id


def test_the_pack_names_are_defined_once_in_the_schemas() -> None:
    assert PACK_NAMES == get_args(DomainPack) == ("fibo", "niem", "stix")


def test_the_harness_union_is_every_seeded_datasets_packs() -> None:
    assert domains_for(["hmp"]) == ["fibo", "niem"]
    assert domains_for(["hmp", "fixture-corp", "scenarios"]) == ["fibo", "niem"]
    assert domains_for(["fixture-corp", "scenarios"]) == []
    assert domains_for(["ledger", "prison-intelligence"]) == ["fibo", "niem"]
    assert domains_for([]) == []
    assert domains_for(["hmp", "hmp"]) == ["fibo", "niem"], "without repeats"


def test_the_harness_union_names_an_unknown_dataset() -> None:
    with pytest.raises(KeyError, match="no-such-seed"):
        domains_for(["hmp", "no-such-seed"])


class _Store:
    """The calls `ensure_case` makes. `set_domains_if_unset` does what the real one does: sets the
    column only while it is None, and says whether it did. `set_domains` overwrites, as the real
    one does, so a seed that called it on reuse would show."""

    def __init__(self) -> None:
        self.stored: dict[str, list[str] | None] = {}
        self.cases: dict[str, Investigation] = {}
        self.calls: list[tuple[str, str]] = []

    async def list_for(self, principal: Principal) -> list[tuple[Investigation, AccessLevel]]:
        return [(await self.get(c.id), AccessLevel.AUTHOR) for c in self.cases.values()]

    async def create(
        self,
        principal: Principal,
        *,
        name: str,
        branched_from: str | None = None,
        domains: list[str] | None = None,
    ) -> Investigation:
        case = Investigation(
            id=f"case-{len(self.cases) + 1}",
            name=name,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_by=principal.id,
            owning_unit=principal.org_unit,
        )
        self.cases[case.id] = case
        self.stored[case.id] = None
        self.calls.append(("create", case.id))
        return case

    async def get(self, investigation_id: str) -> Investigation:
        return self.cases[investigation_id].model_copy(
            update={"domains": sorted(self.stored[investigation_id] or [])}
        )

    async def set_grant(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def set_domains(self, investigation_id: str, domains: list[str], *, by: Any) -> None:
        self.calls.append(("set_domains", investigation_id))
        self.stored[investigation_id] = sorted(set(domains))

    async def set_domains_if_unset(
        self, investigation_id: str, domains: list[str], *, by: Any
    ) -> bool:
        self.calls.append(("set_domains_if_unset", investigation_id))
        if self.stored[investigation_id] is not None:
            return False
        self.stored[investigation_id] = sorted(set(domains))
        return True


async def test_a_new_case_gets_the_seeds_packs() -> None:
    store = _Store()

    case = await ensure_case(
        store,  # type: ignore[arg-type]
        name="Mixed",
        seeder=SEEDER,
        grants={},
        domains=["fibo", "niem"],
    )

    assert store.stored[case.id] == ["fibo", "niem"]
    assert case.domains == ["fibo", "niem"], "the case handed back says what it now holds"


async def test_a_reused_case_keeps_what_anyone_chose() -> None:
    store = _Store()
    first = await ensure_case(
        store,  # type: ignore[arg-type]
        name="Mixed",
        seeder=SEEDER,
        grants={},
        domains=["fibo"],
    )
    await store.set_domains(first.id, ["stix"], by=SEEDER)  # an Author's change

    again = await ensure_case(
        store,  # type: ignore[arg-type]
        name="Mixed",
        seeder=SEEDER,
        grants={},
        domains=["fibo", "niem"],
    )

    assert again.id == first.id
    assert store.stored[first.id] == ["stix"]
    assert again.domains == ["stix"], "what the reused case holds, not what the seed wanted"
    assert [c for c in store.calls if c[0] == "set_domains"] == [("set_domains", first.id)], (
        "only the Author's own call overwrote; the seed went through set_domains_if_unset"
    )


async def test_a_reused_case_chosen_as_pole_is_not_overwritten() -> None:
    store = _Store()
    first = await ensure_case(
        store,  # type: ignore[arg-type]
        name="Plain",
        seeder=SEEDER,
        grants={},
        domains=[],
    )
    assert store.stored[first.id] == []

    await ensure_case(
        store,  # type: ignore[arg-type]
        name="Plain",
        seeder=SEEDER,
        grants={},
        domains=["fibo"],
    )

    assert store.stored[first.id] == []


async def test_a_seed_that_gives_no_packs_never_touches_the_setting() -> None:
    store = _Store()

    case = await ensure_case(store, name="Silent", seeder=SEEDER, grants={})  # type: ignore[arg-type]

    assert store.stored[case.id] is None
    assert [c[0] for c in store.calls] == ["create"]


async def test_the_seeds_packs_reach_ensure_case(monkeypatch: pytest.MonkeyPatch) -> None:
    """`case_from_arguments` is what the dataset seeds call, with the seed's own `SeedDataset`."""
    store = _Store()

    async def connect(dsn: str) -> _Store:
        return store

    async def closed() -> None:
        return None

    store.close = closed  # type: ignore[attr-defined]

    async def no_reads(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(InvestigationStore, "connect", connect)
    monkeypatch.setattr(case_seed, "_reads_from_arguments", no_reads)

    results = {}
    for seed in (HMP, LEDGER, FIXTURE_CORP, PID):
        case = await case_from_arguments(
            name=f"Case for {seed.id}", seeder=SEEDER, grant_texts=[], dataset=seed
        )
        results[seed.id] = store.stored[case.id]

    assert results == {
        "hmp": ["fibo", "niem"],
        "ledger": ["fibo"],
        "fixture-corp": [],
        "prison-intelligence": ["niem"],
    }


def test_the_module_exports_what_the_record_names() -> None:
    assert seed_datasets.SeedDataset.__dataclass_fields__["domains"].default == ()


def test_the_glass_labels_the_packs_as_the_studio_does() -> None:
    """The Glass writes the packs' labels by hand (`cases.ts`, outside `schemas-check`), so the
    two lists are held in step here: each Studio label, in the catalogue's order, is in
    `DOMAIN_PACKS`, and so is the POLE label. A pack added or relabelled in the Conduit fails this
    until the Glass follows."""
    import re

    from tools.layout import REPO

    from ontology.packs import pack_catalogue

    source = (REPO / "apps" / "workspace" / "src" / "investigation" / "cases.ts").read_text()
    pole, *packs = pack_catalogue()
    assert f'POLE_LABEL = "{pole.label}"' in source
    declared = re.findall(r'\{ name: "(\w+)", label: "([^"]+)" \}', source)
    assert declared == [(p.name, p.label) for p in packs]
