"""A real dataset accepted on one machine (ADR-114 Amendment 23): `ospreyflow demo add enron` writes
the record only after the person has accepted what the corpus is, beside the unpacked corpus; the seed
runner admits the dataset by it (or by the owner's local exceptions entry, as before).

What a mistake would do, and the case that catches it:
- a corpus admitted with no acceptance — `test_no_record_is_no_admission`;
- a record for another dataset, or one that says it was not accepted, admitting it —
  `test_a_record_for_another_dataset_or_not_accepted_does_not_admit`;
- a damaged record read as acceptance — `test_an_unreadable_record_is_a_refusal_not_a_crash`;
- the record saying more than it needs to — `test_the_record_holds_when_which_file_and_what_was_accepted`.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts import real_data_acknowledgement as ack


def test_no_record_is_no_admission(tmp_path: Path) -> None:
    assert ack.accepted(tmp_path, "enron") is False


def test_the_record_holds_when_which_file_and_what_was_accepted(tmp_path: Path) -> None:
    ack.record(tmp_path, "enron", source_file="enron_mail_20150507.tar.gz", sha256="ab" * 32)
    held = json.loads((tmp_path / ack.RECORD).read_text(encoding="utf-8"))
    assert set(held) == {"dataset", "accepted", "accepted_at", "source_file", "sha256", "statement"}
    assert held["dataset"] == "enron" and held["accepted"] is True
    assert "real people" in held["statement"]
    assert ack.accepted(tmp_path, "enron") is True


def test_a_record_for_another_dataset_or_not_accepted_does_not_admit(tmp_path: Path) -> None:
    ack.record(tmp_path, "paysim", source_file="x", sha256="0" * 64)
    assert ack.accepted(tmp_path, "enron") is False
    (tmp_path / ack.RECORD).write_text(json.dumps({"dataset": "enron", "accepted": False}), encoding="utf-8")
    assert ack.accepted(tmp_path, "enron") is False


def test_an_unreadable_record_is_a_refusal_not_a_crash(tmp_path: Path) -> None:
    (tmp_path / ack.RECORD).write_text("{not json", encoding="utf-8")
    assert ack.accepted(tmp_path, "enron") is False
