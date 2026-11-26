"""The README's citations of the line's own scripts and tests, by their full paths, name files that exist.

make ci's citation-check (`OspreyFlow_Build/tools/doc_citations_check.py`) checks a backticked path only when it
begins with one of the project's logical folders (`tests/`, `scripts/`, ...), and maps `scripts/` to
OspreyFlow_Core. The line's files live in OspreyFlow_Build/scripts/slice_line, so the README cites them by their full
paths, which that check never reads. 54's line 131 cited the short tests/run.sh instead: the check read it, could not
resolve it, and main was red on citation-check from 05:47 on 26 November 2026 until 61. Cited by the full path, a
wrong name would pass make ci unseen; this check reads those.
"""
from __future__ import annotations

import re
from pathlib import Path

TOP = Path(__file__).resolve().parents[4]
README = TOP / "OspreyFlow_Build/process/lanes/v062/slice-line/README.md"
CITED = re.compile(r"`(OspreyFlow_Build/scripts/[A-Za-z0-9_./-]+\.[A-Za-z0-9]+)`")


def not_there(text: str, top: Path = TOP) -> list[str]:
    """Each line's citation of a file under OspreyFlow_Build/scripts/ that is not in the checkout."""
    missing = []
    for number, line in enumerate(text.splitlines(), start=1):
        for cited in CITED.findall(line):
            if not (top / cited).is_file():
                missing.append(f"{number}: {cited}")
    return missing


def test_every_script_and_test_the_readme_cites_by_its_full_path_exists():
    text = README.read_text()
    assert CITED.search(text), "the README cites none of the line's files by its full path"
    assert not_there(text) == []


def test_a_cited_file_not_there_is_named_and_one_there_is_not():
    text = ("`OspreyFlow_Build/scripts/slice_line/tests/run.sh` and\n"
            "`OspreyFlow_Build/scripts/slice_line/demo_server/tests/run.sh` print a beat;\n"
            "`OspreyFlow_Build/scripts/slice_line/tests/test_no_such_file.py` cites a test not written.\n")
    assert not_there(text) == ["3: OspreyFlow_Build/scripts/slice_line/tests/test_no_such_file.py"]
