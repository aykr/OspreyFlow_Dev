"""A test directory without `__init__.py` is put on `sys.path` by pytest, and every module in it
then becomes importable by its bare name, ahead of the product's own.

Seen while moving the tests into the Build folder (ADR-054): `tests/golden/harness.py` sat in such
a directory, and once any earlier test stopped importing the product's `harness` first, every test
that did `from harness.apply import ...` failed with "'harness' is not a package". The suite had
passed before only because of the order in which modules happened to be imported. Each test below
names what it would catch.
"""

from __future__ import annotations

from pathlib import Path

from tools.layout import BUILD, CORE

TESTS = BUILD / "tests"


def _product_names() -> set[str]:
    names = {p.name for p in CORE.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))}
    names |= {p.stem for p in CORE.glob("*.py")}
    packages = CORE / "packages"
    names |= {p.name for p in packages.iterdir() if p.is_dir() and not p.name.startswith(".")}
    names |= {p.stem for p in packages.glob("*.py")}
    return names


def _directories_pytest_puts_on_the_path() -> list[Path]:
    """Test directories with no `__init__.py`, which pytest inserts into `sys.path`."""
    return [
        d
        for d in [TESTS, *TESTS.rglob("*")]
        if d.is_dir()
        and d.name != "__pycache__"
        and not (d / "__init__.py").exists()
        and any(d.glob("*.py"))
    ]


def _clashes(directories: list[Path], product: set[str]) -> list[str]:
    return [
        f"{d.name}/{entry.name}"
        for d in directories
        for entry in d.iterdir()
        if (entry.suffix == ".py" and entry.stem in product)
        or (entry.is_dir() and entry.name in product and entry.name != "__pycache__")
    ]


def test_no_directory_on_the_path_holds_a_module_named_like_a_product_module() -> None:
    clashes = _clashes(_directories_pytest_puts_on_the_path(), _product_names())
    assert clashes == [], f"these would shadow the product once on the path: {clashes}"


def test_the_check_can_see_a_clash_when_there_is_one(tmp_path: Path) -> None:
    """The check above passes when there is nothing to find, so prove it finds something."""
    (tmp_path / "harness.py").write_text("", encoding="utf-8")
    (tmp_path / "unrelated.py").write_text("", encoding="utf-8")
    assert _clashes([tmp_path], {"harness"}) == [f"{tmp_path.name}/harness.py"]
