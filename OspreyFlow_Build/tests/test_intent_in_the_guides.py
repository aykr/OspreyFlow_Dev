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
- the README's "the deployment never calls out" is corrected —
  `test_the_readme_does_not_say_the_deployment_never_calls_out`;
- the passages carry the limits the truth check found (privacy an aim with read-side gaps named, the export ledger
  scoped, what is outside the licence gate said to be coming) —
  `test_the_passages_carry_the_limits_the_truth_check_found`;
- section 9 does not say every avoided component has an alternative —
  `test_section_9_does_not_say_every_avoided_component_has_an_alternative`;
- (round 5) no sentence in any of the five files says the licence gate covers every or all dependencies without
  saying it does not yet reach every package inside the images, none says each store or engine sits behind a port,
  none says replaceable software holds a record hostage or "never" does anything, and the architecture guide says
  which stores are not behind a port —
  `test_no_file_states_the_licence_gate_or_replacement_without_its_limit`,
  `test_the_architecture_passage_says_which_stores_are_behind_a_port`;
- (round 6) the replacement claim is found in the shapes the text takes now (plurals, "all the stores", "any one of
  them can be swapped", "replacing any store", with or without the word "port"), in all five files and both copies,
  each planted back in each kind of file by `test_each_check_is_shown_red`; the two copies of the administration
  guide agree on a passage when only a link's target differs (it differs: `spec/` is not `docs/`), and no passage
  links to a file that is not there — `test_both_copies_of_the_administration_guide_agree_on_the_new_passages`,
  `test_no_passage_links_to_a_file_that_is_not_there`.

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


def without_link_targets(text: str | None) -> str | None:
    """A passage with each markdown link's target blanked, its text kept: the two copies of a guide sit in different
    folders, so the same link needs a different path in each (round 6), but not a different word."""
    return None if text is None else re.sub(r"\]\([^)\s]*\)", "](target)", text)


def dead_links(text: str | None, folder: Path) -> list[str]:
    """The relative links in a passage whose target is no file, read from the folder the file is in."""
    found = re.findall(r"\]\(([^)\s#]+)(?:#[^)\s]*)?\)", text or "")
    return [t for t in found if "://" not in t and not t.startswith("mailto:") and not (folder / t).is_file()]


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
    """Everything this slice wrote, by where it is: the passages, sections 6 and 9 of the architecture guide, the
    README's corrected line, and the paragraph above the moved table in `spec/00`. The specification's audit
    paragraph and the sentence on Superset's maps are added by `test_nothing_written_here_guarantees`."""
    out: dict[str, str] = {}
    for name, text in texts.items():
        body = passage(text)
        if body is not None:
            out[f"{name}: passage"] = body
    arch = texts[ARCHITECTURE]
    out["architecture guide: section 6"] = section(arch, "6", "7")
    out["architecture guide: section 9"] = section(arch, "9", "10")
    out["README: release check"] = release_check_line(texts["README"])
    out["spec/00: note above the moved table"] = moved_table_note(read(SPEC / "00_ARCHITECTURE.md"))
    return out


def release_check_line(readme: str) -> str:
    """The README's corrected paragraph on whether there is a newer release; empty when it is gone."""
    start = readme.find("**Is there a newer release?**")
    return readme[start : readme.index("\n\n", start)] if start >= 0 else ""


def moved_table_note(spec_00: str) -> str:
    """The paragraph this slice wrote above the moved table, from its bold lead-in to the table; empty if none."""
    start = spec_00.find("**The avoided components, as the architecture guide's section 9 stated them")
    return spec_00[start : spec_00.index(MOVED_HEADER, start)] if start >= 0 and MOVED_HEADER in spec_00 else ""


def bullet(body: str, name: str) -> str:
    """The item or paragraph of a passage that opens with the constraint's bold name; empty when none does."""
    found = re.search(rf"\*\*{re.escape(name)}[.:]\*\*(.*?)(?=\n\s*\n|\n- \*\*|\Z)", body, re.DOTALL)
    return fold(found.group(1)) if found else ""


#: A sentence that says "every"/"all" dependencies are covered by the licence check or are open source, in whatever
#: words (round 5: the user guide said "every software dependency is under an open-source licence ... outside the
#: check that holds that", with no "on every change" in it).
LICENCE_CLAIM = re.compile(r"\b(?:every|all)\s+(?:the\s+)?(?:software\s+)?dependenc", re.IGNORECASE)
LICENCE_NAMED = re.compile(r"licen[cs]e|\bgate\b|\bcheck\b", re.IGNORECASE)
#: What limits it: the gate does not yet reach every package inside the images, or is for two images only.
LICENCE_LIMIT = re.compile(
    r"not\s+(?:yet\s+)?(?:reach|cover)|does\s+not\s+yet|two\s+images|inside\s+(?:an|the)\s+images?"
    r"|only\s+for\s+two",
    re.IGNORECASE,
)
#: "each store or engine sits behind a port": PostgreSQL, Valkey and OpenSearch are not behind one. Round 6: in the
#: shapes the text takes now, not only the singular "behind a port": plurals ("behind ports"), "all the stores",
#: "any one of them can be swapped" (the README's "four typed ports so any one of them can be swapped"), "are all
#: replaceable", and "replacing any store", with or without the word "port".
_QUANT = r"(?:each|every|all|any)(?:\s+one)?(?:\s+of)?(?:\s+the)?"
_KIND = r"(?:stores?|engines?|components?|dependenc\w+|tiers?|layers?|parts?|them|these|those)"
PORT_CLAIM = re.compile(
    rf"\b{_QUANT}\s+{_KIND}\b[^.;]{{0,80}}\bbehind\s+(?:a\s+|the\s+|typed\s+|its\s+own\s+)*ports?\b"
    rf"|\b{_QUANT}\s+{_KIND}\b[^.;]{{0,60}}\b(?:can|could|may|will|must)\s+(?:all\s+)?be\s+"
    r"(?:swapped|replaced|exchanged|substituted)\b"
    rf"|\b{_QUANT}\s+{_KIND}\b[^.;]{{0,40}}\b(?:is|are)\s+(?:all\s+)?(?:swappable|replaceable|interchangeable)\b"
    rf"|\b(?:swapp?\w*|replac\w*|exchang\w*|substitut\w*)\s+(?:any|each|every|all)(?:\s+one)?(?:\s+of)?"
    rf"(?:\s+the)?\s+{_KIND}\b"
    rf"|\b{_KIND}\s+(?:all|each)\s+(?:sit|stand|are|live)\b[^.;]{{0,40}}\bbehind\b",
    re.IGNORECASE,
)
#: What stands before a claim that makes it a limit instead: "Not every store is behind a port".
NEGATED = re.compile(r"\b(?:not|never)\s*$", re.IGNORECASE)
HOSTAGE = re.compile(r"hostage", re.IGNORECASE)
NEVER_OF_SUPPLIERS = re.compile(r"\bnever\b", re.IGNORECASE)


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.;])\s+", fold(text)) if s.strip()]


