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

**What the registry holds today, checked directly against `DEMO_GUIDE.md` §1's own table and the
seed scripts' own imports.** Four entries, every one `shipped`. Three
entries are synthetic, generated and seeded from code in this repository (`hmp`, `fixture-corp`,
`operation-ledger`; ADR-035 §C5's "Generated output is owned outright"). `paysim` is shipped as a
*download*: its data is third-party, CC-BY-SA-4.0, and is fetched by the person who wants it, never
placed in an artefact (`06_DECISIONS.md` ADR-114 Amendment 1, which supersedes ADR-055 §3's
`internal`). An `internal` demo — real data admitted only through `scripts/real_data_exceptions.py`
— is registered outside this repository, beside its own code, and never published with it
(ADR-114 Amendment 2); the packaging and publishing gates judge an artefact against both lists. The
VAST-shaped fixture (§C4) is not built. This module keys off
the packaging grain, "which files does the build include or refuse"; `tools/demo_guide_check.py`'s
own `DEMO_REGISTRY` keys off `DEMO_GUIDE.md`'s prose, a feature-level grain (ADR-034 §B10's
"shares a shape, not an implementation"). Both name the same demos and are kept in sync by hand.

**`delivery` fails closed too** (ADR-114 Amendment 1 decision 1): `is_seeded` is a strict
`== "seed"`, so a missing or misspelt value is not seeded, and the packaging gate then refuses that
manifest's data whatever its `distribution`.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

DISTRIBUTION_SHIPPED = "shipped"
DISTRIBUTION_INTERNAL = "internal"

#: ADR-114 Amendment 1: how a shipped demo's data reaches the person using it. `seed` means the
#: data is generated from code in the artefact; `download` means it is fetched and never bundled.
DELIVERY_SEED = "seed"
DELIVERY_DOWNLOAD = "download"


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


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
    #: ADR-114 Amendment 1: `seed` or `download`; see `is_seeded`. Defaults to `seed`, but
    #: `from_dict` defaults a missing key to empty, which is not seeded.
    delivery: str = DELIVERY_SEED
    #: The credit a share-alike or attribution licence requires, or `None` where none is owed.
    attribution: str | None = None

    @property
    def is_shipped(self) -> bool:
        """Strict equality, not a membership test — a misspelled `"Shipped"`/`"SHIPPED"`/`"shiped"`
        or an empty string all fail this and fall to `internal`, exactly as ADR-035 §C1 requires."""
        return self.distribution == DISTRIBUTION_SHIPPED

    @property
    def is_seeded(self) -> bool:
        """Strict equality, for the same fail-closed reason as `is_shipped`: a misspelt `"Seed"`,
        an empty string or a missing key is not seeded, and the packaging gate refuses the data of
        every manifest that is not seeded (ADR-114 Amendment 1 decision 1)."""
        return self.delivery == DELIVERY_SEED

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
            delivery=str(raw.get("delivery", "")),
            data_licence=_optional_text(raw.get("data_licence")),
            attribution=_optional_text(raw.get("attribution")),
        )


#: Sourced from `DEMO_GUIDE.md` §1's own table and verified against the real seed scripts'
#: own imports at the time this module was written — update both together when either changes.
REGISTRY: tuple[DemoManifest, ...] = (
    DemoManifest(
        id="hmp",
        distribution=DISTRIBUTION_SHIPPED,
        delivery=DELIVERY_SEED,
        seed_module="scripts.seed_hmp_fixture",
        paths=(
            "packages/demo_fixtures/hmp.py",
            "packages/demo_fixtures/hmp_graph.py",
        ),
    ),
    DemoManifest(
        id="fixture-corp",
        distribution=DISTRIBUTION_SHIPPED,
        delivery=DELIVERY_SEED,
        seed_module="scripts.seed_fixture_corp",
        paths=("packages/demo_fixtures/fixture_corp.py",),
    ),
    # ADR-114 Amendment 1. Synthetic and generated by this project, so owned outright.
    DemoManifest(
        id="operation-ledger",
        distribution=DISTRIBUTION_SHIPPED,
        delivery=DELIVERY_SEED,
        seed_module="scripts.seed_ledger_fixture",
        paths=(
            "packages/demo_fixtures/ledger.py",
            "packages/demo_fixtures/ledger_onboarding_applications.csv",
            "packages/demo_fixtures/screening_list_synthetic.yaml",
        ),
    ),
    # ADR-114 Amendment 1 (superseding ADR-055 §3's `internal`). Third-party simulated data
    # (Kaggle `ealaxi/paysim1`), CC-BY-SA-4.0, so shipped as a download only: the file is fetched
    # and checked, never placed in an artefact, and the packaging gate refuses it there.
    DemoManifest(
        id="paysim",
        distribution=DISTRIBUTION_SHIPPED,
        delivery=DELIVERY_DOWNLOAD,
        seed_module="scripts.seed_paysim",
        paths=("OspreyFlow_Data/PaySIM_Dataset/PS_20174392719_1491204439457_log.csv",),
        data_licence="CC-BY-SA-4.0",
        attribution=(
            'E. A. Lopez-Rojas, A. Elmir and S. Axelsson, "PaySim: A financial mobile money '
            'simulator for fraud detection", EMSS 2016 (Larnaca, Cyprus)'
        ),
    ),
)


def shipped_manifests(registry: tuple[DemoManifest, ...] = REGISTRY) -> tuple[DemoManifest, ...]:
    return tuple(m for m in registry if m.is_shipped)


def internal_manifests(registry: tuple[DemoManifest, ...] = REGISTRY) -> tuple[DemoManifest, ...]:
    return tuple(m for m in registry if not m.is_shipped)


def seeded_manifests(registry: tuple[DemoManifest, ...] = REGISTRY) -> tuple[DemoManifest, ...]:
    return tuple(m for m in registry if m.is_shipped and m.is_seeded)


def downloaded_manifests(
    registry: tuple[DemoManifest, ...] = REGISTRY,
) -> tuple[DemoManifest, ...]:
    return tuple(m for m in registry if m.is_shipped and m.delivery == DELIVERY_DOWNLOAD)


def main() -> int:
    """`make demo-manifest` — ADR-035 §C1: "prints each demo and its distribution class... so what
    will ship is inspectable before shipping rather than after." """
    for manifest in REGISTRY:
        print(f"{manifest.id}: {manifest.distribution} ({manifest.delivery or 'no delivery'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
