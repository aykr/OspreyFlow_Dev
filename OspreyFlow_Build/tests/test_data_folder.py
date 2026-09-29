"""OspreyFlow_Data is where datasets live, and nothing in the product tree holds one (ADR-054).

Before this, a Conduit run from a checkout wrote its analytics store to a `data/` folder inside the
tree, and the seeds and the pre-flight check each carried their own copy of that path. Each test
below names what it would catch.
"""

from __future__ import annotations

import subprocess

import pytest
from scripts import seed_hmp_fixture, seed_scenarios
from services.api.config import DEFAULT_ANALYTICS_DB_PATH, ApiConfig

from tools import packaging_gate
from tools.layout import CORE
from tools.layout import REPO as REPO_ROOT

DATA_FOLDER = "OspreyFlow_Data"


def test_the_analytics_store_defaults_to_the_data_folder_not_the_product_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches a Conduit run from a checkout that writes its store back into the tree."""
    monkeypatch.delenv("ANALYTICS_DB_PATH", raising=False)
    monkeypatch.setenv("OIDC_JWKS_URL", "http://localhost:8081/jwks")
    assert DEFAULT_ANALYTICS_DB_PATH == f"../{DATA_FOLDER}/_local-runtime/analytics.duckdb"
    assert ApiConfig.from_env().analytics_db_path == DEFAULT_ANALYTICS_DB_PATH


@pytest.mark.parametrize("seed", [seed_hmp_fixture, seed_scenarios])
def test_the_seeds_write_to_the_same_store_the_conduit_reads(
    seed: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catches the seeds and the Conduit disagreeing on where the store is: the seed then succeeds
    into a file nobody reads, and the Glass shows nothing."""
    monkeypatch.delenv("ANALYTICS_DB_PATH", raising=False)
    argv = ["--investigation-scope", "x"]
    args = seed._parse_args(argv)  # type: ignore[attr-defined]
    assert args.analytics_db_path == DEFAULT_ANALYTICS_DB_PATH


def test_the_preflight_check_looks_where_the_conduit_writes() -> None:
    from harness.preflight.context import PreflightContext

    field = PreflightContext.__dataclass_fields__["analytics_db_path"]
    assert field.default_factory().resolve() == (CORE / DEFAULT_ANALYTICS_DB_PATH).resolve()  # type: ignore[misc]


def test_the_packaging_gate_refuses_anything_under_the_data_folder() -> None:
    """Catches a build that carries a dataset because it now lives under a name the gate did not
    know. ADR-035 §C2 refuses `demo-data/`; the same refusal must cover the new home."""
    refused = packaging_gate.find_internal_demo_data(
        [f"{DATA_FOLDER}/enron/maildir.tar.gz", f"{DATA_FOLDER}/_local-runtime/analytics.duckdb"]
    )
    assert len(refused) == 2
    assert packaging_gate.find_internal_demo_data(["demo-data/enron/x.csv"]) == [
        "demo-data/enron/x.csv"
    ]


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    ).stdout


def test_git_ignores_everything_in_the_data_folder_except_its_readme() -> None:
    """Catches a dataset committed by a bare `git add`. The folder exists in a clone (it has a
    README) but nothing else in it can be added."""
    ignored = _git(
        "check-ignore",
        f"{DATA_FOLDER}/enron/maildir.tar.gz",
        f"{DATA_FOLDER}/_local-runtime/analytics.duckdb",
    ).splitlines()
    assert len(ignored) == 2
    assert _git("check-ignore", f"{DATA_FOLDER}/README.md") == ""


def test_the_only_tracked_file_in_the_data_folder_is_its_readme() -> None:
    tracked = _git("ls-files", DATA_FOLDER).split()
    assert tracked == [f"{DATA_FOLDER}/README.md"]
