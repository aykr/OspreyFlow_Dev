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


def _control(version: str = "1.1", rows: str | None = None) -> str:
    """A version record as the guides write it (ADR-114 Amendment 26)."""
    history = rows or (
        f"| {version} | 2026-10-15 | Something new. |\n| 1.0 | 2026-10-14 | First issue. |\n"
    )
    return (
        "<!-- document-control:begin -->\n## Document control\n\n"
        f"**Version {version}** · 2026-10-15 · For OspreyFlow v0.1.0 · Issued\n\n"
        "| Version | Date | What changed |\n| --- | --- | --- |\n"
        f"{history}\n<!-- document-control:end -->\n\n"
    )


def _guide(stem: str, words: str = "", control: str | None = None) -> str:
    return f"# {stem}\n\nWho it is for.\n\n{control or _control()}![a screen](images/{stem}.png)\n{words}"


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
        text = _guide(stem)
        (tmp_path / name).write_text(text, encoding="utf-8")
        (tmp_path / "pdf" / f"{stem}.pdf").write_bytes(f"%PDF {stem}".encode())
        manifest[name] = {
            "source": _sha(text.encode()),
            "images": {image: _sha(f"png of {stem}".encode())},
            "pdf": _sha(f"%PDF {stem}".encode()),
            "version": "1.1",
            "body": _sha(docs_pdf.body_of(text).encode()),
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


def test_a_link_between_guides_is_printed_as_its_name_never_as_an_address(tmp_path: Path) -> None:
    """A browser prints a link as an absolute address — `file:///Users/<you>/…` — which would carry the
    printing machine's home folder out with the install package (the publish refused it, 14 October
    2026). So in the PDF a link to another guide is its words, naming the guide's file."""
    markdown = "# T\n\nWho.\n\n" + _control() + "See the [user guide](user-guide.md#start).\n"
    made = docs_pdf.page(markdown, "t", tmp_path)
    assert "href" not in made.split("<main>")[1]
    assert "the user guide (user-guide.pdf)" in made and 'data-theme="light"' in made


def test_a_pdf_carrying_a_local_address_is_named(docs: Path) -> None:
    pdf = docs / "pdf" / "user-guide.pdf"
    pdf.write_bytes(b"%PDF /URI (file:///Users/someone/docs/admin.pdf)")
    manifest = json.loads((docs / "pdf" / "manifest.json").read_text(encoding="utf-8"))
    manifest["user-guide.md"]["pdf"] = _sha(pdf.read_bytes())
    (docs / "pdf" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert docs_pdf.check(docs) == ["user-guide.pdf carries a local address (file:///Users/someone/…)"]


def test_the_guides_and_their_pdfs_are_in_step() -> None:
    assert docs_pdf.check() == [], "\n".join(docs_pdf.check())


# --- each guide's version record (ADR-114 Amendment 26) -----------------------------------------


def test_the_shipped_guides_each_carry_a_version_record() -> None:
    for name, _title in docs_pdf.GUIDES:
        control = docs_pdf.control_of((docs_pdf.DOCS / name).read_text(encoding="utf-8"))
        assert control.history[0][:2] == (control.version, control.date), name


def test_content_changed_without_a_new_version_is_named_and_not_printed(docs: Path) -> None:
    """The gate's purpose: the history is kept, not merely present. Red in the shape a real edit
    takes — a sentence added below the version record, the record untouched."""
    (docs / "user-guide.md").write_text(_guide("user-guide", "A new sentence.\n"), encoding="utf-8")
    problems = docs_pdf.check(docs)
    assert any("user-guide.md changed since version 1.1 without a new version" in p for p in problems)
    with pytest.raises(SystemExit, match="without a new version"):
        docs_pdf.write(docs)


def test_the_same_change_with_its_own_history_row_is_not_named(docs: Path) -> None:
    rows = "| 1.2 | 2026-10-15 | A new sentence. |\n| 1.1 | 2026-10-15 | Something new. |\n"
    text = _guide("user-guide", "A new sentence.\n", _control("1.2", rows))
    (docs / "user-guide.md").write_text(text, encoding="utf-8")
    assert not any("without a new version" in p for p in docs_pdf.check(docs))


@pytest.mark.parametrize(
    ("control", "says"),
    [
        ("", "no document control section"),
        (_control("1.2"), "newest history row is"),  # the line says 1.2, the table's top is 1.1
        (
            _control("1.1", "| 1.1 | 2026-10-15 | B. |\n| 1.2 | 2026-10-14 | A. |\n"),
            "not newest first",
        ),
    ],
)
def test_a_malformed_version_record_is_named(docs: Path, control: str, says: str) -> None:
    text = f"# user-guide\n\nWho.\n\n{control}![a screen](images/user-guide.png)\n"
    if control == _control("1.2"):
        text = text.replace("| 1.2 | 2026-10-15 | Something new. |", "| 1.1 | 2026-10-15 | X. |")
    (docs / "user-guide.md").write_text(text, encoding="utf-8")
    assert any(says in p for p in docs_pdf.check(docs)), docs_pdf.check(docs)


def test_page_numbers_are_read_after_the_list_of_figures_not_where_its_words_first_occur() -> None:
    """The first printing found every heading on the contents page: the version history said "a
    list of figures", and the search for where the guide's text begins stopped there."""
    markdown = "# G\n\nWho.\n\n" + _control() + "## 1. First\n\n![A screen](x.png)\n\n## 2. Second\n"
    pages = [
        "OSPREYFLOW G",
        "Document control ... a list of figures, and this version history.",
        "Contents 1. First 000 2. Second 000",
        "List of figures Figure 1 — A screen 000",
        "1. First text Figure 1. A screen",
        "2. Second more text",
    ]
    assert docs_pdf.locate(pages, markdown) == {"s1": 5, "s2": 6, "f1": 5}
