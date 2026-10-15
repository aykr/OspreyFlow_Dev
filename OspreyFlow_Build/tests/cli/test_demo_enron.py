"""`ospreyflow demo add enron` (ADR-114 Amendment 23): the Enron corpus — real people's email — as an
optional download each user makes from CMU, checked, accepted in words, unpacked on their machine,
and only then seeded.

What a mistake would do, and the case that catches it:
- the corpus loaded without the person accepting what it is —
  `test_declining_adds_nothing_and_unpacks_nothing` and
  `test_the_seed_starts_only_after_acceptance_and_its_record`;
- a file nobody checked — `test_the_file_is_checked_before_anything_is_shown_or_unpacked`;
- the person not told what they are accepting — `test_the_notice_says_real_people_privacy_and_no_licence`;
- a scripted run passing without saying it accepts — `test_accept_real_data_accepts_and_says_so`;
- no way to find the corpus — `test_without_a_file_or_a_corpus_it_names_the_source`;
- the owner's corpus, already unpacked, loaded without asking —
  `test_a_corpus_already_unpacked_is_still_asked_about`;
- the CLI's notice drifting from the record's — `test_the_notice_is_the_records_own_statement`.
"""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

import pytest
from ospreyflow import demo
from scripts import real_data_acknowledgement

from .conftest import Rig


def _corpus_tarball(tmp_path: Path) -> Path:
    """A tiny stand-in in the corpus's own layout (`maildir/<custodian>/<folder>/<file>`), invented."""
    path = tmp_path / "enron_mail_20150507.tar.gz"
    with tarfile.open(path, "w:gz") as tar:
        body = b"From: a@example.org\nTo: b@example.org\nSubject: invented\n\nHello\n"
        info = tarfile.TarInfo("maildir/someone-a/inbox/1.")
        info.size = len(body)
        tar.addfile(info, io.BytesIO(body))
    return path


@pytest.fixture
def data_root(rig: Rig, tmp_path: Path) -> Path:
    root = tmp_path / "demo-data"
    rig.env["OSPREYFLOW_DEMO_DATA"] = str(root)
    return root


def _seed_calls(rig: Rig) -> list[list[str]]:
    return [argv for argv in rig.runner.argvs() if "scripts.seed_internal" in argv]


