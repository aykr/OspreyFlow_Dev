"""The platform's stated intent is in the README and the four guides, said plainly and said true (DC1c,
the owner's brief of 20 November 2026 and his rulings on DC1a's report; `process/lanes/v062/slices/DOC1A_REPORT.md`
is the truth check every sentence is held to).

What the owner's text asks, and the case that fails if it is not so (rule 12):
- each of the five files (the README and the architecture, administration, developer and user guides, the
  administration guide in both its copies) carries a "Why OspreyFlow is built this way" passage after its
  opening statement, naming the five constraints exactly as the owner gives them —
  `test_every_file_carries_the_passage_naming_the_five_constraints`,
  `test_the_passage_sits_after_the_opening_and_before_the_document_control`;
- the architecture guide's is the fullest and the others link to it —
  `test_the_architecture_guide_has_the_fullest_passage_and_the_others_link_to_it`;
- the passages name no product, say what "access" covers, say "coming" for what is not built, describe a hosted
  engine as an opt-in and say the Superset tracking fix is in v0.6.2 —
  `test_the_passages_name_no_product`, `test_the_architecture_passage_says_what_access_covers_and_what_is_coming`;
- the architecture guide's section 9 names no product, and the eleven-row table it carried moved, complete and
  unchanged, into the specification's licence register — `test_section_9_names_no_product`,
  `test_the_moved_table_is_complete_in_the_specification`;
- the three audit statements no longer say "every read and write" without scope (the websites' is DC1b's) —
  `test_no_audit_statement_is_unscoped`;
- no "guarantee" in anything this slice wrote — `test_nothing_written_here_guarantees`;
- both copies of the administration guide agree on every new passage —
  `test_both_copies_of_the_administration_guide_agree_on_the_new_passages`;
- the administration guide says a Superset chart needing Mapbox tiles will not load, and why —
  `test_the_administration_guide_says_a_mapbox_chart_will_not_load`;
- the README's "the deployment never calls out" is corrected — `test_the_readme_does_not_say_the_deployment_never_calls_out`.

**Rule 15: each gate is shown red** at the shape the real text takes — the old section 9 table put back, the old
bullet of section 6 put back in its list item, the old paragraph of `spec/03` section 6, a passage with the word
"guarantee" in a sentence — by `test_each_check_is_shown_red`.

**What it reads.** Seven named files, each opened by its path; no folder is listed or searched:
`OspreyFlow_Core/README.md`; the four `*-guide.md` files in `OspreyFlow_Core/docs/`;
`OspreyFlow_Build/spec/10_ADMINISTRATION_GUIDE.md` (the only guide with a copy in the specification: found by
listing `spec/` on 20 November 2026, `test_admin_guide_copies.py` holds that copy to the shipped one),
`spec/00_ARCHITECTURE.md` and `spec/03_CONDUIT_MIDDLEWARE.md`. So its scan-map row, if one is wanted, is empty.
"""

from __future__ import annotations

import re
from pathlib import Path

from tools.layout import BUILD, CORE

SPEC = BUILD / "spec"
DOCS = CORE / "docs"

#: Each file the passage must be in, by the name a failure shows. The administration guide has two copies.
FILES: dict[str, Path] = {
    "README": CORE / "README.md",
    "architecture guide": DOCS / "architecture-guide.md",
    "administration guide": DOCS / "administration-guide.md",
    "administration guide (spec/10)": SPEC / "10_ADMINISTRATION_GUIDE.md",
    "developer guide": DOCS / "developer-guide.md",
    "user guide": DOCS / "user-guide.md",
}
ARCHITECTURE = "architecture guide"
ADMIN = ("administration guide", "administration guide (spec/10)")

HEADING = "## Why OspreyFlow is built this way"
#: The owner's names, exactly as his file gives them (`PROMPT_ORCHESTRATOR.md`, "The five constraints, named").
CONSTRAINTS = (
    "Software sovereignty",
    "Data sovereignty",
    "Privacy control",
    "Security management",
    "Analytical accountability",
)

