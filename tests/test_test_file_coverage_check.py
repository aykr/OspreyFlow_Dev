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
    find_makefile_ci_drift,
    find_misclassified,
    find_orphaned,
    find_stale_entries,
    is_live_service_file,
    job_tokens,
    list_test_files,
    load_allowlist,
    makefile_test_ignored,
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


def test_makefile_test_target_agrees_with_ci_ymls_test_job() -> None:
    """The real-tree proof of `find_makefile_ci_drift` — `Makefile`'s own `test` target's
    `--ignore` list and `ci.yml`'s own `test` job's, compared directly. Red against this tree
    before `Makefile` was fixed to add `test_ws_ticket.py`/`test_bundle_exit_test.py`/
    `test_harness_image.py` (26 September 2026); green after."""
    ci_ignored, _ = _load()
    missing_from_makefile, missing_from_ci = find_makefile_ci_drift(
        ci_ignored, makefile_test_ignored()
    )
    assert missing_from_makefile == [], (
        f"`ci.yml` ignores these but `Makefile` does not: {missing_from_makefile}"
    )
    assert missing_from_ci == [], (
        f"`Makefile` ignores these but `ci.yml` does not: {missing_from_ci}"
    )


def test_makefile_test_ignored_parses_a_backslash_continued_recipe_line() -> None:
    """`make`'s own line-continuation shape, tolerated per this gate's own docstring — not
    exercised by the real `Makefile` today (one physical line), so proven here against a fabricated
    one instead."""
    fake_makefile = (
        ".PHONY: test\n"
        "\n"
        "test:\n"
        "\t$(PYTEST) --ignore=tests/fake_one.py \\\n"
        "\t\t--ignore=tests/fake_two.py\n"
        "\tnpm test\n"
        "\n"
        "dev-up:\n"
        "\tdocker compose up -d\n"
    )
    assert makefile_test_ignored(fake_makefile) == {"tests/fake_one.py", "tests/fake_two.py"}


def test_makefile_test_ignored_is_not_fooled_by_a_comment_between_targets() -> None:
    """The same class of bug `job_tokens`'s own comment-stripping fixes for `ci.yml` — a comment
    line between `test:`'s own recipe and the next target header must not be scanned for
    `tests/...` tokens as if it were part of `test:`'s own recipe."""
    fake_makefile = (
        "test:\n"
        "\t$(PYTEST) --ignore=tests/fake_one.py\n"
        "\n"
        "# See tests/fake_two.py for the reason this target exists.\n"
        "dev-up:\n"
        "\tdocker compose up -d\n"
    )
    assert makefile_test_ignored(fake_makefile) == {"tests/fake_one.py"}


def test_find_makefile_ci_drift_catches_a_file_ci_ignores_that_makefile_does_not() -> None:
    missing_from_makefile, missing_from_ci = find_makefile_ci_drift(
        {"tests/fake.py"}, set()
    )
    assert missing_from_makefile == ["tests/fake.py"]
    assert missing_from_ci == []


def test_find_makefile_ci_drift_catches_the_reverse() -> None:
    missing_from_makefile, missing_from_ci = find_makefile_ci_drift(
        set(), {"tests/fake.py"}
    )
    assert missing_from_makefile == []
    assert missing_from_ci == ["tests/fake.py"]


def test_a_comment_naming_a_test_file_between_two_ci_yml_jobs_is_not_attributed_to_the_first() -> (
    None
):
    """The real bug found building `find_makefile_ci_drift`, not a hypothetical one: adding
    `sustained-load-exit-test` between `bundle-install-exit-test` and `harness-image-exit-test` in
    `ci.yml`, with a comment naming `tests/harness/test_sustained_load.py` in the gap between them,
    made this gate report that file "covered" by `bundle-install-exit-test` — which never runs it.
    `_job_blocks` attributes the comment to the *preceding* job's own block (there is nowhere else
    to put it under a header-to-header split); `job_tokens` must not scan it for tokens regardless.
    """
    job_body = (
        "\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: >-\n"
        "          uv run pytest -p no:randomly\n"
        "          tests/harness/test_bundle_exit_test.py\n"
        "\n"
        "  # A comment naming tests/harness/test_sustained_load.py, which this job never runs.\n"
    )
    _, positional = job_tokens(job_body)
    assert positional == {"tests/harness/test_bundle_exit_test.py"}


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
    fake = _FakeTestFile("tests/fake_live_service_test.py", "from valkey.asyncio import Valkey\n")
    misclassified = find_misclassified(
        [fake],  # type: ignore[list-item]
        test_job_ignored={"tests/fake_live_service_test.py"},
        live_job_tokens={"conformance": set()},
    )
    assert misclassified == [
        "tests/fake_live_service_test.py: ignored by `test` but not run by any live-service job"
    ]


def test_a_live_service_file_missing_from_the_ignore_list_is_caught_even_if_covered() -> None:
    fake = _FakeTestFile("tests/fake_live_service_test.py", "from valkey.asyncio import Valkey\n")
    misclassified = find_misclassified(
        [fake],  # type: ignore[list-item]
        test_job_ignored=set(),
        live_job_tokens={"conformance": {"tests/fake_live_service_test.py"}},
    )
    assert misclassified == [
        "tests/fake_live_service_test.py: needs a live service but is not ignored by the `test` job"
    ]


def test_classification_recognises_a_test_that_reaches_its_service_by_shelling_out() -> None:
    """The class this gate was blind to until 24 September 2026.

    `tests/harness/test_restore_exit_test.py` destroys a running deployment's volumes and restores
    it. It is as live-service as anything in this repository — and it imports none of the markers
    above, because it reaches every service through `docker compose`. The gate reported clean.

    That is `CLAUDE.md` rule 12's shape: the invariant "a live-service test is wired into CI
    deliberately" was exercised by a check whose every marker was a Python import, so it could not
    have found this violation if one existed. The planted source below is the real shape — this
    repository's own `OSPREY_TEST_*` opt-in convention, read from the environment and used to skip.
    """
    source = (
        "import os\n"
        "import pytest\n"
        'COMPOSE = os.environ.get("OSPREY_TEST_COMPOSE_FILE")\n'
        "requires = pytest.mark.skipif(not COMPOSE, reason='needs a real deployment')\n"
    )
    assert is_live_service_file(source) is True


def test_a_test_that_merely_renders_a_compose_file_is_not_misclassified() -> None:
    """The first attempt at the marker above matched the literal `"docker compose"` and flagged
    `test_render.py` and `test_image_references.py`, neither of which needs a running service: one
    renders a compose file, the other asks a registry about a tag.

    A marker that fires on prose is a gate that trains people to ignore it, so this is the case
    that keeps the narrowing honest.
    """
    source = (
        '"""Renders a docker compose file and asserts its services. Needs no running service."""\n'
        "import yaml\n"
        "from harness.render import render_compose\n"
    )
    assert is_live_service_file(source) is False
