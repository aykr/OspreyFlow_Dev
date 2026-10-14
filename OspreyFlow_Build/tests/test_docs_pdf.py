"""The install package's guides and their PDFs stay in step (`06_DECISIONS.md` ADR-114 Amendment 15
point 2; `tools/docs_pdf.py`).

What a drift would do, and the case that catches it:
- a guide edited without its PDF made again — `test_a_changed_guide_is_out_of_step`;
- a screenshot replaced under a PDF — `test_a_changed_image_is_out_of_step`;
- a PDF swapped or edited by hand — `test_a_replaced_pdf_is_out_of_step`;
- a PDF never made — `test_a_guide_with_no_pdf_is_named`;
- a guide showing an image that is not there — `test_a_missing_image_is_named`;
- a screenshot nobody shows — `test_an_image_no_guide_shows_is_named`;
- the PDFs' own page taking a colour outside the tokens — `test_the_page_takes_every_colour_from_the_tokens`;
- the real guides out of step today — `test_the_guides_and_their_pdfs_are_in_step`.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
from tools import docs_pdf


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def docs(tmp_path: Path) -> Path:
    """A docs folder in step: each guide shows one image, and has a PDF the manifest names."""
    (tmp_path / "images").mkdir()
    (tmp_path / "pdf").mkdir()
    manifest = {}
    for name, _title in docs_pdf.GUIDES:
        stem = name.removesuffix(".md")
        image = f"images/{stem}.png"
        (tmp_path / image).write_bytes(f"png of {stem}".encode())
        text = f"# {stem}\n\n![a screen](images/{stem}.png)\n"
        (tmp_path / name).write_text(text, encoding="utf-8")
        (tmp_path / "pdf" / f"{stem}.pdf").write_bytes(f"%PDF {stem}".encode())
        manifest[name] = {
            "source": _sha(text.encode()),
            "images": {image: _sha(f"png of {stem}".encode())},
            "pdf": _sha(f"%PDF {stem}".encode()),
        }
    (tmp_path / "pdf" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path


def test_a_folder_in_step_has_no_problems(docs: Path) -> None:
    assert docs_pdf.check(docs) == []


def test_a_changed_guide_is_out_of_step(docs: Path) -> None:
    (docs / "user-guide.md").write_text("# user-guide\n\nA new sentence.\n", encoding="utf-8")
    problems = docs_pdf.check(docs)
    assert any("user-guide.md changed since user-guide.pdf was made" in p for p in problems)


def test_a_changed_image_is_out_of_step(docs: Path) -> None:
    (docs / "images" / "developer-guide.png").write_bytes(b"another screen")
    problems = docs_pdf.check(docs)
    assert problems == [
        (
            "developer-guide.md's images changed since developer-guide.pdf was made: run "
            "`python -m tools.docs_pdf --write`"
        )
    ]


def test_a_replaced_pdf_is_out_of_step(docs: Path) -> None:
    (docs / "pdf" / "administration-guide.pdf").write_bytes(b"%PDF edited by hand")
    assert any("administration-guide.pdf is not the one made" in p for p in docs_pdf.check(docs))


def test_a_guide_with_no_pdf_is_named(docs: Path) -> None:
    (docs / "pdf" / "user-guide.pdf").unlink()
    assert any("user-guide.pdf has not been made" in p for p in docs_pdf.check(docs))


def test_a_missing_image_is_named(docs: Path) -> None:
    (docs / "images" / "user-guide.png").unlink()
    assert any("user-guide.md shows images/user-guide.png, which is not there" in p
               for p in docs_pdf.check(docs))  # fmt: skip


def test_an_image_no_guide_shows_is_named(docs: Path) -> None:
    (docs / "images" / "spare.png").write_bytes(b"unused")
    assert docs_pdf.check(docs) == ["images/spare.png is in docs/images but no guide shows it"]


def test_the_page_takes_every_colour_from_the_tokens() -> None:
    literal = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(")
    assert not literal.findall(docs_pdf.DOC_CSS)
    named = re.findall(r"var\((--[a-z0-9-]+)\)", docs_pdf.DOC_CSS)
    tokens = docs_pdf.TOKENS.read_text(encoding="utf-8")
    assert named and all(f"{token}:" in tokens for token in named), "a token the page names is not defined"


def test_links_between_guides_point_at_their_pdfs(tmp_path: Path) -> None:
    made = docs_pdf.page("See the [user guide](user-guide.md#start).", "t", tmp_path)
    assert 'href="user-guide.pdf#start"' in made and 'data-theme="light"' in made


def test_the_guides_and_their_pdfs_are_in_step() -> None:
    assert docs_pdf.check() == [], "\n".join(docs_pdf.check())
