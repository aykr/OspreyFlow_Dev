"""Every recipe committed to the repository passes the engine's pin check against the deployment
ontology (`06_DECISIONS.md` ADR-120 Amendment 1, decision 3). The recipes are found by content, a
top-level `row_template`, among the files git tracks, not by directory or name, so a recipe added
anywhere in the two trees is checked without anyone remembering to list it.

What each test checks, and the violation that fails it:
- `test_the_committed_recipes_are_found_by_content_and_include_the_ledger_five`: the search missing
  a tree (it would then check nothing and pass), or the five Ledger recipes, which write FIBO types,
  not being among those found.
- `test_every_committed_recipe_passes_the_pin_check`: a committed recipe that writes or names a pack
  without pinning it at the loaded version, which the engine would refuse at its next run. This is
  the claim "no recipe that loads today is refused" checked rather than asserted.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml
from services.ingest.recipe_loader import load_recipe

from ontology.packs import load_deployment_ontology

_BUILD = Path(__file__).resolve().parents[2]
_REPOSITORY = _BUILD.parent
_ROOTS = ("OspreyFlow_Core", "OspreyFlow_Build")
_LEDGER_FIVE = (
    "ledger_transactions",
    "ledger_kyc",
    "ledger_companies",
    "ledger_onboarding",
    "ledger_ownership",
)


def _committed_recipes() -> list[Path]:
    """Every tracked YAML file in the two trees whose top-level mapping has a `row_template`.

    The candidates come from `git ls-files`, so what is checked is what is committed: no
    dependency folder, virtual environment or generated output can be walked into or missed.
    """
    listed = subprocess.run(
        [
            "git",
            "ls-files",
            "-z",
            "--",
            *(f"{root}/**/*.yaml" for root in _ROOTS),
            *(f"{root}/**/*.yml" for root in _ROOTS),
        ],
        cwd=_REPOSITORY,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    found: list[Path] = []
    for name in sorted({entry for entry in listed.split("\0") if entry}):
        path = _REPOSITORY / name
        if not path.is_file():
            continue
        text = path.read_text(errors="replace")
        if "row_template" not in text:
            continue
        try:
            document = yaml.safe_load(text)
        except yaml.YAMLError:
            continue
        if isinstance(document, dict) and "row_template" in document:
            found.append(path)
    return found


def test_the_committed_recipes_are_found_by_content_and_include_the_ledger_five() -> None:
    found = _committed_recipes()
    stems = {path.stem for path in found}
    for ledger in _LEDGER_FIVE:
        assert any(stem.startswith(ledger) for stem in stems), f"{ledger} was not found"
    assert len(found) >= 20, (
        f"only {len(found)} recipes found; the search is not reaching the trees"
    )


@pytest.mark.parametrize("path", _committed_recipes(), ids=lambda p: p.name)
def test_every_committed_recipe_passes_the_pin_check(path: Path) -> None:
    from services.ingest.engine import check_recipe_pins

    check_recipe_pins(load_recipe(path), load_deployment_ontology())
