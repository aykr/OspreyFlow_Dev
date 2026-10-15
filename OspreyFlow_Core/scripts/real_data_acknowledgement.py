"""A real dataset accepted by the person adding it, on their own machine (ADR-114 Amendment 23).

`ospreyflow demo add enron` shows what the corpus is — real people's email and personal data, no
licence stated, CMU's request to be sensitive to their privacy — and writes this record beside the
unpacked corpus only once the person has answered `yes` (or passed `--accept-real-data`). The seed
runner admits the dataset by it; the owner's local exceptions list (`scripts.real_data_exceptions`)
admits it too, as before. The record never leaves the machine: it sits in the demo data folder,
which every packaging and publish check refuses.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

RECORD = "ACCEPTED_REAL_DATA.json"

#: What the person accepted, kept in the record in the same words they were shown.
STATEMENT = (
    "This corpus is real people's email: their names, addresses and private correspondence. No "
    "licence is stated for it; Carnegie Mellon University distributes it as a resource for "
    "researchers and asks that you be sensitive to the privacy of the people involved. Your "
    "organisation needs its own lawful basis to process this personal data. It stays on this "
    "machine and is never shared by OspreyFlow."
)


def record(folder: Path, dataset: str, *, source_file: str, sha256: str) -> Path:
    """Writes the acceptance beside the corpus; called only after the person has accepted."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / RECORD
    path.write_text(
        json.dumps(
            {
                "dataset": dataset,
                "accepted": True,
                "accepted_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "source_file": source_file,
                "sha256": sha256,
                "statement": STATEMENT,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def accepted(folder: Path, dataset: str) -> bool:
    """Whether the corpus in `folder` was accepted for `dataset`. Anything else — no record, a
    record for another dataset, a damaged one — is a refusal, never a crash and never permission."""
    try:
        held = json.loads((folder / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(held, dict):
        return False
    return held.get("dataset") == dataset and held.get("accepted") is True
