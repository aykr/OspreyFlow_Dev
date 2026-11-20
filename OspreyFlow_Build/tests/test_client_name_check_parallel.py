"""`tools.client_name_check` on the branch the real tree takes (slice BL6, round 4). A tree of `PARALLEL_FROM` files or
more is scanned in a pool of worker processes, each given its hashes only through the `_start` initialiser. The real
tree is about 5,000 files, so `make client-name-check` always takes that branch; the other cases plant in a repository
of a few files, which is read in this process. Planted as the real caller produces them: the pool is made to be used
(a repository of `PARALLEL_FROM` files or more), and the name is found by a worker that was given its hashes by the
initialiser, not by this process.
"""

from __future__ import annotations

from concurrent import futures
from pathlib import Path

import pytest

from tests.test_client_name_check import (
    SYNTHETIC_ABBREVIATION,
    SYNTHETIC_CLIENT,
    _list,
    _repo,
    _run,
)
from tools import client_name_check

PLANTED = "OspreyFlow_Build/spec/planted.md"


def _tree(count: int) -> dict[str, str]:
    files = {f"OspreyFlow_Build/spec/clean_{n}.md": f"A clean line {n}.\n" for n in range(count - 1)}
    files[PLANTED] = f"A line.\nRead as {SYNTHETIC_CLIENT} reads it.\n"
    return files


@pytest.fixture
def pool_used(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """The pools made during the scan: a case that planted a name but never reached the pool proves nothing."""
    made: list[int] = []
    real = futures.ProcessPoolExecutor

    def counting(*args: object, **kwargs: object) -> futures.ProcessPoolExecutor:
        made.append(1)
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(client_name_check, "ProcessPoolExecutor", counting)
    return made


def test_a_name_in_a_tree_scanned_by_the_pool_is_flagged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], pool_used: list[int], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(client_name_check, "PARALLEL_FROM", 1)
    root = _repo(tmp_path, _tree(4))
    code, out = _run(root, _list(tmp_path), capsys)
    assert pool_used, "the scan did not use the pool, so this case planted nothing on the branch it names"
    assert code == 1, out
    assert f"{PLANTED}:2:" in out, out
    assert "1 hit(s) in 1 file(s)" in out.splitlines()[-1], out
    assert SYNTHETIC_CLIENT not in out and SYNTHETIC_ABBREVIATION not in out


def test_a_name_in_a_tree_of_the_real_threshold_is_flagged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], pool_used: list[int]
) -> None:
    """No change to `PARALLEL_FROM`: a repository of that many tracked files, as the real tree is."""
    root = _repo(tmp_path, _tree(client_name_check.PARALLEL_FROM))
    code, out = _run(root, _list(tmp_path), capsys)
    assert pool_used, "a tree of PARALLEL_FROM files was not scanned by the pool"
    assert code == 1, out
    assert f"{PLANTED}:2:" in out, out


def test_a_clean_tree_scanned_by_the_pool_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], pool_used: list[int], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(client_name_check, "PARALLEL_FROM", 1)
    files = {k: v for k, v in _tree(4).items() if k != PLANTED}
    code, out = _run(_repo(tmp_path, files), _list(tmp_path), capsys)
    assert pool_used
    assert code == 0, out