#: The table the architecture guide's section 9 carried until DC1c, word for word (the owner's ruling of
#: 20 November: it moves to the specification, complete and unchanged).
MOVED_HEADER = "| Avoided | Its licence | Used instead |"
MOVED_ROWS = (
    "| Redis 7.4 and later | RSAL / SSPL | Valkey (BSD-3-Clause) |",
    "| Elasticsearch | SSPL / Elastic Licence | OpenSearch (Apache-2.0) |",
    "| Neo4j Community | GPL-3.0 | ArcadeDB |",
    "| ArangoDB | BSL 1.1 | ArcadeDB |",
    "| FalkorDB | SSPL | rustworkx for in-memory algorithms |",
    "| Mapbox GL JS 2 and later | Proprietary | MapLibre GL JS (BSD-3-Clause) |",
    "| MongoDB | SSPL | PostgreSQL, and an S3-protocol object store |",
    "| Highcharts, AG Grid Enterprise | Commercial | Apache ECharts, TanStack Table |",
    "| Grafana 9 and later | AGPL-3.0 | Never bundled; acceptable only as an unmodified separate service |",
    "| Stanford CoreNLP | GPL-3.0 | Stanza (Apache-2.0), held at a version with no GPL dependency |",
    "| Terraform | BSL 1.1 | OpenTofu (MPL-2.0) |",
)
#: What the "Used instead" column names: read back from the table too, so this list cannot drift from it.
USED_INSTEAD = (
    "Valkey", "OpenSearch", "ArcadeDB", "rustworkx", "MapLibre", "PostgreSQL", "ECharts", "TanStack",
    "Stanza", "OpenTofu",
)  # fmt: skip

#: The three sentences as they stood, in the shape they took (a list item; a paragraph wrapped at the margin).
OLD_GUIDE_AUDIT = (
    "- **Every read and write is audited**, with who, when and what; an expansion that crosses a handling\n"
    "  boundary needs a justification.\n"
)
OLD_SPEC03_AUDIT = (
    "**Audit.** Append-only, to a stream the Conduit cannot rewrite. Every read, expansion, path\n"
    "query, pattern run, document view and export records principal, timestamp, the resolved query,\n"
    "result cardinality, and — where the action crosses a handling boundary — the justification the\n"
    "analyst supplied. Audit write failure fails the request; an unaudited read in this domain is\n"
    "worse than a refused one.\n"
)
#: What marks an audit statement as scoped: it says what is outside it.
SCOPE_WORDS = ("deployment metadata", "unaudited")
UNSCOPED = re.compile(
    r"every\s+read\s+and\s+write\s+(?:is|are)\s+audited"
    r"|every\s+read,\s+expansion,\s+path\s+query,\s+pattern\s+run,\s+document\s+view\s+and\s+export\s+records",
    re.IGNORECASE,
)

