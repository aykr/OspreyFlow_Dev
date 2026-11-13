"""The real-Caddy proxy for the shared key's tests is a fixtures module of its own (CARRIES; POST_051's
step B), as `tls_fixtures.py` is: no test module takes it from `test_access_key_proxy.py`, another
lane's test file, whose own tests, marks and helpers would come with it. Admin's refresh tests did
until 13 November 2026."""

from __future__ import annotations

import ast
from pathlib import Path

TESTS = Path(__file__).resolve().parents[1]


def _imports_from(source: str, module: str) -> list[str]:
    """The names a module imports from `module` (relative, `tests.harness.` or bare), at any depth."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and (node.module or "").rsplit(".", 1)[-1] == module:
            found += [alias.name for alias in node.names]
        elif isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name.rsplit(".", 1)[-1] == module]
    return found


def test_no_test_module_takes_the_proxy_from_the_proxy_s_test_file() -> None:
    takers = {
        str(path.relative_to(TESTS)): names
        for path in sorted(TESTS.rglob("*.py"))
        if path.name != Path(__file__).name
        and (names := _imports_from(path.read_text(encoding="utf-8"), "test_access_key_proxy"))
    }
    assert takers == {}


def test_the_proxy_and_its_skip_are_the_shared_module_s() -> None:
    for name in ("test_access_key_proxy.py", "test_refresh_silent_round_through_the_key.py"):
        source = (TESTS / "harness" / name).read_text(encoding="utf-8")
        assert {"proxy", "NEEDS_CADDY"} <= set(_imports_from(source, "access_key_proxy_fixtures")), name
        assert "pytestmark = NEEDS_CADDY" in source, name


def test_the_check_sees_each_shape_of_the_import() -> None:
    """Rule 15: the shape admin's file had, and the others a later file might take."""
    assert _imports_from("from .test_access_key_proxy import HOST, _Proxy, proxy\n", "test_access_key_proxy") == [
        "HOST", "_Proxy", "proxy"]  # fmt: skip
    assert _imports_from("from tests.harness.test_access_key_proxy import proxy\n", "test_access_key_proxy") == ["proxy"]
    assert _imports_from("def f():\n    from .test_access_key_proxy import KEY\n", "test_access_key_proxy") == ["KEY"]
    assert _imports_from("import tests.harness.test_access_key_proxy\n", "test_access_key_proxy") == [
        "tests.harness.test_access_key_proxy"]  # fmt: skip
    assert _imports_from("from .access_key_proxy_fixtures import proxy\n", "test_access_key_proxy") == []
