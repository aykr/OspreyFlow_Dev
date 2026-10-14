"""The guided install page, present and current before it is served (ADR-114 Amendment 11).

What a mistake would do, and the case that catches it:
- the build's stamp and the install's check disagreeing about a hash, so every page reads stale —
  `test_the_build_and_the_install_hash_the_same_sources_alike` (Node and Python on the same files);
- a page built from older sources served as current — `test_a_changed_source_makes_the_page_stale`;
- a missing page met with a traceback, or a blank page — `test_with_no_page_and_no_release_it_says_how_to_build_it`;
- a release's page unpacked without its signature checked, or over a good one when the check fails —
  `test_a_release_page_whose_signature_fails_is_not_unpacked`;
- an archive writing outside its folder — `test_an_archive_reaching_outside_its_folder_is_refused`.
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest
from harness import install_page_build as page
from tools.layout import CORE

STAMP_SCRIPT = CORE / "apps" / "harness" / "scripts" / "stamp.mjs"


def _product(tmp_path: Path) -> Path:
    root = tmp_path / "product"
    for path, text in {
        "apps/harness/src/main.tsx": "export {};\n",
        "apps/harness/src/screens/Mode.tsx": "// Mode — ünïcode\n",
        "apps/harness/src/.DS_Store": "junk",
        "apps/harness/src/Icon\r": "",
        "apps/harness/index.html": "<div id=root></div>",
        "apps/harness/package.json": json.dumps({"name": "x"}),
        "apps/workspace/src/design/tokens.css": ":root{}",
        "apps/workspace/src/theme/theme.ts": "export const t = 1;\n",
        "apps/workspace/src/other/not-a-source.ts": "x",
    }.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


def _built(root: Path) -> None:
    dist = root / page.DIST
    dist.mkdir(parents=True, exist_ok=True)
    (dist / "index.html").write_text("<html>built</html>", encoding="utf-8")
    (dist / page.STAMP).write_text(page.source_hash(root) + "\n", encoding="utf-8")


@pytest.mark.skipif(shutil.which("node") is None, reason="needs Node, as the build does")
def test_the_build_and_the_install_hash_the_same_sources_alike(tmp_path: Path) -> None:
    root = _product(tmp_path)
    said = subprocess.run(
        ["node", "--input-type=module", "-e",
         f"import {{ sourceHash }} from {json.dumps(STAMP_SCRIPT.as_uri())}; "
         f"console.log(sourceHash({json.dumps(str(root))}))"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()  # fmt: skip
    assert said == page.source_hash(root)


def test_junk_and_other_folders_do_not_count(tmp_path: Path) -> None:
    root = _product(tmp_path)
    before = page.source_hash(root)
    (root / "apps/harness/src/.DS_Store").write_text("other junk", encoding="utf-8")
    (root / "apps/workspace/src/other/not-a-source.ts").write_text("y", encoding="utf-8")
    assert page.source_hash(root) == before


def test_a_page_built_from_these_sources_is_current(tmp_path: Path) -> None:
    root = _product(tmp_path)
    assert not page.is_current(root)
    _built(root)
    assert page.is_current(root)


def test_a_changed_source_makes_the_page_stale(tmp_path: Path) -> None:
    root = _product(tmp_path)
    _built(root)
    (root / "apps/workspace/src/design/tokens.css").write_text(":root{--x:1}", encoding="utf-8")
    assert not page.is_current(root)


def _never(*_: object) -> tuple[bytes, bytes]:
    raise AssertionError("nothing may be fetched")


def test_a_current_page_is_used_and_nothing_fetched(tmp_path: Path) -> None:
    root = _product(tmp_path)
    _built(root)
    said = page.ensure(root, release_tag="v1.2.3", fetch=_never, verify=_never)
    assert "built from this checkout" in said


def test_with_no_page_and_no_release_it_says_how_to_build_it(tmp_path: Path) -> None:
    root = _product(tmp_path)
    with pytest.raises(page.InstallPageMissing, match="npm run build"):
        page.ensure(root, release_tag=None, fetch=_never, verify=_never)


def _archive(members: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return out.getvalue()


def test_on_a_release_its_signed_page_is_fetched_checked_and_unpacked(tmp_path: Path) -> None:
    root = _product(tmp_path)
    stamp = (page.source_hash(root) + "\n").encode()
    archive = _archive({"index.html": b"<html>release</html>", page.STAMP: stamp,
                        "assets/app.js": b"1"})  # fmt: skip
    checked: list[str] = []

    def verify(tag: str, archive_path: Path, signature_path: Path) -> None:
        assert archive_path.read_bytes() == archive and signature_path.read_bytes() == b"bundle"
        checked.append(tag)

    said = page.ensure(root, release_tag="v1.2.3", fetch=lambda tag: (archive, b"bundle"),
                       verify=verify)  # fmt: skip
    assert checked == ["v1.2.3"] and "v1.2.3" in said
    assert (root / page.DIST / "index.html").read_text() == "<html>release</html>"
    assert page.is_current(root)


def test_a_release_page_whose_signature_fails_is_not_unpacked(tmp_path: Path) -> None:
    root = _product(tmp_path)
    (root / page.DIST).mkdir(parents=True)
    (root / page.DIST / "index.html").write_text("<html>what was there</html>", encoding="utf-8")

    def refuse(*_: object) -> None:
        raise RuntimeError("no matching signatures")

    with pytest.raises(page.InstallPageMissing, match="not signed by its release"):
        page.ensure(root, release_tag="v1.2.3",
                    fetch=lambda tag: (_archive({"index.html": b"evil"}), b"x"), verify=refuse)  # fmt: skip
    assert (root / page.DIST / "index.html").read_text() == "<html>what was there</html>"


def test_an_archive_reaching_outside_its_folder_is_refused(tmp_path: Path) -> None:
    root = _product(tmp_path)
    bad = _archive({"index.html": b"x", "../../escaped.txt": b"x"})
    with pytest.raises(page.InstallPageMissing, match="unpacked safely"):
        page.unpack(root, bad)
    assert not (tmp_path / "escaped.txt").exists() and not (root / "escaped.txt").exists()