def unlimited_claims(text: str) -> list[str]:
    """Round 5's three claims, by sentence and in any words: the licence check said to cover every dependency
    with no limit in the same or the next sentence; a port said to stand in front of each store or engine; and
    replaceable software said to keep a record from being held hostage, or a supplier's terms "never" to."""
    found: list[str] = []
    parts = sentences(text)
    for i, sentence in enumerate(parts):
        near = sentence + " " + (parts[i + 1] if i + 1 < len(parts) else "")
        if LICENCE_CLAIM.search(sentence) and LICENCE_NAMED.search(sentence) and not LICENCE_LIMIT.search(near):
            found.append("the licence check is said to cover every dependency, with no limit: " + sentence[:70])
        if any(not NEGATED.search(sentence[: m.start()]) for m in PORT_CLAIM.finditer(sentence)):
            found.append("each store or engine is said to sit behind a port: " + sentence[:70])
        if HOSTAGE.search(sentence):
            found.append("a supplier is implied to hold records hostage: " + sentence[:70])
        if NEVER_OF_SUPPLIERS.search(sentence) and re.search(r"suppliers?|vendors?", sentence, re.IGNORECASE):
            found.append("an absolute 'never' about a supplier or its terms: " + sentence[:70])
    return found


def overstated_lines(body: str) -> list[str]:
    """What the truth check does not support in a passage (DOC1A_REPORT.md rows 1, 3 and 4): privacy stated as
    fact with no read-side gap named, a ledger said to hold exports without its scope, and a licence statement
    that does not say what is outside the gate."""
    problems: list[str] = []
    privacy = bullet(body, "Privacy control").lower()
    if privacy and not ("gap" in privacy or "read side" in privacy):
        problems.append("privacy control names no read-side gap")
    for sentence in re.split(r"(?<=[.;:])\s+", privacy):
        if re.search(r"\bbounded\b|\bis left out\b|\bis absent\b", sentence) and not re.search(
            r"meant to|\baim\b", sentence
        ):
            problems.append("privacy control is stated as fact in: " + sentence[:60])
    security = bullet(body, "Security management").lower()
    if "ledger" in security and not re.search(r"report, assessment, pack|some (?:other )?exports", security):
        problems.append("the export ledger is not scoped to the exports that write it")
    if re.search(r"\bevery (?:change|mutation|write)\s+(?:is|are|was|were)\b", security):
        problems.append("an audit row for every change is claimed; the truth check supports mutations audited only")
    licence = bullet(body, "Software sovereignty").lower()
    if "licence" in licence and not ("weights" in licence and "coming" in licence):
        problems.append("the licence statement does not say what is outside the gate, as coming")
    if re.search(r"on every change", licence) and not re.search(
        r"not (?:yet )?(?:reach|cover|check)|only|two images|inside an image|inside the images", licence
    ):
        problems.append("the licence gate is said to check every dependency on every change, unlimited")
    problems += unlimited_claims(licence)
    return problems


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


