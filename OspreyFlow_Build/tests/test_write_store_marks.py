"""`tools/write_store_marks.py`, the mark commit as a script (admin's T1 part 2, 10 November 2026).

Each shape a live test file takes today is marked, and pytest itself is asked what it selects: a file is proved
marked by `pytest --collect-only -m store` finding its tests, not by the text alone. Red if a shape is left unmarked,
marked twice, broken, or loses a mark it had.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tools.write_store_marks import is_marked, main, marked

SHAPES = {
    "no_mark": '"""A live test."""\n\nfrom __future__ import annotations\n\nimport pytest\n\n\ndef test_a():\n    pass\n',
    "no_import_of_pytest": '"""A live test."""\n\nimport os\n\n\ndef test_a():\n    assert os\n',
    "nothing_imported": "def test_a():\n    pass\n",
    "a_single_mark": "import pytest\n\npytestmark = pytest.mark.usefixtures('x')\n\n\n@pytest.fixture\ndef x():\n    return 1\n\n\ndef test_a():\n    pass\n",
    "a_list_on_one_line": "import pytest\n\npytestmark = [pytest.mark.usefixtures('x')]\n\n\n@pytest.fixture\ndef x():\n    return 1\n\n\ndef test_a():\n    pass\n",
    "a_list_over_lines": (
        "import pytest\n\npytestmark = [\n    pytest.mark.usefixtures('x'),\n    pytest.mark.filterwarnings('ignore'),\n]\n\n\n"
        "@pytest.fixture\ndef x():\n    return 1\n\n\ndef test_a():\n    pass\n"
    ),
    "an_empty_list": "import pytest\n\npytestmark: list = []\n\n\ndef test_a():\n    pass\n",
    "already_marked": "import pytest\n\npytestmark = [pytest.mark.store]\n\n\ndef test_a():\n    pass\n",
}


def _collect(path: Path, *args: str) -> str:
    ran = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", "-c", os.devnull,
         "--rootdir", str(path.parent), "-W", "ignore::pytest.PytestUnknownMarkWarning", *args, str(path)],
        capture_output=True, text=True, cwd=path.parent,
    )  # fmt: skip
    return ran.stdout


@pytest.mark.parametrize("shape", list(SHAPES))
def test_each_shape_is_marked_once_keeps_its_own_marks_and_pytest_selects_it(tmp_path: Path, shape: str) -> None:
    source = SHAPES[shape]
    once = marked(source)
    assert is_marked(once)
    assert marked(once) == once, "a second run changed the file"
    if shape == "already_marked":
        assert once == source
    compile(once, shape, "exec")
    path = tmp_path / f"test_{shape}.py"
    path.write_text(once)
    assert "test_a" in _collect(path, "-m", "store"), once
    assert "no tests collected" in _collect(path, "-m", "not store") or "deselected" in _collect(path, "-m", "not store")
    for kept in ("usefixtures('x')", "filterwarnings('ignore')"):
        if kept in source:
            assert kept in once, once


def test_check_names_each_unmarked_file_and_writing_marks_them(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools import write_store_marks

    monkeypatch.setattr(write_store_marks, "BUILD", tmp_path)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_one.py").write_text(SHAPES["no_mark"])
    (tmp_path / "tests" / "test_two.py").write_text(SHAPES["already_marked"])
    files = ["tests/test_one.py", "tests/test_two.py"]
    assert main(["--check", *files]) == 1
    assert main(files) == 0
    assert main(["--check", *files]) == 0
    assert (tmp_path / "tests" / "test_two.py").read_text() == SHAPES["already_marked"]


def test_every_live_file_here_can_be_marked_and_read_back() -> None:
    """Today's live set, marked in memory: each file still parses, is marked once, and keeps its other marks."""
    from tools.live_select import Repo

    build = Path(__file__).resolve().parents[1]
    for rel in Repo().live_set():
        source = (build / rel).read_text(encoding="utf-8")
        once = marked(source)
        compile(once, rel, "exec")
        assert is_marked(once) and marked(once) == once, rel