def test_without_a_file_or_a_corpus_it_names_the_source(
    rig: Rig, data_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert rig("demo", "add", "enron") == 1
    said = capsys.readouterr().err
    assert "https://www.cs.cmu.edu/~enron/" in said and "--file" in said
    assert rig.runner.calls == []


def test_the_file_is_checked_before_anything_is_shown_or_unpacked(
    rig: Rig, data_root: Path, tmp_path: Path
) -> None:
    rig.runner.fail["verify"] = 1
    assert rig("demo", "add", "enron", "--file", str(_corpus_tarball(tmp_path))) == 1
    (verify,) = rig.runner.argvs()
    assert verify[-3:] == ["verify", "enron", str(tmp_path / "enron_mail_20150507.tar.gz")]
    assert rig.questions == [] and not (data_root / "Enron_Mails").exists()


def test_the_notice_says_real_people_privacy_and_no_licence(
    rig: Rig, data_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rig.replies = ["no"]
    rig("demo", "add", "enron", "--file", str(_corpus_tarball(tmp_path)))
    said = capsys.readouterr().out
    for words in ("real people's email", "No licence is stated", "sensitive to the privacy",
                  "lawful basis"):  # fmt: skip
        assert words in said, words


def test_declining_adds_nothing_and_unpacks_nothing(
    rig: Rig, data_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rig.replies = ["no"]
    assert rig("demo", "add", "enron", "--file", str(_corpus_tarball(tmp_path))) == 0
    assert "Nothing was added" in capsys.readouterr().out
    assert not (data_root / "Enron_Mails").exists()
    assert _seed_calls(rig) == []


def test_the_seed_starts_only_after_acceptance_and_its_record(
    rig: Rig, data_root: Path, tmp_path: Path
) -> None:
    rig.replies = ["yes"]
    assert rig("demo", "add", "enron", "--file", str(_corpus_tarball(tmp_path))) == 0
    corpus = data_root / "Enron_Mails"
    assert (corpus / "someone-a" / "inbox" / "1.").is_file()
    assert real_data_acknowledgement.accepted(corpus, "enron")
    record = json.loads((corpus / real_data_acknowledgement.RECORD).read_text(encoding="utf-8"))
    assert record["source_file"] == "enron_mail_20150507.tar.gz"
    (seed,) = _seed_calls(rig)
    assert seed[-2:] == ["enron", "--stop-api"]


def test_accept_real_data_accepts_and_says_so(
    rig: Rig, data_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert rig("demo", "add", "enron", "--file", str(_corpus_tarball(tmp_path)), "--accept-real-data") == 0
    assert rig.questions == []
    assert "accepted with --accept-real-data" in capsys.readouterr().out
    assert len(_seed_calls(rig)) == 1


def test_a_corpus_already_unpacked_is_still_asked_about(rig: Rig, data_root: Path) -> None:
    (data_root / "Enron_Mails" / "someone-a").mkdir(parents=True)
    rig.replies = ["no"]
    assert rig("demo", "add", "enron") == 0
    assert len(rig.questions) == 1 and _seed_calls(rig) == []


def test_the_notice_is_the_records_own_statement() -> None:
    assert demo.ENRON_STATEMENT == real_data_acknowledgement.STATEMENT


# --- never by default (Amendment 23 point 4) ---------------------------------------------------


def test_an_install_never_adds_enron_and_says_how_to(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    answers = tmp_path / "answers.yaml"
    answers.write_text("mode: lite\ndemo_packs: [hmp, enron]\n", encoding="utf-8")
    assert rig("install", "--mode", "lite", "--config", str(answers), "--yes") == 1
    said = capsys.readouterr().err
    assert "real" in said and "ospreyflow demo add enron" in said
    assert rig.runner.calls == []


def test_the_pack_list_marks_enron_as_real_data_and_the_install_page_leaves_it_out() -> None:
    from harness import install_page
    from scripts import demo_packs

    (enron,) = [p for p in demo_packs.packs() if p.id == "enron"]
    assert enron.real_data is True
    assert all(not p.real_data for p in demo_packs.packs() if p.id != "enron")
    assert "enron" not in [row["id"] for row in install_page._pack_rows()]


# --- never in CI (Amendment 23 point 1) --------------------------------------------------------

_NEVER_IN_AUTOMATION = ("demo add enron", "cs.cmu.edu/~enron", "--accept-real-data", "enron_mail_20150507")


def _automation_naming_enron(texts: dict[str, str]) -> list[str]:
    return [f"{name}: {word}" for name, text in texts.items() for word in _NEVER_IN_AUTOMATION if word in text]


def test_a_workflow_adding_enron_would_be_found() -> None:
    assert _automation_naming_enron({"ci.yml": "run: ospreyflow demo add enron --accept-real-data"})


def test_no_workflow_or_makefile_adds_enron() -> None:
    from tools.layout import BUILD, CORE, ROOT

    files = [*sorted((ROOT / ".github" / "workflows").glob("*.yml")),
             *sorted((CORE / ".github" / "workflows").glob("*.yml")),
             BUILD / "Makefile", CORE / "Makefile"]  # fmt: skip
    texts = {path.relative_to(ROOT).as_posix(): path.read_text(encoding="utf-8") for path in files}
    assert _automation_naming_enron(texts) == []


def test_the_command_and_the_pack_pin_the_same_file() -> None:
    from scripts import demo_packs

    (enron,) = [p for p in demo_packs.packs() if p.id == "enron"]
    assert enron.download is not None
    assert demo.ENRON_SHA256 == enron.download.sha256 == demo_packs.ENRON_SHA256
    assert len(demo.ENRON_SHA256) == 64 and demo.ENRON_FILE == enron.download.filename
