"""A recipe's source file is read only from inside the ingest folder (the security review, 18
October 2026; `09_INGEST_STUDIO.md` §2).

The file picker (`ingest_sources.py`) offers only files inside `OSPREY_INGEST_ROOT`, but a draft's
`source_location` is a free string the client sends, and Profile, Map, Verify and a run all read it
through `studio_profile._read_rows`. Before this, a pipeline author could name `/etc/passwd`, or a
mounted secret, and read it back as sample rows; and a missing path answered differently from an
existing one, saying which files exist. Each test below names the hole it closes. The planted
violations take the shapes a client actually sends: an absolute path, a `..` walk out of the root,
and a symlink inside the root pointing out of it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from services.api.studio_profile import SourceUnreadableError, _read_rows

from schemas.ingest import StudioRecipeDraft, StudioRecipeStatus

_HANDLING = {
    "classification": "OFFICIAL",
    "handling_code": "P",
    "originator": "Test Unit",
    "owning_unit": "Test Unit",
}


def _draft(location: str) -> StudioRecipeDraft:
    return StudioRecipeDraft(
        recipe_id="r-confine",
        version=1,
        status=StudioRecipeStatus.DRAFT,
        label="confinement",
        connector_profile="generic-csv",
        source_location=location,
        handling=_HANDLING,
        legal_basis="test",
        owning_unit="Test Unit",
        created_by="tester",
        created_at=datetime.now(UTC),
        ready_for_profile=True,
    )


@pytest.fixture
def ingest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "ingest"
    root.mkdir()
    (root / "calls.csv").write_text("a,b\n1,2\n")
    outside = tmp_path / "secret.csv"
    outside.write_text("password,value\nroot,hunter2\n")
    monkeypatch.setenv("OSPREY_INGEST_ROOT", str(root))
    return root


def test_a_file_in_the_ingest_folder_is_read(ingest: Path) -> None:
    assert _read_rows(_draft(str(ingest / "calls.csv"))) == [{"a": "1", "b": "2"}]


def test_an_absolute_path_outside_the_ingest_folder_is_refused(ingest: Path) -> None:
    with pytest.raises(SourceUnreadableError, match="not in the ingest folder"):
        _read_rows(_draft(str(ingest.parent / "secret.csv")))


def test_a_walk_out_of_the_ingest_folder_is_refused(ingest: Path) -> None:
    with pytest.raises(SourceUnreadableError, match="not in the ingest folder"):
        _read_rows(_draft(str(ingest / ".." / "secret.csv")))


def test_a_link_inside_the_ingest_folder_to_a_file_outside_it_is_refused(ingest: Path) -> None:
    (ingest / "innocent.csv").symlink_to(ingest.parent / "secret.csv")
    with pytest.raises(SourceUnreadableError, match="not in the ingest folder"):
        _read_rows(_draft(str(ingest / "innocent.csv")))


def test_outside_the_folder_a_missing_file_and_a_present_one_answer_alike(ingest: Path) -> None:
    """The existence oracle: the refusal must not differ by whether the path exists."""
    answers = []
    for name in ("secret.csv", "no-such-file.csv"):
        with pytest.raises(SourceUnreadableError) as refused:
            _read_rows(_draft(str(ingest.parent / name)))
        answers.append(str(refused.value).replace(name, "<name>"))
    assert answers[0] == answers[1]
    assert "<name>" not in answers[0], "the refusal should not echo the path at all"
