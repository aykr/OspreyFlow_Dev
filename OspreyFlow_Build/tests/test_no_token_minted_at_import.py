"""A token is minted when a test runs, never when its module is imported (slice CO2b, rule 12).

**Which test fails if the fault returns.** `test_no_test_file_mints_a_token_or_reads_the_clock_at_import`
fails, naming the file, the line and the minter, the moment a `default_claims(`, `sign_token(` or
`entra_claims(` call (or any helper that wraps one, or an `exp`/`iat`/`nbf` built from the wall clock) is
written where Python runs it once, at import: in a decorator (a `parametrize` list), at module or class
level, in a default argument, or in the body of a `module`, `session`, `package` or `class` scope fixture.

The fault it guards: `test_auth_entra_pages.py::test_a_token_from_a_realm_client_without_the_audience_
mapper_is_refused` parametrised its two cases with `default_claims(...)`, which stamps `iat` now and `exp`
now + 300 s, so the token's life began at collection and had ended by the time GitHub's 40 to 49 minute
suite reached the test ("Signature has expired"; runs 44730215386 and 44739376824). The Mac's suite is
fast, so it passed there. `tests/services/api/test_token_clock_independence.py` shows the same fault
red by moving the clock; this file stops the next one being written.

**Folders it walks:** `OspreyFlow_Build/tests/`, every `*.py` below it (test modules, `conftest.py`,
fixtures and helper modules), skipping `__pycache__`. That is the whole of the Python test tree. It does
not walk `OspreyFlow_Core/apps/pages/test/` (TypeScript, a different language and clock: the Node tests
there were read by hand for CO2b, and the report lists them) nor any other repository folder.

Rule 15, the planted shapes: the self-tests below hand the scanner source of the shapes the real tree
used (a `parametrize` of `default_claims(...)` calls, a module constant, a module-scope fixture, ...),
and the same shapes written deferred (a lambda, a call inside the test) to show they are not flagged.
The allowlist's own test shows a stale entry (one that no longer matches a site) fails.
"""

from __future__ import annotations

import ast
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent

#: The functions that stamp a token's life from the wall clock. Helpers that wrap one are found by
#: `_minters()`, so a new wrapper is covered without anyone listing it here.
SEED_MINTERS = frozenset({"default_claims", "sign_token", "entra_claims"})

#: A call that reads the wall clock (`time.monotonic` and `perf_counter` are not it: no token's life
#: is measured with them).
CLOCK_CALLS = frozenset(
    {("time", "time"), ("_time", "time"), ("datetime", "now"), ("datetime", "utcnow")}
)
LIFE_KEYS = frozenset({"exp", "iat", "nbf"})
LONG_SCOPES = frozenset({"module", "session", "package", "class"})
#: A wrapper that calls a minter is itself a minter only when its name says it makes something a request
#: carries (`_bearer`, `_app_token`, `_v1_claims`, `_headers`): `resolve`, `get` and `list` also *call*
#: `sign_token` in some test and are not minters. A wrapper that stamps a life from the clock itself is
#: found whatever its name.
WRAPPER_NAME = re.compile(r"token|claims|bearer|jwt|header|auth|signed|credential|principal", re.I)


@dataclass(frozen=True)
class Site:
    path: str  # relative to the tests folder
    line: int
    what: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.what}"


#: Allowed sites: (path, what) -> why. Each is checked to still match a real site, so an entry cannot
#: outlive the code it excuses. Add one only with a reason a reviewer can test.
ALLOWED: dict[tuple[str, str], str] = {}


# --- the scanner -------------------------------------------------------------------------------------


def _is_clock_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    f = node.func
    if isinstance(f, ast.Attribute):
        base = f.value
        if isinstance(base, ast.Name) and (base.id, f.attr) in CLOCK_CALLS:
            return True
        # `datetime.datetime.now()` / `dt.datetime.now()`
        if isinstance(base, ast.Attribute) and (base.attr, f.attr) in CLOCK_CALLS:
            return True
    return False