def test_no_passage_links_to_a_file_that_is_not_there() -> None:
    """Round 6: the specification's copy of the administration guide sits in `spec/`, where `architecture-guide.md`
    is no file; its link has to be the path that resolves from there."""
    problems = {
        name: dead_links(passage(text), path.parent) for (name, path), text in zip(FILES.items(), _texts().values())
    }
    assert {n: d for n, d in problems.items() if d} == {}


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
        if not where.startswith("spec/")  # the internal specification is where the names now live
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


def test_the_passages_carry_the_limits_the_truth_check_found() -> None:
    texts = _texts()
    problems = {n: overstated_lines(passage(t) or "") for n, t in texts.items()}
    assert {n: p for n, p in problems.items() if p} == {}


def test_section_9_does_not_say_every_avoided_component_has_an_alternative() -> None:
    """The register's Grafana row records no alternative used, only that it is never bundled."""
    nine = fold(section(read(FILES[ARCHITECTURE]), "9", "10")).lower()
    assert "does not bundle" in nine or "not bundle" in nine
    assert not re.search(r"uses an open-source alternative instead\.", nine)


def test_both_copies_of_the_administration_guide_agree_on_the_new_passages() -> None:
    shipped, spec = (read(FILES[n]) for n in ADMIN)
    assert passage(shipped) is not None
    assert without_link_targets(passage(shipped)) == without_link_targets(passage(spec))
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


def test_no_file_states_the_licence_gate_or_replacement_without_its_limit() -> None:
    """Round 5: the whole of each file (less its version record), not only the passage, in any sentence shape."""
    problems = {
        name: unlimited_claims(without_control(text)) for name, text in _texts().items()
    }  # fmt: skip
    assert {n: p for n, p in problems.items() if p} == {}