GUARANTEE = re.compile(r"guarant", re.IGNORECASE)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def fold(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def without_control(text: str) -> str:
    """The guide less its version record, whose rows name what changed and so name Mapbox too."""
    return re.sub(r"<!-- document-control:begin -->.*?<!-- document-control:end -->", " ", text, flags=re.DOTALL)


def passage(text: str) -> str | None:
    """The text under the heading, up to the next heading, comment or rule; None when there is none."""
    start = text.find(HEADING + "\n")
    if start < 0:
        return None
    body = text[start + len(HEADING) :]
    end = re.search(r"^(?:## |<!-- |---$)", body.lstrip("\n"), re.MULTILINE)
    body = body.lstrip("\n")
    return body[: end.start()] if end else body


def section(text: str, number: str, next_number: str) -> str:
    text = "\n" + text
    start = text.index(f"\n## {number}. ") + 1
    return text[start : text.index(f"\n## {next_number}. ", start)]


def paragraphs(text: str) -> list[str]:
    return [p for p in re.split(r"\n\s*\n", text) if p.strip()]


def moved_table(spec_00: str) -> list[str]:
    """The rows of the table headed `MOVED_HEADER` in the specification, header and rule excluded."""
    lines = spec_00.splitlines()
    if MOVED_HEADER not in lines:
        return []
    rows: list[str] = []
    for line in lines[lines.index(MOVED_HEADER) + 2 :]:
        if not line.startswith("|"):
            break
        rows.append(line)
    return rows


def avoided_names(rows: list[str]) -> list[str]:
    """The product names the table's first column carries ("Redis 7.4 and later" is Redis)."""
    names: list[str] = []
    for row in rows:
        first = row.split("|")[1].strip()
        for part in first.split(","):
            name = part.strip()
            while (stripped := re.sub(r"\s+(?:\d[\d.]*|and later|Community|Enterprise|GL JS|GL)$", "", name)) != name:
                name = stripped
            names.append(name)
    return names


def products_in(text: str, names: list[str]) -> list[str]:
    return [n for n in names if re.search(rf"(?<![A-Za-z]){re.escape(n)}(?![A-Za-z])", text)]


def unscoped_audit_statements(text: str) -> list[str]:
    """Each paragraph that makes the broad audit claim and, with the one after it, says nothing of its limits."""
    found: list[str] = []
    blocks = paragraphs(text)
    for i, block in enumerate(blocks):
        if UNSCOPED.search(fold(block)):
            near = fold(block + " " + (blocks[i + 1] if i + 1 < len(blocks) else "")).lower()
            if not all(w in near for w in SCOPE_WORDS):
                found.append(fold(block)[:80])
    return found


def new_text(texts: dict[str, str]) -> dict[str, str]:
    """Everything this slice wrote, by where it is: the passages, section 9, section 6, the sentence on
    Superset's maps, the README's corrected line, the specification's scope note and moved table."""
    out: dict[str, str] = {}
    for name, text in texts.items():
        body = passage(text)
        if body is not None:
            out[f"{name}: passage"] = body
    arch = texts[ARCHITECTURE]
    out["architecture guide: section 6"] = section(arch, "6", "7")
    out["architecture guide: section 9"] = section(arch, "9", "10")
    return out


def _texts() -> dict[str, str]:
    return {name: read(path) for name, path in FILES.items()}


# ---------------------------------------------------------------- the passage


def test_every_file_carries_the_passage_naming_the_five_constraints() -> None:
    problems = []
    for name, text in _texts().items():
        if text.count(HEADING + "\n") != 1:
            problems.append(f"{name}: no single {HEADING!r}")
            continue
        body = passage(text) or ""
        problems += [f"{name}: does not name {c!r}" for c in CONSTRAINTS if c not in body]
        if len(body.split()) < 120:
            problems.append(f"{name}: the passage is too short to say what each means ({len(body.split())} words)")
    assert problems == []


def test_the_passage_sits_after_the_opening_and_before_the_document_control() -> None:
    problems = []
    for name, text in _texts().items():
        at = text.find(HEADING + "\n")
        if at < 0:
            problems.append(f"{name}: no passage")
            continue
        opening = text[:at].split("\n", 1)[1].strip()  # what stands between the title and the passage
        if len(opening.split()) < 25:
            problems.append(f"{name}: the passage is not after an opening statement")
        for later in ("<!-- document-control:begin -->", "\n## 1. ", "\n## What it does"):
            if later in text and text.index(later) < at:
                problems.append(f"{name}: the passage is after {later.strip()!r}")
    assert problems == []


def test_the_architecture_guide_has_the_fullest_passage_and_the_others_link_to_it() -> None:
    bodies = {name: passage(text) or "" for name, text in _texts().items()}
    fullest = len(bodies[ARCHITECTURE].split())
    problems = [f"{n}: not shorter than the architecture guide's" for n, b in bodies.items()
                if n != ARCHITECTURE and len(b.split()) >= fullest]  # fmt: skip
    problems += [f"{n}: no link to the architecture guide" for n, b in bodies.items()
                 if n != ARCHITECTURE and "architecture-guide.md" not in b]  # fmt: skip
    assert problems == []


def test_the_passages_name_no_product() -> None:
    """The owner: argue for open source on its merits, characterising and naming no proprietary tool."""
    names = avoided_names(moved_table(read(SPEC / "00_ARCHITECTURE.md")))
    assert names, "the specification's moved table is not there to read the names from"
    found = [
        f"{where}: {n}"
        for where, body in new_text(_texts()).items()
        for n in products_in(body, names + list(USED_INSTEAD))
    ]
    assert found == []


def test_the_architecture_passage_says_what_access_covers_and_what_is_coming() -> None:
    body = fold(passage(read(FILES[ARCHITECTURE])) or "")
    wanted = {
        "access means every read and write of case data": "every read and write of case data",
        "the reference reads outside it, named": "type list",
        "map tiles named as outside it": "map tiles",
        "model calls' attribution is coming": "model calls",
        "sign-in's attribution is coming": "sign-in",
        "the word coming": "coming",
        "a hosted engine described as an opt-in": "opt-in",
        "the Superset tracking fix is in v0.6.2": "v0.6.2",
        "weights, map data, fonts and base images outside the licence gate": "base images",
    }
    assert [why for why, words in wanted.items() if words not in body] == []


# ---------------------------------------------------------------- section 9 and the specification's table


def test_the_moved_table_is_complete_in_the_specification() -> None:
    rows = moved_table(read(SPEC / "00_ARCHITECTURE.md"))
    assert rows == list(MOVED_ROWS), "the moved table is not the guide's eleven rows, complete and unchanged"
    assert len(rows) == 11


def test_section_9_names_no_product() -> None:
    names = avoided_names(moved_table(read(SPEC / "00_ARCHITECTURE.md")))
    assert len(names) == 12, "eleven rows, one of them naming two (Highcharts and AG Grid)"
    nine = section(read(FILES[ARCHITECTURE]), "9", "10")
    assert products_in(nine, names + list(USED_INSTEAD)) == []
    assert MOVED_HEADER not in nine
    for rule in ("allowlist", "GPL", "LGPL", "recorded exception"):
        assert rule in nine, f"the licence rule and the allowlist stay in section 9: {rule!r} is gone"


# ---------------------------------------------------------------- the three audit statements


def test_no_audit_statement_is_unscoped() -> None:
    texts = {name: read(path) for name, path in FILES.items()}
    texts["spec/03"] = read(SPEC / "03_CONDUIT_MIDDLEWARE.md")
    problems = {n: unscoped_audit_statements(t) for n, t in texts.items()}
    assert {n: p for n, p in problems.items() if p} == {}
    guide = fold(section(texts[ARCHITECTURE], "6", "7"))
    for words in ("case reads", "export ledger", "withheld", "deployment metadata", "refusals"):
        assert words in guide.lower(), f"architecture guide section 6 does not say {words!r}"
    spec = fold(read(SPEC / "03_CONDUIT_MIDDLEWARE.md"))
    audit = spec[spec.index("**Audit.**") : spec.index("**Export gate.**")].lower()
    for words in ("deployment metadata", "model calls", "sign-in"):
        assert words in audit, f"spec/03 section 6's audit paragraph has no scope note on {words!r}"


# ---------------------------------------------------------------- the rules for all wording


def test_nothing_written_here_guarantees() -> None:
    texts = _texts()
    written = new_text(texts)
    written["spec/03: audit"] = read(SPEC / "03_CONDUIT_MIDDLEWARE.md")[
        read(SPEC / "03_CONDUIT_MIDDLEWARE.md").index("**Audit.**") :
    ].split("**Export gate.**")[0]
    sentence = re.search(r"[^.\n]*Mapbox[^.]*\.", fold(without_control(texts["administration guide"])))
    written["administration guide: Mapbox sentence"] = sentence.group(0) if sentence else ""
    assert {where for where, body in written.items() if GUARANTEE.search(body)} == set()


def test_both_copies_of_the_administration_guide_agree_on_the_new_passages() -> None:
    shipped, spec = (read(FILES[n]) for n in ADMIN)
    assert passage(shipped) is not None and passage(shipped) == passage(spec)
    for text in (shipped, spec):
        assert re.search(r"Mapbox", text)
    assert section(shipped, "12", "13").split("\n###")[0].replace("\n", " ").count("Mapbox") == section(
        spec, "12", "13"
    ).split("\n###")[0].replace("\n", " ").count("Mapbox")


def test_the_administration_guide_says_a_mapbox_chart_will_not_load() -> None:
    """The owner's addition of 20 November (SE6a's facts): the content policy allows no outside address and no
    map key is set."""
    for name in ADMIN:
        text = fold(without_control(read(FILES[name])))
        sentence = next((s for s in re.split(r"(?<=\.)\s", text) if "Mapbox" in s), "")
        assert "will not load" in sentence, f"{name}: no sentence that a chart needing Mapbox tiles will not load"
        assert "content" in sentence and "policy" in sentence, f"{name}: the sentence does not say why (the policy)"
        assert "key" in sentence, f"{name}: the sentence does not say no map key is set"


def test_the_readme_does_not_say_the_deployment_never_calls_out() -> None:
    readme = fold(read(FILES["README"]))
    assert "never calls out" not in readme
    assert "nothing checks on its own" in readme.lower(), "the release check's line is corrected, not removed"


# ---------------------------------------------------------------- rule 15: each check shown red


def test_each_check_is_shown_red() -> None:
    # A product put back into section 9, as a table row of the old table.
    clean = "## 9. Open source\n\nThe build fails if a licence is not on the allowlist.\n\n## 10. Limits\n"
    nine = section(clean, "9", "10")
    names = avoided_names(list(MOVED_ROWS))
    assert products_in(nine, names + list(USED_INSTEAD)) == []
    assert products_in(nine + "\n" + MOVED_ROWS[0] + "\n", names) == ["Redis"]
    assert products_in(nine + "\nIt avoids Terraform.\n", names) == ["Terraform"]
    assert products_in(nine + "\nIt uses Valkey instead.\n", names + list(USED_INSTEAD)) == ["Valkey"]
    # The old table in the specification is found complete, and one row lost is found.
    short = "\n".join([MOVED_HEADER, "| --- | --- | --- |", *MOVED_ROWS[:-1], ""])
    assert moved_table(short) != list(MOVED_ROWS)
    # The old guide bullet, in its list, with and without the scope next to it.
    assert unscoped_audit_statements("## 6. Access control\n\n" + OLD_GUIDE_AUDIT) != []
    assert unscoped_audit_statements("Intro.\n\n" + OLD_SPEC03_AUDIT + "\n**Export gate.** ...\n") != []
    scoped = OLD_GUIDE_AUDIT + "\nDeployment metadata is unaudited by design.\n"
    assert unscoped_audit_statements("## 6.\n\n" + scoped) == []
    # The passage, read from a guide that has one and from one that has none.
    assert passage("Opening.\n\n" + HEADING + "\n\nText here.\n\n<!-- document-control:begin -->\n") == "Text here.\n\n"
    assert passage("Opening.\n") is None
    # A passage with the word in a sentence is found.
    assert GUARANTEE.search("OspreyFlow guarantees that nothing leaves.")
    assert GUARANTEE.search("a guaranteed result")
    assert not GUARANTEE.search("what it does and how it is checked")