def _call_name(node: ast.Call) -> str | None:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def _walk_now(node: ast.AST):  # type: ignore[no-untyped-def]
    """Every node that runs when `node` is evaluated, not when something inside it is later called:
    it does not enter a lambda, a nested `def` or a comprehension-free deferred body."""
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        for child in ast.iter_child_nodes(n):
            if isinstance(child, ast.Lambda | ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            stack.append(child)


def _fixture_scope(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    for dec in fn.decorator_list:
        call = dec if isinstance(dec, ast.Call) else None
        target = call.func if call else dec
        name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", None)
        if name != "fixture" or call is None:
            continue
        for kw in call.keywords:
            if (
                kw.arg == "scope"
                and isinstance(kw.value, ast.Constant)
                and isinstance(kw.value.value, str)
            ):
                return kw.value.value
        # `pytest.fixture("module")` is not valid in pytest 8: scope is keyword-only.
    return None


def _defs(tree: ast.AST):  # type: ignore[no-untyped-def]
    return [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]


def _minters(trees: dict[str, ast.AST]) -> frozenset[str]:
    """The seed minters, plus every function in the tree that calls one or stamps a life from the wall
    clock itself, to a fixed point. By name: a helper that shares a name with an unrelated function is a
    false positive a reviewer can allow with a reason, which is the safe side."""
    found = set(SEED_MINTERS)
    funcs = [(fn, tree) for tree in trees.values() for fn in _defs(tree)]
    changed = True
    while changed:
        changed = False
        for fn, _ in funcs:
            if fn.name in found or fn.name.startswith("test_"):
                continue
            wraps = WRAPPER_NAME.search(fn.name) and any(
                isinstance(n, ast.Call) and _call_name(n) in found for n in ast.walk(fn)
            )
            if _stamps_a_life(fn) or wraps:
                found.add(fn.name)
                changed = True
    return frozenset(found)


def _clock_derived(value: ast.AST, clock_names: frozenset[str] | set[str]) -> bool:
    """A value that holds a wall-clock read, or a name that was assigned from one."""
    return any(
        _is_clock_call(m) or (isinstance(m, ast.Name) and m.id in clock_names)
        for m in ast.walk(value)
    )


def _assigned_from_clock(
    scope_body: list[ast.stmt], outer: frozenset[str] | set[str] = frozenset()
) -> set[str]:
    """Names a body assigns from a clock read (`now = int(time.time())`), without entering a nested def."""
    names: set[str] = set()
    for stmt in scope_body:
        if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
            continue  # its names are its own, bound when it is called
        for n in _walk_now(stmt):
            if isinstance(n, ast.Assign) and _clock_derived(n.value, names | set(outer)):
                names.update(t.id for t in n.targets if isinstance(t, ast.Name))
            elif (
                isinstance(n, ast.AnnAssign)
                and n.value is not None
                and isinstance(n.target, ast.Name)
            ):
                if _clock_derived(n.value, names | set(outer)):
                    names.add(n.target.id)
    return names


def _life_stamps(node: ast.AST):  # type: ignore[no-untyped-def]
    """Each `exp`/`iat`/`nbf` a node sets, as (value node): dict keys and keyword arguments."""
    if isinstance(node, ast.Dict):
        for k, v in zip(node.keys, node.values, strict=True):
            if isinstance(k, ast.Constant) and k.value in LIFE_KEYS:
                yield v
    elif isinstance(node, ast.Call):
        for kw in node.keywords:
            if kw.arg in LIFE_KEYS:
                yield kw.value


def _stamps_a_life(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """A body that sets `exp`, `iat` or `nbf` from the wall clock, directly or through a local name."""
    local = _assigned_from_clock(fn.body)
    return any(_clock_derived(value, local) for n in ast.walk(fn) for value in _life_stamps(n))


def _import_time_nodes(tree: ast.Module):  # type: ignore[no-untyped-def]
    """Yield every node that runs once, at import, or in a long-scope fixture's body."""
    pending: list[ast.AST] = list(tree.body)
    while pending:
        stmt = pending.pop()
        if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
            for dec in stmt.decorator_list:
                yield from _walk_now(dec)
            args = stmt.args
            for default in [*args.defaults, *[d for d in args.kw_defaults if d is not None]]:
                yield from _walk_now(default)
            if _fixture_scope(stmt) in LONG_SCOPES:
                for inner in stmt.body:
                    yield from _walk_now(inner)
                    # a nested def's own body runs only if called, which `_walk_now` does not follow
            continue
        if isinstance(stmt, ast.ClassDef):
            for dec in stmt.decorator_list:
                yield from _walk_now(dec)
            pending.extend(stmt.body)
            continue
        yield from _walk_now(stmt)


def scan_source(source: str, path: str, minters: frozenset[str] = SEED_MINTERS) -> list[Site]:
    tree = ast.parse(source)
    # Names read from the clock at import (`NOW = int(time.time())`): a life built from one is stamped
    # at import wherever it is used, so a use inside a test body is a site too.
    module_clock = _assigned_from_clock(tree.body)
    sites: dict[tuple[int, str], Site] = {}

    def add(node: ast.AST, what: str) -> None:
        line = node.lineno  # type: ignore[attr-defined]
        sites.setdefault((line, what), Site(path, line, what))

    stamped = "exp/iat/nbf is stamped from the wall clock at import"
    for n in _import_time_nodes(tree):
        if isinstance(n, ast.Call) and _call_name(n) in minters:
            add(n, f"{_call_name(n)}(...) runs at import")
        for value in _life_stamps(n):
            if _clock_derived(value, module_clock):
                add(value, stamped)
    for fn in _defs(tree):
        local = _assigned_from_clock(fn.body, module_clock) - module_clock
        for n in ast.walk(fn):
            for value in _life_stamps(n):
                uses_module_clock = any(
                    isinstance(m, ast.Name) and m.id in module_clock and m.id not in local
                    for m in ast.walk(value)
                )
                if uses_module_clock:
                    add(value, stamped)
    return sorted(sites.values(), key=lambda x: (x.path, x.line, x.what))


def tree_files() -> list[Path]:
    return sorted(p for p in TESTS.rglob("*.py") if "__pycache__" not in p.parts)


def scan_tree(root: Path = TESTS) -> list[Site]:
    files = sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)
    trees: dict[str, ast.AST] = {}
    for p in files:
        try:
            trees[str(p.relative_to(root))] = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:  # a fixture that is deliberately not Python is not a test module
            continue
    minters = _minters(trees)
    out: list[Site] = []
    for rel in sorted(trees):
        out.extend(scan_source((root / rel).read_text(encoding="utf-8"), rel, minters))
    return out


# --- the guard over the real tree --------------------------------------------------------------------


def test_no_test_file_mints_a_token_or_reads_the_clock_at_import() -> None:
    """Fails, naming each site, if any file under `tests/` mints a token (or reads the wall clock) where
    it runs once at import. Allowed sites are in `ALLOWED`, each with its reason."""
    allowed = {key for key in ALLOWED}
    found = [s for s in scan_tree() if (s.path, s.what) not in allowed]
    assert not found, (
        "a token is minted (or the wall clock read) when the module is imported, so its life starts at "
        "collection and may end before the test runs on a slow suite. Mint inside the test (parametrise "
        "with overrides or a factory) :\n  " + "\n  ".join(str(s) for s in found)
    )


def test_every_allowed_site_still_exists_and_has_a_reason() -> None:
    sites = {(s.path, s.what) for s in scan_tree()}
    for key, why in ALLOWED.items():
        assert why.strip(), f"{key}: an allowed site needs its reason"
        assert key in sites, f"{key}: allowed, but no such site any more; remove the entry"


def test_the_scan_walks_the_python_test_tree_and_finds_the_helpers() -> None:
    files = {str(p.relative_to(TESTS)) for p in tree_files()}
    assert "conftest.py" in files and "services/api/test_auth_entra_pages.py" in files
    trees = {
        str(p.relative_to(TESTS)): ast.parse(p.read_text(encoding="utf-8")) for p in tree_files()
    }
    minters = _minters(trees)
    # the seeds and a wrapper nobody listed: `_v1_claims` stamps `exp` from the clock itself
    assert SEED_MINTERS <= minters
    assert "_v1_claims" in minters


# --- rule 15: the scanner is shown to find each shape the real tree used, and to pass the safe one ------


def _flag(source: str) -> list[str]:
    return [s.what for s in scan_source(textwrap.dedent(source), "planted.py")]


@pytest.mark.parametrize(
    "source",
    [
        # the shape CO2's test had: a parametrize list built at import
        """
        import pytest
        @pytest.mark.parametrize("claims", [default_claims(azp="a"), default_claims(aud="b")])
        def test_x(claims): ...
        """,
        # a pytest.param inside it
        """
        @pytest.mark.parametrize("c", [pytest.param(default_claims(), id="x")])
        def test_x(c): ...
        """,
        # the expiry case alone, as test_auth.py wrote it
        """
        import time
        @pytest.mark.parametrize("c", [default_claims(iat=int(time.time()) - 3600)])
        def test_x(c): ...
        """,
        # a module constant
        """
        GOOD = sign_token(key, default_claims())
        """,
        # a module-level dict whose life comes from the wall clock
        """
        import time
        CLAIMS = {"sub": "a", "exp": int(time.time()) + 300}
        """,
        # a clock read at import, used for a life inside a test: the read is still the import's
        """
        import time
        NOW = int(time.time())
        def test_x():
            claims = {"sub": "a", "iat": NOW, "exp": NOW + 300}
        """,
        # a class body
        """
        class TestX:
            claims = default_claims()
        """,
        # a default argument, evaluated once at def
        """
        def helper(claims=default_claims()): ...
        """,
        # a module-scope fixture
        """
        @pytest.fixture(scope="module")
        def token(keypair):
            return sign_token(keypair[0], default_claims())
        """,
        # a session-scope fixture, with the decorator through an alias
        """
        @pytest.fixture(scope="session")
        def claims():
            return entra_claims()
        """,
    ],
    ids=[
        "parametrize-list",
        "pytest-param",
        "expired-case",
        "module-constant",
        "module-dict-from-clock",
        "module-clock-name-used-in-a-test",
        "class-body",
        "default-argument",
        "module-fixture",
        "session-fixture",
    ],
)
def test_the_scanner_finds_each_shape_that_starts_a_token_s_life_at_import(source: str) -> None:
    assert _flag(source), "the scanner missed a token minted at import"


@pytest.mark.parametrize(
    "source",
    [
        # parametrised with overrides, minted in the test (the fix)
        """
        @pytest.mark.parametrize("overrides", [{"aud": "account"}, {}])
        def test_x(overrides):
            claims = default_claims(**overrides)
        """,
        # a factory, minted when the case runs
        """
        @pytest.mark.parametrize("make", [lambda: default_claims(azp="a")])
        def test_x(make):
            make()
        """,
        # a function-scope fixture (the default) is minted per test
        """
        @pytest.fixture
        def token(keypair):
            return sign_token(keypair[0], default_claims())
        """,
        """
        @pytest.fixture(scope="function")
        def token(keypair):
            return sign_token(keypair[0], default_claims())
        """,
        # a module-scope fixture that mints nothing
        """
        @pytest.fixture(scope="module")
        def keys():
            return generate()
        """,
        # a clock read at import that is not a token's life (a date window, say) is not this guard's
        """
        from datetime import UTC, datetime
        NOW = datetime.now(UTC)
        def test_x():
            window = {"from": NOW}
        """,
        # a clock read inside the test is the fix itself
        """
        import time
        def test_x():
            now = int(time.time())
            claims = {"iat": now, "exp": now + 300}
        """,
        # a fixed instant is not the wall clock
        """
        CLAIMS = {"sub": "a", "iat": 1_763_000_000, "exp": 1_763_000_000 + 300}
        """,
        # a nested helper called only inside the test
        """
        def test_x():
            def mint():
                return default_claims()
            mint()
        """,
    ],
    ids=[
        "overrides",
        "lambda-factory",
        "function-fixture",
        "explicit-function-fixture",
        "module-fixture-no-token",
        "clock-at-import-not-a-life",
        "clock-read-in-the-test",
        "fixed-instant",
        "nested-helper",
    ],
)
def test_the_scanner_passes_a_token_minted_when_the_test_runs(source: str) -> None:
    assert _flag(source) == []


def test_a_wrapper_helper_called_at_import_is_found_through_the_tree(tmp_path: Path) -> None:
    """The real call-site shape: the wrapper is defined in one module and imported by another."""
    (tmp_path / "helpers.py").write_text(
        "import time\n"
        "def _app_token(key, **over):\n"
        "    return sign_token(key, {'exp': int(time.time()) + 3600, **over})\n"
    )
    (tmp_path / "test_a.py").write_text(
        "import pytest\n"
        "from helpers import _app_token\n"
        "@pytest.mark.parametrize('t', [_app_token(None)])\n"
        "def test_a(t): ...\n"
    )
    found = scan_tree(tmp_path)
    assert [(s.path, s.what) for s in found] == [("test_a.py", "_app_token(...) runs at import")]