def test_the_architecture_passage_says_which_stores_are_behind_a_port() -> None:
    """Section 2 puts four ports and three narrower ones in front of the graph store, the analytics store, graph
    algorithms, the models, the media store, recognition and the index feed; the relational store (the audit
    table and the export ledger), the working-set store and the search index are in front of none, so the
    passage must say so and must not claim replacement for them. It names them by what they do: the passage
    names no product (`test_the_passages_name_no_product`)."""
    bullet_text = fold(bullet(passage(read(FILES[ARCHITECTURE])) or "", "Software sovereignty")).lower()
    for behind in ("graph store", "analytics store", "graph algorithms", "model engines", "media store"):
        assert behind in bullet_text, f"the passage does not say the {behind} sits behind a port"
    for outside in ("relational store", "working-set store", "search index"):
        assert outside in bullet_text, f"the passage does not name the {outside} as outside the ports"
    assert re.search(r"not behind a port|behind no port|no port", bullet_text)
    assert "replacing one is not an adapter" in bullet_text


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
    # The overstated lines as they stood, in the shape a passage takes, are found; the corrected ones are not.
    old = (
        "- **Software sovereignty:** every software dependency is under an open-source licence.\n"
        "- **Privacy control:** what a person sees is bounded by handling markings and case membership.\n"
        "- **Security management:** case reads are audited, and exports go in a ledger.\n"
    )
    assert len(overstated_lines(old)) == 5  # the licence line is found twice: no weights, and no limit
    # The shapes the passages actually took before this round: each is found for its own reason.
    real_licence = (
        "- **Software sovereignty:** every software dependency is under an open-source licence, checked on every\n"
        "  change. Model weights are outside that check; a register and a gate for them are coming.\n"
    )
    found = overstated_lines(real_licence)
    assert len(found) == 2
    assert found[0] == "the licence gate is said to check every dependency on every change, unlimited"
    assert found[1].startswith("the licence check is said to cover every dependency, with no limit: every software")
    real_privacy = (
        "- **Privacy control:** What you see is bounded by handling markings and case membership. A record you\n"
        "  may not see is left out, and the aim is that no count reveals it either; known gaps\n"
        "  on the read side remain.\n"
    )
    assert len(overstated_lines(real_privacy)) == 1
    real_audit = "- **Security management:** case reads, refusals of access to a case and every change are audited.\n"
    assert len(overstated_lines(real_audit)) == 1
    assert overstated_lines(
        "- **Software sovereignty:** every dependency is open. Weights are outside it; a gate is coming.\n"
        "- **Privacy control:** meant to be bounded by markings. Some gaps on the read side are known.\n"
        "- **Security management:** report, assessment, pack and feed exports go in a ledger.\n"
    ) == []
    # The new text is read from the README's line and the specification's note, and a planted word there is found.
    line = release_check_line("x\n\n**Is there a newer release?** Ask.\n\nNext.\n")
    assert line == "**Is there a newer release?** Ask."
    note = "**The avoided components, as the architecture guide's section 9 stated them (a).**\nWords.\n\n"
    assert GUARANTEE.search(moved_table_note(note + MOVED_HEADER + "\n") + "It guarantees.") is not None
    assert moved_table_note(note + MOVED_HEADER + "\n").startswith("**The avoided components")

    # Round 5: each old sentence put back in the shape it took, in the file it was in, is found; the text now is not.
    old_user = (
        "- **Software sovereignty.** Your organisation can inspect, modify, host and replace the software you work\n"
        "  in: every software dependency is under an open-source licence. Model weights, map data, fonts and base\n"
        "  images are outside the check that holds that; a register and a gate for them are coming.\n"
    )
    found = overstated_lines(old_user)
    assert len(found) == 1 and "with no limit" in found[0], found
    assert unlimited_claims(old_user) != []
    old_dev = (
        "- **Software sovereignty.** You can inspect, modify, host and replace what you work with. Every software\n"
        "  dependency is under an open-source licence. Model weights, map data, fonts and base images are outside the\n"
        "  licence gate; a register and a gate for them are coming.\n"
    )
    assert unlimited_claims(old_dev) != []
    old_arch = (
        "**Software sovereignty.** You can inspect, modify, host and replace the software. Software you can\n"
        "replace means a supplier's change of terms never holds your records hostage. Here that means every\n"
        "dependency is under an open-source licence, and each store or engine sits behind a port (section 2), so\n"
        "replacing one is one adapter and one line of configuration. Weights are outside the gate; a gate is coming.\n"
    )
    kinds = " | ".join(unlimited_claims(old_arch))
    assert "implied to hold records hostage" in kinds
    assert "absolute 'never'" in kinds
    assert "behind a port" in kinds
    assert "no limit" in kinds
    # The wording that replaces them is not found.
    for fine in (
        "Your organisation can inspect, modify, host and replace the software. The software dependencies are under\n"
        "open-source licences, and a gate checks the build's package list on every change; it does not yet reach\n"
        "every package inside the images.\n",
        "The graph store, the analytics store, graph algorithms and the models sit behind ports. PostgreSQL,\n"
        "Valkey and OpenSearch are not behind a port.\n",
        "A package under the GPL never passes the gate.\n",
    ):
        assert unlimited_claims(fine) == [], fine
    # Other shapes the same claims take.
    assert unlimited_claims("The licence check covers all dependencies.\n") != []
    assert unlimited_claims("A gate reads every dependency's licence.\n") != []
    assert unlimited_claims("Every component sits behind a port.\n") != []
    assert unlimited_claims("A supplier's new terms can never hold you to ransom.\n") != []

    # Round 6: the shapes the replacement claim takes now, planted in each kind of file (a list item as the guides and
    # the README's passage have it; a paragraph as the README's "How it is built" has it), each found; the text is not.
    readme_86 = (
        "Three tiers, separated by four typed ports so any one of them can be swapped without touching the\n"
        "others:\n"
    )
    planted = {
        "README paragraph, 'any one of them can be swapped'": readme_86,
        "developer guide item, 'behind ports'": (
            "- **Software sovereignty.** Each store and engine sits behind ports, so an adapter is the unit of\n"
            "  replacement.\n"
        ),
        "user guide item, 'all the stores'": (
            "- **Software sovereignty.** All the stores sit behind ports, so you can replace any of them.\n"
        ),
        "administration guide item, no word 'port'": (
            "- **Software sovereignty.** Every store and engine can be replaced with one adapter.\n"
        ),
        "architecture guide, 'replacing any store'": (
            "**Software sovereignty.** Replacing any store is one adapter and one line of configuration.\n"
        ),
        "README, 'are all replaceable'": "The stores are all open source, and each of them is replaceable.\n",
        "plural, 'the components all sit behind'": "The components all sit behind typed ports.\n",
    }
    for where, text in planted.items():
        assert unlimited_claims(text) != [], where
    assert unlimited_claims("Not every store is behind a port. But every engine sits behind ports.\n") != []
    for where, text in planted.items():  # the same sentence among the README's and the guides' own text
        assert unlimited_claims("Opening words here.\n\n" + text + "\nMore words.\n") != [], where
    for fine in (
        "Three tiers, separated by four typed ports. Swapping the engine behind a port means one adapter.\n",
        "The graph store, the analytics store, graph algorithms and the model engines sit behind ports, so for them\n"
        "an adapter is the unit of replacement.\n",
        "Not every store is behind a port, and not all the stores can be replaced with an adapter.\n",
        "The graph store and the model engines sit behind ports (section 2), so for each of them replacing the engine\n"
        "is one adapter. The search index is not behind a port, so replacing it is not an adapter's work.\n",
    ):
        assert unlimited_claims(fine) == [], fine

    # Round 6: the two copies of a guide agree when only a link target differs, and not when a word does.
    one = "Opening.\n\n" + HEADING + "\n\nSee the [guide](architecture-guide.md) now.\n\n<!-- document-control:begin -->\n"
    other = one.replace("(architecture-guide.md)", "(../../OspreyFlow_Core/docs/architecture-guide.md)")
    assert passage(one) != passage(other)
    assert without_link_targets(passage(one)) == without_link_targets(passage(other))
    changed = other.replace("now", "later")
    assert without_link_targets(passage(one)) != without_link_targets(passage(changed))
    assert without_link_targets(passage(one)) != without_link_targets(passage(one.replace("[guide]", "[the guide]")))
    assert without_link_targets(None) is None
    # A link to no file is found, one to a file is not (the folder is this test's own).
    here = Path(__file__).parent
    assert dead_links("See [it](no-such-guide.md).", here) == ["no-such-guide.md"]
    assert dead_links("See [it](" + Path(__file__).name + ").", here) == []
    assert dead_links("See [it](https://example.org/x.md) and [that](#top).", here) == []
