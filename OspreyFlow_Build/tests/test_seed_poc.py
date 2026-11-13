"""The POC seed path's one entry (ADR-148 Amendment 14): `python -m scripts.seed_poc`, run by the
`ospreyflow-seed` Job in the api image with the Conduit scaled to none. It makes (or reuses) one
named case, its first Author the deployment's first administrator, its packs the union of the
seeds' own (ADR-126 decision 2, as `harness.apply` sets them), then runs spec 08's three seeds into
it in `harness.apply`'s order, each printing every line it reports. A seed that fails stops the run
there, named, and the Job fails with it: never "seeded" over a missing dataset (rule 2)."""

from __future__ import annotations

from typing import Any

import pytest
from scripts import seed_poc

from demo_fixtures.datasets import domains_for

ADMIN = "50000000-0000-4000-8000-000000000001"


class _Case:
    id = "case-poc-1"


@pytest.fixture
def recorded(monkeypatch) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    seen: dict[str, Any] = {"cases": [], "seeds": []}

    async def case_from_arguments(**kwargs: Any) -> _Case:
        seen["cases"].append(kwargs)
        return _Case()

    def seed(name: str, code: int = 0):  # type: ignore[no-untyped-def]
        def main(argv: list[str]) -> int:
            seen["seeds"].append((name, argv))
            return seen.get("fail", {}).get(name, code)

        return main

    monkeypatch.setattr(seed_poc, "case_from_arguments", case_from_arguments)
    monkeypatch.setattr(seed_poc, "_seed_main", lambda module: seed(module))
    return seen


def test_one_case_its_author_the_first_administrator_then_the_three_seeds(recorded) -> None:  # type: ignore[no-untyped-def]
    assert seed_poc.main(["--author", ADMIN, "--org-unit", "unit-1"]) == 0
    [case] = recorded["cases"]
    assert case["name"] == seed_poc.CASE_NAME
    assert case["grant_texts"] == [f"{ADMIN}=author"]
    assert case["domains"] == domains_for(["hmp", "fixture-corp", "scenarios"])
    assert case["seeder"].org_unit == "unit-1" and case["seeder"].id == seed_poc.SEEDER_ID
    assert recorded["seeds"] == [
        ("scripts.seed_hmp_fixture", ["--investigation-scope", "case-poc-1"]),
        ("scripts.seed_fixture_corp", ["--investigation-scope", "case-poc-1"]),
        ("scripts.seed_scenarios", ["--investigation-scope", "case-poc-1"]),
    ]


def test_a_failed_seed_stops_the_run_by_name_and_fails_the_job(recorded, capsys) -> None:  # type: ignore[no-untyped-def]
    recorded["fail"] = {"scripts.seed_fixture_corp": 1}
    assert seed_poc.main(["--author", ADMIN]) == 1
    assert [name for name, _ in recorded["seeds"]] == [
        "scripts.seed_hmp_fixture",
        "scripts.seed_fixture_corp",
    ]
    assert "fixture-corp" in capsys.readouterr().err


def test_a_seed_that_raises_fails_the_job_too(recorded, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    def boom(argv: list[str]) -> int:
        raise ConnectionError("ArcadeDB refused")

    monkeypatch.setattr(seed_poc, "_seed_main", lambda module: boom)
    assert seed_poc.main(["--author", ADMIN]) == 1
    assert "hmp" in capsys.readouterr().err


def test_no_first_administrator_is_refused_before_anything_is_written(
    recorded, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("OSPREY_FIRST_ADMINISTRATORS", raising=False)
    with pytest.raises(SystemExit):
        seed_poc.main([])
    with pytest.raises(SystemExit):
        seed_poc.main(["--author", "  "])
    assert recorded["cases"] == [] and recorded["seeds"] == []


def test_the_real_seed_modules_are_the_ones_apply_runs() -> None:
    from scripts import seed_fixture_corp, seed_hmp_fixture, seed_scenarios

    assert [seed_poc._seed_main(m) for m in seed_poc.SEEDS.values()] == [
        seed_hmp_fixture.main,
        seed_fixture_corp.main,
        seed_scenarios.main,
    ]
    assert list(seed_poc.SEEDS) == ["hmp", "fixture-corp", "scenarios"]


def test_the_author_is_the_deployments_first_administrator_by_default(
    recorded, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """In the Job, the case's first Author is read from the settings the Conduit is given
    (`OSPREY_FIRST_ADMINISTRATORS`, the ConfigMap's), the first of them: no argument to render."""
    monkeypatch.setenv(
        "OSPREY_FIRST_ADMINISTRATORS", f"{ADMIN},50000000-0000-4000-8000-000000000002"
    )
    assert seed_poc.main([]) == 0
    assert recorded["cases"][0]["grant_texts"] == [f"{ADMIN}=author"]
