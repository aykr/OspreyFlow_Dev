"""The drift gate `scripts/test_file_coverage_check.py`'s own docstring names in full — the
orphan check and the live-service classification check, proven non-vacuous here the same way
`tests/test_route_coverage_check.py`/`tests/test_domain_model_coverage_check.py` already prove
their own gates.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from test_file_coverage_check import (  # noqa: E402
    _load,
    find_misclassified,
    find_orphaned,
    find_stale_entries,
    is_live_service_file,
    list_test_files,
    load_allowlist,
)


def test_no_new_drift_beyond_the_allowlist() -> None:
    test_job_ignored, live_job_tokens = _load()
    test_files_abs = list_test_files()
    test_files = [str(p.relative_to(REPO_ROOT)) for p in test_files_abs]
    allowlist = load_allowlist()

    orphaned = find_orphaned(test_files, test_job_ignored, live_job_tokens)
    new_orphans = sorted(set(orphaned) - allowlist)
    misclassified = find_misclassified(test_files_abs, test_job_ignored, live_job_tokens)

    assert new_orphans == [], (
        f"test file(s) reachable by no CI job and not in the allowlist: {new_orphans}"
    )
    assert misclassified == [], f"live-service test file(s) not correctly wired: {misclassified}"


def test_no_stale_allowlist_entries() -> None:
    test_job_ignored, live_job_tokens = _load()
    test_files_abs = list_test_files()
    test_files = [str(p.relative_to(REPO_ROOT)) for p in test_files_abs]
    allowlist = load_allowlist()

    stale = find_stale_entries(test_files, test_job_ignored, live_job_tokens, allowlist)

    assert stale == [], f"stale allowlist entr(ies): {stale} — remove them."


def test_the_orphan_check_fires_for_a_file_referenced_by_no_job() -> None:
    """Proves the gate is not vacuous by naming the test that would fail. A file
    ignored by `test` (so not covered by its own default collection) and absent from every
    live-service job's own explicit list is reachable by nothing at all."""
    orphaned = find_orphaned(
        ["tests/totally_fictional_test.py"],
        test_job_ignored={"tests/totally_fictional_test.py"},
        live_job_tokens={"conformance": set()},
    )
    assert orphaned == ["tests/totally_fictional_test.py"]


def test_a_file_covered_by_the_fast_jobs_default_collection_is_not_orphaned() -> None:
    """A file not ignored by `test` and not in any live-service job's own list is still covered —
    by `test`'s own default, unignored collection — the exact shape the vast majority of this
    repo's own test files take."""
    orphaned = find_orphaned(
        ["tests/services/api/test_ordinary_fake_backed.py"],
        test_job_ignored=set(),
        live_job_tokens={"conformance": set()},
    )
    assert orphaned == []


def test_classification_recognises_a_real_arcadedb_import() -> None:
    source = "from adapters.graph_arcadedb.testing import arcadedb_adapter\n"
    assert is_live_service_file(source) is True


def test_classification_recognises_a_real_valkey_client_import() -> None:
    source = "from valkey.asyncio import Valkey\n"
    assert is_live_service_file(source) is True


def test_classification_recognises_a_real_postgres_from_env_call_but_not_a_bare_import() -> None:
    """The `PostgresConfig` false positive this gate's own first real run found:
    `test_auth.py`/`test_websocket_auth.py` import `PostgresConfig` only to build an inert config
    object with dummy placeholder credentials, never connected to — only an actual `.from_env()`
    call is the real signal."""
    bare_import = "from services.api.config import PostgresConfig\n\nPostgresConfig(host='x')\n"
    real_call = "from services.api.config import PostgresConfig\n\nPostgresConfig.from_env()\n"
    assert is_live_service_file(bare_import) is False
    assert is_live_service_file(real_call) is True


def test_a_docstring_naming_a_marker_to_explain_its_own_absence_is_not_misclassified() -> None:
    """The `working_set/test_service.py` false positive this gate's own first real run found: a
    module docstring stating the file does *not* use `ValkeyWorkingSetStore` must not trip the
    check — only a real import does (`ast.parse`-checked, never a substring search)."""
    source = (
        '"""Exercises the service against fakes, not `ValkeyWorkingSetStore` or a real '
        'adapter, which is why this needs neither Valkey nor ArcadeDB to run."""\n'
        "from .fakes import FakeGraphPort, FakeWorkingSetStore\n"
    )
    assert is_live_service_file(source) is False


class _FakeTestFile:
    """A `Path`-shaped stand-in so `find_misclassified` can be exercised against fabricated
    content without a real file on disk — the same "no real file touched" discipline this gate's
    own other proof cases already follow."""

    def __init__(self, rel: str, source: str) -> None:
        self._rel = rel
        self._source = source

    def relative_to(self, _root: Path) -> str:
        return self._rel

    def read_text(self, encoding: str = "utf-8") -> str:  # noqa: ARG002
        return self._source


def test_a_live_service_file_missing_from_the_live_job_list_is_caught_even_if_ignored() -> None:
    fake = _FakeTestFile(
        "tests/fake_live_service_test.py", "from valkey.asyncio import Valkey\n"
    )
    misclassified = find_misclassified(
        [fake],  # type: ignore[list-item]
        test_job_ignored={"tests/fake_live_service_test.py"},
        live_job_tokens={"conformance": set()},
    )
    assert misclassified == [
        "tests/fake_live_service_test.py: ignored by `test` but not run by any live-service job"
    ]


def test_a_live_service_file_missing_from_the_ignore_list_is_caught_even_if_covered() -> None:
    fake = _FakeTestFile(
        "tests/fake_live_service_test.py", "from valkey.asyncio import Valkey\n"
    )
    misclassified = find_misclassified(
        [fake],  # type: ignore[list-item]
        test_job_ignored=set(),
        live_job_tokens={"conformance": {"tests/fake_live_service_test.py"}},
    )
    assert misclassified == [
        "tests/fake_live_service_test.py: needs a live service but is not ignored by the `test` job"
    ]
