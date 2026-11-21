"""C068 (and, by the same cause, the live ingest tests of C043 that name `SourceUnreadableError`):
the live seed tests read the seed's files in the process, and the in-process read refused them.

**The cause, found by reading** (the failing run itself is the evidence seat's, RS1). The seed's
files live in `<scratch>/ingest/uploaded/pid/` and `tests/ingest/test_pid_seed_live.py` gives the
seed *subprocess* that folder as `OSPREY_INGEST_ROOT` (`_environment`). But the tests also run the
recipes in the test's own process (`run_recipe_as`, `publish_reports_fallback`), and there the root
is the one `tests/conftest.py`'s autouse `_ingest_root_for_tests` sets for every test: that test's
own `tmp_path`. Since L1.4 (ADR-140 Amendment 12) `studio_profile._confined` reads a recipe's file
only from inside the root, so every in-process read of the seed's files raised
`SourceUnreadableError("That file is not in the ingest folder. ...")`, from `studio_profile` as the
row says. It is a fault in the test's setting, not in the confinement, which is right to refuse a
file outside its root.

What is proved here, without the stack: with the root as conftest sets it, the seed's file is
refused, in those words (the shape the code really raises, from the real location the seed reads);
and the live module sets the root for in-process reads to the seed's folder. The plant is the
module without that setting: the second case then fails with the real refusal. A read that is
refused for a file outside the dataset's folders stays refused (`test_source_confinement.py`).

Owed to RS1: the slow seed's two cases run on a leased stack, to see them pass.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from _pytest.fixtures import FixtureFunctionDefinition
from scripts import seed_pid
from services.api.studio_profile import SourceUnreadableError, _confined

from demo_fixtures import pid_files
from tests.ingest import test_pid_seed_live as live

#: The dataset the seed's recipes name (`seed_pid.FOLDER`), whose folder the file is in.
DATASET = seed_pid.FOLDER


def _seed_file() -> str:
    return seed_pid.source_of(live.INGEST, pid_files.REPORTS)


def test_the_seeds_file_is_outside_the_root_conftest_gives_every_test() -> None:
    """The refusal that failed the slow seed, as the code raises it for the real location."""
    with pytest.raises(SourceUnreadableError, match="not in the ingest folder"):
        _confined(_seed_file(), DATASET)


def _autouse_fixtures(module: object) -> list[FixtureFunctionDefinition]:
    return [
        value
        for value in vars(module).values()
        if isinstance(value, FixtureFunctionDefinition) and value._fixture_function_marker.autouse
    ]


def test_the_live_module_points_in_process_reads_at_the_seeds_folder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for fixture in _autouse_fixtures(live):
        fixture._get_wrapped_function()(monkeypatch)
    assert _confined(_seed_file(), DATASET) == _seed_file()


def test_the_setting_does_not_open_the_root_to_a_file_outside_the_seeds_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The setting moves the root to the seed's folder; it does not widen it. A file elsewhere, and
    the seed's file for another dataset, are refused as before."""
    for fixture in _autouse_fixtures(live):
        fixture._get_wrapped_function()(monkeypatch)
    with pytest.raises(SourceUnreadableError, match="not in the ingest folder"):
        _confined(str(tmp_path / "elsewhere.csv"), DATASET)
    with pytest.raises(SourceUnreadableError, match="not one of this dataset's files"):
        _confined(_seed_file(), "another-dataset")
