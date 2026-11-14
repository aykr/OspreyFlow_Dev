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

    async def unit(args: Any) -> str:
        seen["unit_of"] = args.author
        return "unit-7"

    monkeypatch.setattr(seed_poc, "case_from_arguments", case_from_arguments)
    monkeypatch.setattr(seed_poc, "_seed_main", lambda module: seed(module))
    monkeypatch.setattr(seed_poc, "_unit", unit)
    monkeypatch.delenv("OSPREY_HIGHEST_MARKING", raising=False)
    monkeypatch.delenv("OSPREY_ORG_UNIT", raising=False)
    return seen


def test_one_case_its_author_the_first_administrator_then_the_three_seeds(
    recorded,
) -> None:  # type: ignore[no-untyped-def]
    assert seed_poc.main(["--author", ADMIN]) == 0
    [case] = recorded["cases"]
    assert case["name"] == seed_poc.CASE_NAME
    assert case["grant_texts"] == [f"{ADMIN}=author"]
    assert case["domains"] == domains_for(["hmp", "fixture-corp", "scenarios"])
    # The case in the first administrator's own unit, as Entra gave it at their sign-in.
    assert recorded["unit_of"] == ADMIN
    assert (
        case["seeder"].org_unit == "unit-7" and case["seeder"].id == seed_poc.SEEDER_ID
    )
    assert recorded["seeds"] == [
        ("scripts.seed_hmp_fixture", ["--investigation-scope", "case-poc-1"]),
        ("scripts.seed_fixture_corp", ["--investigation-scope", "case-poc-1"]),
        ("scripts.seed_scenarios", ["--investigation-scope", "case-poc-1"]),
    ]


def test_a_failed_seed_stops_the_run_by_name_and_fails_the_job(
    recorded, capsys
) -> None:  # type: ignore[no-untyped-def]
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


def test_the_seeds_are_the_ones_harness_apply_runs_in_its_order() -> None:
    """A local deployment's seed (`harness.apply.seed`) and the POC's run the same three modules in
    the same order: its map is read from its own source, so the two cannot drift."""
    import ast
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2] / "OspreyFlow_Core/harness/apply.py"
    ).read_text()
    maps = [
        {k.value: v.value for k, v in zip(node.keys, node.values, strict=True)}  # type: ignore[union-attr]
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Dict)
        and node.keys
        and all(isinstance(k, ast.Constant) for k in node.keys)
        and {getattr(k, "value", None) for k in node.keys}
        == {"hmp", "fixture-corp", "scenarios"}
    ]
    assert maps == [seed_poc.SEEDS]
    assert list(maps[0]) == list(seed_poc.SEEDS)


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


def test_the_seeds_are_given_the_cases_unit(recorded, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Each seed registers its dataset as held by its principal's unit
    (`case_seed.ensure_case_reads`), read from OSPREY_ORG_UNIT: the case's own, or the case
    could not read what it seeds."""
    import os

    units: list[str | None] = []
    monkeypatch.setattr(
        seed_poc,
        "_seed_main",
        lambda m: lambda argv: units.append(os.environ.get("OSPREY_ORG_UNIT")) or 0,
    )
    assert seed_poc.main(["--author", ADMIN]) == 0
    assert units == ["unit-7", "unit-7", "unit-7"]


@pytest.mark.parametrize("ceiling", ["OFFICIAL-SENSITIVE", "OFFICIAL"])
def test_a_ceiling_below_the_seeds_is_refused_before_anything_is_written(
    recorded, monkeypatch, capsys, ceiling
) -> None:  # type: ignore[no-untyped-def]
    """ADR-148 decision 10: HMP's and Fixture Corp's data reach SECRET (`seed_internal.DATASETS`),
    above the cloud-platform profile's default ceiling. Refused before the case or any seed, the
    ceiling and what the seeds hold named (a pack written in several transactions is never
    partly written)."""
    monkeypatch.setenv("OSPREY_HIGHEST_MARKING", ceiling)
    assert seed_poc.main(["--author", ADMIN]) == 1
    said = capsys.readouterr().err
    assert (
        ceiling in said
        and "SECRET" in said
        and "hmp" in said
        and "fixture-corp" in said
    )
    assert "step 9" in said and "nothing was seeded" in said
    assert (
        recorded["cases"] == []
        and recorded["seeds"] == []
        and "unit_of" not in recorded
    )


def test_the_ceiling_s_refusal_says_what_the_client_would_declare(
    recorded, monkeypatch, capsys
) -> None:  # type: ignore[no-untyped-def]
    """The owner's ruling (MORNING item 2, (a)): a POC shown with spec 08's data declares SECRET;
    the refusal names both values and the setting that would admit the seeds."""
    monkeypatch.setenv("OSPREY_HIGHEST_MARKING", "OFFICIAL-SENSITIVE")
    assert seed_poc.main(["--author", ADMIN]) == 1
    said = capsys.readouterr().err
    assert "OFFICIAL-SENSITIVE" in said and "deployment.highest_marking: SECRET" in said
    assert recorded["cases"] == [] and recorded["seeds"] == []


def test_the_seeds_markings_are_the_packs_declared_ones() -> None:
    from scripts.seed_internal import DATASETS

    assert seed_poc.SEED_MARKINGS["hmp"] == DATASETS["hmp"].highest_marking == "SECRET"
    assert (
        seed_poc.SEED_MARKINGS["fixture-corp"]
        == DATASETS["fixture-corp"].highest_marking
    )
    assert list(seed_poc.SEED_MARKINGS) == list(seed_poc.SEEDS)


class _People:
    """The people store's `one` as the real one answers it: a person not recorded is refused
    (`IdentityAdminRefused("no such person")`); one added ahead of sign-in has no unit yet."""

    def __init__(self, rows: dict[str, Any]) -> None:
        self.rows = rows

    async def one(self, oid: str) -> Any:
        from services.api.identity_admin import IdentityAdminRefused

        if oid not in self.rows:
            raise IdentityAdminRefused("no such person")
        return self.rows[oid]


async def test_the_unit_is_the_first_administrators_own_from_their_sign_in() -> None:
    from types import SimpleNamespace

    people = _People({ADMIN: SimpleNamespace(signed_in=True, org_unit="unit-7")})
    assert await seed_poc.author_unit(people, ADMIN) == "unit-7"


@pytest.mark.parametrize("state", ["never recorded", "added ahead of sign-in"])
async def test_a_first_administrator_not_yet_signed_in_is_refused(state: str) -> None:
    from types import SimpleNamespace

    rows = (
        {}
        if state == "never recorded"
        else {ADMIN: SimpleNamespace(signed_in=False, org_unit=None)}
    )
    with pytest.raises(seed_poc.SeedRefused, match="has not signed in"):
        await seed_poc.author_unit(_People(rows), ADMIN)


def test_a_refusal_from_the_unit_is_said_and_fails_the_job(
    recorded, monkeypatch, capsys
) -> None:  # type: ignore[no-untyped-def]
    async def unit(args: Any) -> str:
        raise seed_poc.SeedRefused("the first administrator x has not signed in yet")

    monkeypatch.setattr(seed_poc, "_unit", unit)
    assert seed_poc.main(["--author", ADMIN]) == 1
    assert "has not signed in" in capsys.readouterr().err
    assert recorded["cases"] == [] and recorded["seeds"] == []
