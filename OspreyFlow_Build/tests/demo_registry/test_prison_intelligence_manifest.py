"""ADR-127 Amendment 23, "The registration": the Prison Intelligence Dataset is a shipped, seeded
demo, so its generator code, its seventeen recipes and its connector layout travel in the artefact
and the packaging gate must not refuse them. What would fail if it drifted:

- a PID module or recipe added to the folder and left out of the manifest, so the artefact would
  carry it unregistered (`test_the_manifest_lists_every_pid_module_and_recipe_and_nothing_else`);
- a path that no longer exists, which the gate would never match
  (`test_every_listed_path_exists`);
- the manifest's seed module not the seed that exists (`test_it_is_shipped_and_seeded_by_the_seed_script`).
"""

from __future__ import annotations

from scripts.demo_registry import REGISTRY, seeded_manifests
from tools import packaging_gate
from tools.layout import CORE

FIXTURES = CORE / "packages" / "demo_fixtures"


def _manifest():  # type: ignore[no-untyped-def]
    return next(m for m in REGISTRY if m.id == "prison-intelligence")


def test_it_is_shipped_and_seeded_by_the_seed_script() -> None:
    manifest = _manifest()
    assert manifest.is_shipped and manifest.is_seeded
    assert manifest in seeded_manifests()
    assert manifest.seed_module == "scripts.seed_pid"
    assert manifest.data_licence is None and manifest.attribution is None, "generated, owned"
    assert (CORE / "scripts" / "seed_pid.py").is_file()


def test_the_manifest_lists_every_pid_module_and_recipe_and_nothing_else() -> None:
    listed = set(_manifest().paths)
    on_disk = {
        f"packages/demo_fixtures/{p.name}"
        for pattern in ("pid_*.py", "pid_*_recipe.yaml")
        for p in FIXTURES.glob(pattern)
    }
    assert len(on_disk) == 5 + 17, "five modules and seventeen recipes"
    assert listed == on_disk | {"connectors/pin-calls-csv.yaml"}


def test_every_listed_path_exists() -> None:
    for path in _manifest().paths:
        assert (CORE / path).is_file(), path


def test_its_paths_are_not_refused_by_the_gate() -> None:
    assert packaging_gate.find_internal_demo_data(list(_manifest().paths), registry=REGISTRY) == []
