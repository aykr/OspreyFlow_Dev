"""Slice AD1d: `test-file-coverage-check` knows a test that starts its own private database is not a
live-service test (the owner's ruling (c), 25 November 2026), and the one shared helper that starts it.

**The rule under test.** A test file that imports `asyncpg` **and** imports `tests.private_postgres` (a
real import, read from the file's `import` statements), and has no other live-service marker and no
`PostgresConfig.from_env()` call, is not live-service: it opens a PostgreSQL of its own in a temporary
folder and needs no shared service. Anything else stays as before. No comment, name or flag a file can
write opts it out: the only way is the import of the helper that really starts the private database.

**How each case is planted** (`CLAUDE.md` rule 15: the plant takes the shape the real call site
receives): a real file under a temporary `tests/` tree, found by `list_test_files()` (the tree it
reads, `TESTS_DIR`, pointed at the temporary one) and judged by `find_misclassified`, the very
functions `main()` calls. A live-service file there is named in a message; a file that is not live is
not.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from tools.layout import REPO as REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "tools"))

import test_file_coverage_check as coverage  # noqa: E402

HELPER_IMPORT = "from tests.private_postgres import running_postgres"

_A_TEST = "\n\ndef test_it() -> None:\n    assert True\n"


def _problems(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str) -> list[str]:
    """What the check says of one planted test file, read as `main()` reads files: listed by
    `list_test_files()` and judged by `find_misclassified` with no job listing it anywhere."""
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_planted.py").write_text(source + _A_TEST, encoding="utf-8")
    monkeypatch.setattr(coverage, "TESTS_DIR", tests)
    files = coverage.list_test_files()
    assert [p.name for p in files] == ["test_planted.py"]
    return coverage.find_misclassified(files, set(), {})


def test_a_file_importing_asyncpg_and_the_helper_is_not_live_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = f"import asyncpg\n{HELPER_IMPORT}\n"
    assert _problems(tmp_path, monkeypatch, source) == []


def test_the_helper_is_read_from_a_plain_import_of_its_module_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for form in ("import tests.private_postgres", "from tests import private_postgres"):
        sub = tmp_path / form.replace(" ", "_").replace(".", "_")
        sub.mkdir()
        assert _problems(sub, monkeypatch, f"import asyncpg\n{form}\n") == [], form


def test_a_file_importing_asyncpg_without_the_helper_is_live_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    problems = _problems(tmp_path, monkeypatch, "import asyncpg\n")
    assert len(problems) == 1 and "test_planted.py" in problems[0]
    assert "in neither the `test` job's ignore list nor any live-service job" in problems[0]


@pytest.mark.parametrize(
    "other",
    [
        "from graph_arcadedb.client import ArcadeDBClient",
        "from graph_arcadedb.client import ArcadeDBConfig",
        "from working_set.store import ValkeyWorkingSetStore",
        "from tests.conformance.registry import GRAPH_PORT_ADAPTERS",
    ],
)
def test_a_file_importing_the_helper_and_another_marker_is_live_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, other: str
) -> None:
    problems = _problems(tmp_path, monkeypatch, f"import asyncpg\n{HELPER_IMPORT}\n{other}\n")
    assert len(problems) == 1 and "test_planted.py" in problems[0]


def test_a_file_importing_the_helper_and_reading_the_live_service_env_is_live_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = (
        f"import os\nimport asyncpg\n{HELPER_IMPORT}\n"
        'URL = os.environ.get("OSPREY_TEST_COMPOSE_FILE")\n'
    )
    problems = _problems(tmp_path, monkeypatch, source)
    assert len(problems) == 1 and "test_planted.py" in problems[0]


def test_a_file_importing_the_helper_and_calling_postgres_config_from_env_is_live_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = (
        "import asyncpg\n"
        f"{HELPER_IMPORT}\n"
        "from services.api.config import PostgresConfig\n"
        "CONFIG = PostgresConfig.from_env()\n"
    )
    problems = _problems(tmp_path, monkeypatch, source)
    assert len(problems) == 1 and "test_planted.py" in problems[0]


def test_a_file_that_only_names_the_helper_in_text_is_live_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The name in a docstring, a comment or a string is not the import."""
    source = (
        f'"""Uses {HELPER_IMPORT}, or so it says."""\n'
        "import asyncpg\n"
        f"# {HELPER_IMPORT}\n"
        f'NOTE = "{HELPER_IMPORT}"\n'
        "OTHER = 'tests.private_postgres'\n"
    )
    problems = _problems(tmp_path, monkeypatch, source)
    assert len(problems) == 1 and "test_planted.py" in problems[0]


def test_a_relative_import_of_another_modules_namesake_is_not_the_helper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only `tests.private_postgres` counts: a module of another package with the same last word does not."""
    source = "import asyncpg\nfrom elsewhere.private_postgres import running_postgres\n"
    problems = _problems(tmp_path, monkeypatch, source)
    assert len(problems) == 1 and "test_planted.py" in problems[0]


# --- the helper itself -------------------------------------------------------------------------


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


async def test_the_helper_starts_a_real_postgresql_under_the_temporary_folder_and_removes_it(
    tmp_path: Path,
) -> None:
    import asyncpg

    from tests import port_guard
    from tests.private_postgres import running_postgres

    with running_postgres(tmp_path) as database:
        assert database.host == "127.0.0.1"
        assert database.port not in port_guard.reserved_ports()
        assert database.port not in port_guard.LIVE_PORTS
        assert tmp_path in database.folder.parents
        assert tmp_path in database.data_dir.parents
        assert database.data_dir.is_dir()
        pid = int((database.data_dir / "postmaster.pid").read_text().splitlines()[0])
        assert _alive(pid)

        connection = await asyncpg.connect(
            host=database.host,
            port=database.port,
            user=database.user,
            database=database.database,
            timeout=30,
        )
        try:
            assert await connection.fetchval("SELECT 1") == 1
            assert "PostgreSQL" in await connection.fetchval("SELECT version()")
        finally:
            await connection.close()

    assert not _alive(pid)
    assert not database.folder.exists()
    assert list(tmp_path.iterdir()) == []


def test_the_helper_stops_and_removes_what_it_started_whatever_the_test_did(
    tmp_path: Path,
) -> None:
    from tests.private_postgres import running_postgres

    seen: dict[str, object] = {}
    with pytest.raises(RuntimeError, match="the test failed"):
        with running_postgres(tmp_path) as database:
            seen["pid"] = int((database.data_dir / "postmaster.pid").read_text().splitlines()[0])
            seen["folder"] = database.folder
            raise RuntimeError("the test failed")
    assert isinstance(seen["pid"], int) and not _alive(seen["pid"])
    assert isinstance(seen["folder"], Path) and not seen["folder"].exists()


def test_with_no_initdb_the_helper_skips_in_words_naming_initdb(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests import private_postgres

    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    monkeypatch.setattr(private_postgres, "BIN_DIR_GLOBS", ())
    with pytest.raises(pytest.skip.Exception, match="initdb"):
        with private_postgres.running_postgres(tmp_path / "work"):
            pytest.fail("a private database was started with no initdb on the machine")
    assert not (tmp_path / "work").exists()


def test_as_root_the_helper_skips_in_words_naming_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PostgreSQL's `initdb` refuses to run as root; the helper says so rather than failing."""
    from tests import private_postgres

    monkeypatch.setattr(os, "geteuid", lambda: 0)
    with pytest.raises(pytest.skip.Exception, match="root"):
        with private_postgres.running_postgres(tmp_path / "work"):
            pytest.fail("a private database was started as root")
    assert not (tmp_path / "work").exists()
