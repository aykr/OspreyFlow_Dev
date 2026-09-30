"""ADR-035 §C1's demo distribution-class registry — `06_DECISIONS.md`: "Every demo carries a
manifest declaring a `distribution` field: `shipped` (included in artefacts given to customers and
testers) or `internal` (never included in any artefact leaving this project)."

**The registry fails closed.** A manifest with a missing, empty, misspelled or unrecognised
`distribution` value is treated as `internal` — `DemoManifest.is_shipped` is a strict `==
"shipped"` comparison, never a lookup that could raise `KeyError` on an unexpected value and never
an `in {"shipped", ...}` membership test that could be widened by a typo landing on the wrong side.
`DemoManifest.from_dict` is what a hand-edited or generated manifest would round-trip through, and
is where "missing" actually manifests as an empty string rather than a raised exception — the same
"absence is the safe default, never inferred as permission" shape `scripts/real_data_exceptions.py`
already holds itself to for a different registry.

**What is actually shipped today, checked directly against `DEMO_GUIDE.md` §1's own table and
`scripts/seed_hmp_fixture.py`/`scripts/seed_fixture_corp.py`'s own imports — not assumed from ADR
prose:** exactly two demo datasets exist in this repository, both synthetic, both generated, both
carrying no third-party licence (`06_DECISIONS.md` ADR-035 §C5's own "Generated output is owned
outright" for Fixture Corp; the HMP fixture's own "Enron-*shaped*, not Enron-derived" framing, same
ADR, §C3). Neither Enron (real data, admitted only via `scripts/real_data_exceptions.py`, never
committed) nor the VAST-shaped fixture (§C4, not yet built) exists as a file in this tree today —
checked directly, `git grep`/`find` for either name returns nothing. This registry therefore has
two real entries, not the seven narrative rows `tools/demo_guide_check.py`'s own `DEMO_REGISTRY`
enumerates — that module keys off `DEMO_GUIDE.md`'s own prose ("Scenario A", "the Ingest Studio"),
a feature-level grain; this one keys off the packaging grain, "which files does the build have to
either include or refuse to include" — the same "shares a shape, not an implementation" distinction
`06_DECISIONS.md` ADR-034 §B10 already draws between `product_tree_link_check.py` and
`decision_log_publication_check.py`. Both registries name the same underlying demos and must be
kept in sync by hand when either changes; nothing today makes that automatic.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

DISTRIBUTION_SHIPPED = "shipped"
DISTRIBUTION_INTERNAL = "internal"


@dataclass(frozen=True)
class DemoManifest:
    """One demo dataset's own manifest. `paths` names every source location this dataset's own
    data lives at, relative to the repository root — what `find_internal_demo_data` (`scripts/
    packaging_gate.py`) checks a built artefact for when this manifest's own `distribution` is
    `internal`, and what an artefact-hygiene reviewer would grep an unpacked bundle for by hand if
    the mechanical check were ever removed."""

    id: str
    distribution: str
    seed_module: str
    paths: tuple[str, ...] = field(default_factory=tuple)
    #: `06_DECISIONS.md` ADR-035 §C7: neither `pip-licenses` nor `license-checker` inspects a data
    #: file's own accompanying licence — "a fixture carrying its own data licence... passes both
    #: scripts unexamined." `None` (both real entries today) means generated, owned outright, no
    #: third-party licence to check — ADR-035 §C5's own "Generated output is owned outright" for
    #: Fixture Corp, and the HMP fixture's own "Enron-*shaped*, not Enron-derived" framing, same
    #: ADR §C3. A future dataset carrying real terms (§C6's own CDLA-Sharing-1.0 case, if IBM
    #: AML-Data were ever used as data rather than AMLSim as a generator) declares them here.
    data_licence: str | None = None

    @property
    def is_shipped(self) -> bool:
        """Strict equality, not a membership test — a misspelled `"Shipped"`/`"SHIPPED"`/`"shiped"`
        or an empty string all fail this and fall to `internal`, exactly as ADR-035 §C1 requires."""
        return self.distribution == DISTRIBUTION_SHIPPED

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> DemoManifest:
        """The path a hand-edited or generated manifest actually takes — `raw.get(...)` rather
        than `raw[...]`, so a genuinely *missing* `distribution` key produces `""` (fails
        `is_shipped`, per the property above) instead of raising `KeyError` and crashing the
        packaging step instead of failing it closed."""
        return cls(
            id=str(raw.get("id", "")),
            distribution=str(raw.get("distribution", "")),
            seed_module=str(raw.get("seed_module", "")),
            paths=tuple(str(p) for p in raw.get("paths", ())),  # type: ignore[union-attr]
        )


#: Sourced from `DEMO_GUIDE.md` §1's own table and verified against the real seed scripts'
#: own imports at the time this module was written — update both together when either changes.
REGISTRY: tuple[DemoManifest, ...] = (
    DemoManifest(
        id="hmp",
        distribution=DISTRIBUTION_SHIPPED,
        seed_module="scripts.seed_hmp_fixture",
        paths=(
            "packages/demo_fixtures/hmp.py",
            "packages/demo_fixtures/hmp_graph.py",
        ),
    ),
    DemoManifest(
        id="fixture-corp",
        distribution=DISTRIBUTION_SHIPPED,
        seed_module="scripts.seed_fixture_corp",
        paths=("packages/demo_fixtures/fixture_corp.py",),
    ),
    # ADR-055. Synthetic, but third-party (Kaggle `ealaxi/paysim1`; simulator GPL-3.0; the data
    # licence is not verified, so `data_licence` stays empty until the owner records it from the
    # Kaggle page). Never shipped; the data lives under `OspreyFlow_Data/`.
    DemoManifest(
        id="paysim",
        distribution=DISTRIBUTION_INTERNAL,
        seed_module="scripts.seed_paysim",
        paths=("OspreyFlow_Data/PaySIM_Dataset/PS_20174392719_1491204439457_log.csv",),
    ),
    # ADR-053. REAL data, admitted for the owner's own machine only through the local exceptions
    # list, never committed, never shipped. The path is a folder: the gate matches by prefix.
    DemoManifest(
        id="enron",
        distribution=DISTRIBUTION_INTERNAL,
        seed_module="scripts.seed_enron",
        paths=("OspreyFlow_Data/Enron_Mails",),
    ),
)


def shipped_manifests(registry: tuple[DemoManifest, ...] = REGISTRY) -> tuple[DemoManifest, ...]:
    return tuple(m for m in registry if m.is_shipped)


def internal_manifests(registry: tuple[DemoManifest, ...] = REGISTRY) -> tuple[DemoManifest, ...]:
    return tuple(m for m in registry if not m.is_shipped)


def main() -> int:
    """`make demo-manifest` — ADR-035 §C1: "prints each demo and its distribution class... so what
    will ship is inspectable before shipping rather than after." """
    for manifest in REGISTRY:
        print(f"{manifest.id}: {manifest.distribution}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
