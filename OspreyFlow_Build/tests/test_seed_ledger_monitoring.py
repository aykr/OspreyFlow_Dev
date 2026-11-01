"""Operation Ledger's monitoring week, as the seed places it and the presenter releases and resets it
(`spec/06_DECISIONS.md` ADR-108 Amendment 5). File steps only, so pure: a scratch folder stands for the
ingest root, and no store is opened.

What a mistake would do, and the case that catches it:
- the week shown in the Studio's listing before the presenter releases it, or the list's version 2 in
  place before its release (`test_the_seed_places_the_week_out_of_sight_and_the_lists_first_version`);
- a release that copies the wrong file, or nothing (`test_the_week_is_released_into_the_listed_folder`,
  `test_the_list_update_puts_version_2_where_the_subscription_reads`);
- a release before the seed copying nothing and saying it did (`test_a_release_before_the_seed_is_refused`);
- a reset that leaves the week listed or version 2 in place, or says nothing of what stays
  (`test_the_reset_puts_both_back_and_says_what_it_cannot_undo`);
- the subscription reading anything but the seed's own file, through anything but the FCDO connector
  (`test_the_subscription_reads_the_seeds_file_through_the_uk_connector`).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from scripts import seed_ledger_fixture as seed

from demo_fixtures import ledger_monitoring

V1 = seed.LISTS_FOLDER / ledger_monitoring.UK_LIST_V1
V2 = seed.LISTS_FOLDER / ledger_monitoring.UK_LIST_V2


def test_the_seed_places_the_week_out_of_sight_and_the_lists_first_version(tmp_path: Path) -> None:
    said = seed.write_monitoring_files(tmp_path)
    listed = tmp_path / "uploaded" / "ledger"
    assert (listed / "incoming" / ledger_monitoring.WEEK_2).is_file()
    assert not (listed / ledger_monitoring.WEEK_2).exists(), "not offered until it is released"
    assert (listed / "lists" / "uk_sanctions_list.xml").read_bytes() == V1.read_bytes()
    assert (listed / "incoming" / seed.LIST_V2_WAITING).read_bytes() == V2.read_bytes()
    assert any(ledger_monitoring.WEEK_2 in line and "13 rows" in line for line in said)
    # A second seed rewrites each byte for byte, and puts version 1 back over a released version 2.
    seed.release_list_update(tmp_path)
    seed.write_monitoring_files(tmp_path)
    assert (listed / "lists" / "uk_sanctions_list.xml").read_bytes() == V1.read_bytes()


def test_the_week_is_released_into_the_listed_folder(tmp_path: Path) -> None:
    seed.write_monitoring_files(tmp_path)
    said = seed.release_week_2(tmp_path)
    listed = tmp_path / "uploaded" / "ledger"
    assert (listed / ledger_monitoring.WEEK_2).read_bytes() == (
        listed / "incoming" / ledger_monitoring.WEEK_2
    ).read_bytes()
    assert said.startswith("released ")
    assert "nothing changed" in seed.release_week_2(tmp_path)
    assert (listed / "lists" / "uk_sanctions_list.xml").read_bytes() == V1.read_bytes(), (
        "releasing the week leaves the list as it was"
    )


def test_the_list_update_puts_version_2_where_the_subscription_reads(tmp_path: Path) -> None:
    seed.write_monitoring_files(tmp_path)
    said = seed.release_list_update(tmp_path)
    assert seed.list_file(tmp_path).read_bytes() == V2.read_bytes()
    assert "Refresh now" in said
    assert not (tmp_path / "uploaded" / "ledger" / ledger_monitoring.WEEK_2).exists()


@pytest.mark.parametrize("release", [seed.release_week_2, seed.release_list_update])
def test_a_release_before_the_seed_is_refused(tmp_path: Path, release: Any) -> None:
    with pytest.raises(seed.SeedRefusal, match="seed the dataset first"):
        release(tmp_path)
    assert not (tmp_path / "uploaded").exists()


def test_the_reset_puts_both_back_and_says_what_it_cannot_undo(tmp_path: Path) -> None:
    seed.write_monitoring_files(tmp_path)
    seed.release_week_2(tmp_path)
    seed.release_list_update(tmp_path)
    said = seed.reset_week_2(tmp_path)
    listed = tmp_path / "uploaded" / "ledger"
    assert not (listed / ledger_monitoring.WEEK_2).exists()
    assert (listed / "incoming" / ledger_monitoring.WEEK_2).is_file(), "ready for the next rehearsal"
    assert seed.list_file(tmp_path).read_bytes() == V1.read_bytes()
    for item in ("scripts.revert_load", "retire them", "their closes", "version 1 again"):
        assert item in said, item


def test_the_command_runs_a_step_without_a_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    monkeypatch.setenv("OSPREY_INGEST_ROOT", str(tmp_path))
    assert seed.main(["--release-week-2", "--org-unit", "verify", "--run-as", "sub-1"]) == 1
    assert "seed the dataset first" in capsys.readouterr().err
    seed.write_monitoring_files(tmp_path)
    assert seed.main(["--release-week-2", "--org-unit", "verify"]) == 0
    assert "released" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        seed.main(["--release-week-2", "--reset-week-2"])


def test_the_subscription_reads_the_seeds_file_through_the_uk_connector() -> None:
    made: list[Any] = []

    class Store:
        async def subscription(self, name: str) -> Any:
            return made[0] if made else None

        async def subscribe(self, spec: Any, by: str, *, synthetic: bool) -> Any:
            made.append(spec)
            return spec

    said = asyncio.run(seed.subscribe_uk_list(Store(), "ledger-seed-worker"))  # type: ignore[arg-type]
    (spec,) = made
    assert (spec.list_name, spec.source, spec.location, spec.dataset) == (
        "UK Sanctions List (synthetic)", "uk_sanctions_list",
        "uploaded/ledger/lists/uk_sanctions_list.xml", None,
    )  # fmt: skip
    assert "not yet refreshed" in said
    assert "subscribed already" in asyncio.run(seed.subscribe_uk_list(Store(), "x"))  # type: ignore[arg-type]
    assert len(made) == 1
