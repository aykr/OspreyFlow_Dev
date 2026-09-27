"""The documented way to put a source file in the ingest folder actually works — round 13c.

**What went wrong, and why it survived two rounds of review.** `DEMO_GUIDE.md` §3.7a told an
operator to run `sudo cp tests/scenarios/fixtures/files/*.csv /var/lib/osprey/ingest/`. That
directory has never existed — the CDR fixture is generated, not stored — so the documented step
copies nothing and the Studio's Connect stage lists an empty folder.

Nothing caught it because no test reads `DEMO_GUIDE.md`'s shell blocks, and the round that wrote
the step had a file sitting in its own scratchpad ingest folder, placed by hand. The procedure was
never walked from a clean state by the person who wrote it. That is the third time this exact
shape has been found in §3.7a's neighbourhood (round 13's missing `PYTHONPATH`, round 13bd's
`mint_dev_token` roles, this), which is why the fix is an executable module with this test rather
than a corrected sentence.

Rule 12, named: if `scripts/seed_ingest_folder.py` stops producing the file the over-the-wire
B1-B3 cases look up by name, `test_the_seeded_file_is_the_one_the_acceptance_tests_look_for` is
what fails.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
import yaml
from scripts.seed_ingest_folder import (
    CDR_FIXTURE_NAME,
    DEFAULT_INGEST_ROOT,
    ingest_root_from_config,
    write_cdr_fixture,
)


def test_seeding_an_empty_folder_produces_a_readable_csv(tmp_path: Path) -> None:
    written = write_cdr_fixture(tmp_path)

    assert written.exists() and written.stat().st_size > 0
    lines = written.read_text(encoding="utf-8").splitlines()
    assert len(lines) > 1, "header only — the generator produced no rows"

    header = lines[0].split(",")
    for required in ("a_party", "b_party", "start_time"):
        assert required in header, (
            f"{required!r} is missing from the seeded file, so the recipe that maps it cannot "
            f"bind that field. Header: {header}"
        )


def test_the_seeded_file_is_the_one_the_acceptance_tests_look_for(tmp_path: Path) -> None:
    """The coupling is the point. `test_b1_…`/`test_b2_…`/`test_b3_…` select the file by name from
    the deployment's ingest listing, so a rename here makes those three fail with "not in the
    deployment's ingest root" and no indication that this module is the cause."""
    written = write_cdr_fixture(tmp_path)
    assert written.name == CDR_FIXTURE_NAME == "carrier-a-cdr.csv"


def test_the_structural_cases_b1_to_b3_depend_on_are_all_present(tmp_path: Path) -> None:
    """**The half that makes this more than a file-exists check.** B1 needs four renderings of one
    number, B2 needs duplicate rows, B3 needs a local-time row, a `dmy` row and one unparseable
    timestamp. A seeded file missing any of them would still be a valid CSV and would still let
    the Studio walk end to end — and the acceptance rows it is there to prove would quietly stop
    proving anything."""
    rows = list(
        csv.DictReader(write_cdr_fixture(tmp_path).read_text(encoding="utf-8").splitlines())
    )
    assert rows, "the seeded file has no data rows"

    renderings = {row["a_party"] for row in rows}
    assert len(renderings) >= 4, f"B1 needs four renderings of one number, found {renderings}"

    timestamps = [row["start_time"] for row in rows]
    assert any(t.endswith("Z") for t in timestamps), "no UTC-offset row for B3"
    assert any("/" in t for t in timestamps), "no slash-formatted (dmy) row — B3's date-order case"
    assert any(
        not t.endswith("Z") and "+" not in t and "/" not in t for t in timestamps
    ), "no naive local-time row — B3's offset-conversion case"
    assert len(timestamps) != len(set(timestamps)) or len(rows) > len(renderings), (
        "no duplicated call — B2 has nothing to collapse"
    )


def test_the_config_reader_finds_a_rendered_deployments_own_root(tmp_path: Path) -> None:
    config = tmp_path / "osprey.yaml"
    config.write_text(
        yaml.safe_dump({"components": {"storage": {"ingest": "/somewhere/else/ingest"}}}),
        encoding="utf-8",
    )
    assert ingest_root_from_config(config) == Path("/somewhere/else/ingest")


def test_a_config_with_no_storage_block_falls_back_to_the_documented_default(
    tmp_path: Path,
) -> None:
    """A rendered `osprey.yaml` need not carry a `storage` block at all — the fresh clone's own
    does not. Falling back is what makes `--osprey-config` usable against it rather than raising
    `KeyError` at an operator."""
    config = tmp_path / "osprey.yaml"
    config.write_text(yaml.safe_dump({"profile": "local-lite"}), encoding="utf-8")
    assert ingest_root_from_config(config) == Path(DEFAULT_INGEST_ROOT)


def test_seeding_is_idempotent(tmp_path: Path) -> None:
    """An operator re-running it after a failed demo must not end up with two files, or a file
    with the header repeated in the middle of it."""
    first = write_cdr_fixture(tmp_path).read_text(encoding="utf-8")
    second = write_cdr_fixture(tmp_path).read_text(encoding="utf-8")

    assert first == second
    assert sorted(p.name for p in tmp_path.iterdir()) == [CDR_FIXTURE_NAME]


def test_the_documented_copy_source_does_not_exist(tmp_path: Path) -> None:
    """**The regression test for the documentation defect itself.**

    `DEMO_GUIDE.md` §3.7a named `tests/scenarios/fixtures/files/*.csv`. If that directory is ever
    created, this test fails and whoever created it has to decide which of the two mechanisms is
    the real one — rather than the guide quietly becoming correct again by accident while
    `scripts/seed_ingest_folder.py` goes stale beside it.
    """
    repo_root = Path(__file__).resolve().parents[1]
    assert not (repo_root / "tests" / "scenarios" / "fixtures" / "files").exists(), (
        "tests/scenarios/fixtures/files/ now exists. DEMO_GUIDE.md §3.7a used to tell operators "
        "to copy from here and it never existed; the supported path is now "
        "`python -m scripts.seed_ingest_folder`. Pick one."
    )


@pytest.mark.parametrize("subdirectory", ["nested", "deeply/nested/path"])
def test_it_creates_the_folder_when_it_is_not_there(tmp_path: Path, subdirectory: str) -> None:
    """The documented default `/var/lib/osprey/ingest` usually does not exist yet, which is the
    ordinary case rather than an edge one."""
    target = tmp_path / subdirectory
    assert not target.exists()
    assert write_cdr_fixture(target).exists()
