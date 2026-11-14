"""The developer and architecture guides' ports, and the guides' search lines, held to the code (the docs lane's step 5
sweep, part 4; rule 12):

- each narrow port in `packages/ports` beside the four is named in both guides, `IndexFeedSource` among them
  (ADR-150), and the count they give is the count there is;
- the architecture guide gives search as it is built: OpenSearch, and without it (`postgres-fulltext`) the graph
  store's exact search alone, since no PostgreSQL full-text query exists in the code;
- the administration guide gives `opensearch_signing` as the platform settings file holds it and the render's
  `INSTALL.md` words it.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

CORE = Path(__file__).resolve().parents[2] / "OspreyFlow_Core"
DOCS = CORE / "docs"
PORTS = CORE / "packages" / "ports"
FOUR = {"GraphPort", "AnalyticsPort", "ComputePort", "ModelPort"}
#: GraphPort's own bulk loading path, in `ports/graph.py` beside it: not a port of its own to a reader.
NOT_A_PORT_OF_ITS_OWN = {"BulkGraphLoader"}
#: How the guides name each narrow port.
NARROW_NAMES = {"MediaStore": "media store", "RecognisePort": "recognition port", "IndexFeedSource": "`IndexFeedSource`"}
COUNTS = {2: "Two", 3: "Three", 4: "Four", 5: "Five"}


def fold(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def guide(name: str) -> str:
    """A guide without its document-control table, which records what earlier versions said, whitespace folded."""
    text = (DOCS / f"{name}-guide.md").read_text(encoding="utf-8")
    return fold(re.sub(r"<!-- document-control:begin -->.*?<!-- document-control:end -->", " ", text, flags=re.DOTALL))


def protocols() -> set[str]:
    found = set()
    for path in PORTS.glob("*.py"):
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.ClassDef) and any(getattr(b, "id", None) == "Protocol" for b in node.bases):
                found.add(node.name)
    return found


def narrow_ports_sentence(text: str) -> str:
    m = re.search(r"(\w+) narrower ports sit beside them: (.*?)\.(?: |$)", text)
    assert m, "the guide's narrower ports"
    return m.group(0)


def unnamed_narrow_ports(text: str, ports: set[str]) -> list[str]:
    sentence = narrow_ports_sentence(text)
    narrow = sorted(ports - FOUR - NOT_A_PORT_OF_ITS_OWN)
    missing = [p for p in narrow if NARROW_NAMES.get(p, p) not in sentence]
    if not sentence.startswith(f"{COUNTS.get(len(narrow), str(len(narrow)))} narrower ports"):
        missing.append(f"the count ({len(narrow)})")
    return missing


def test_each_narrow_port_is_a_protocol_the_guides_know() -> None:
    narrow = protocols() - FOUR - NOT_A_PORT_OF_ITS_OWN
    assert FOUR <= protocols()
    assert narrow == set(NARROW_NAMES), "a narrow port the guides have no name for: add it to NARROW_NAMES and both guides"


def test_both_guides_name_every_narrow_port() -> None:
    for name in ("developer", "architecture"):
        assert unnamed_narrow_ports(guide(name), protocols()) == [], name


def test_a_narrow_port_left_out_is_flagged() -> None:
    """The guides' own words before this sweep."""
    old = "Two narrower ports sit beside them: the media store, for content files, and the recognition port. "
    assert unnamed_narrow_ports(old, protocols()) == ["IndexFeedSource", "the count (3)"]


def test_the_index_feed_is_said_to_be_unreachable_from_a_route() -> None:
    """`ports/index_feed.py`: a separate Protocol from GraphPort, so no route can reach the unfiltered read (held by
    `tests/services/search_index/test_index_feed_reach.py`)."""
    source = (PORTS / "index_feed.py").read_text(encoding="utf-8")
    assert "so that no route, which is given a `GraphPort`, can reach the unfiltered read" in fold(source)
    assert "so that no route, which is given a GraphPort, can reach that unfiltered read" in guide("developer")
    assert "It is kept apart from GraphPort so that no route can reach that read" in guide("architecture")


# ---------------------------------------------------------------- search as built


def full_text_queries() -> list[str]:
    """Any PostgreSQL full-text query in the services or the adapters."""
    found = []
    for root in (CORE / "services", CORE / "packages" / "adapters"):
        for path in root.rglob("*.py"):
            if re.search(r"to_tsvector|plainto_tsquery|websearch_to_tsquery|@@ ?to_tsquery", path.read_text(encoding="utf-8")):
                found.append(str(path.relative_to(CORE)))
    return found


def test_the_architecture_guide_gives_search_as_built() -> None:
    text = guide("architecture")
    assert full_text_queries() == [], "a PostgreSQL full-text query exists now: the guide must say what it does"
    assert "PostgreSQL full-text" not in text
    deployment = (CORE / "packages" / "schemas" / "deployment.py").read_text(encoding="utf-8")
    assert 'POSTGRES_FULLTEXT = "postgres-fulltext"' in deployment
    service = (CORE / "services" / "api" / "search_service.py").read_text(encoding="utf-8")
    assert '"no_index": "Search is limited to exact identifiers: this deployment has no search index."' in service
    assert ("search (OpenSearch; where a deployment has none, `postgres-fulltext`, the graph store's exact search alone, "
            "and the screen says search is limited to exact identifiers)") in text  # fmt: skip


def test_the_opensearch_signing_setting_is_given_as_the_settings_file_holds_it() -> None:
    settings = (CORE / "harness" / "cloud_platform" / "settings.py").read_text(encoding="utf-8")
    assert 'opensearch_signing: Literal["sigv4", "none"] = "sigv4"' in settings
    runbook = fold((CORE / "harness" / "cloud_platform" / "runbooks.py").read_text(encoding="utf-8"))
    assert "with no fine-grained access control" in runbook and "(`opensearch_signing: none`)" in runbook
    assert "_opensearch_needs(config, platform)" in runbook, "the words are rendered into INSTALL.md"
    text = guide("administration")
    assert "How they reach it is the platform settings file's `opensearch_signing`. With `sigv4`, the default," in text
    assert "admits that role alone, with no fine-grained access control" in text
    assert "With `none`, for a platform whose own module fronts the domain with a proxy that signs for us" in text


def test_section_6a11_asks_about_opensearch_without_fine_grained_access_and_says_what_replaces_it() -> None:
    """Question 13 (the orchestrator's ruling, 14 November 2026): the domain the render makes, one IAM role and no
    fine-grained access control, and in its place the reader's access in OspreyFlow's own query to the index
    (`search_access.py`'s `index_access_filter`, given to every search by the route)."""
    settings = (CORE / "harness" / "cloud_platform" / "settings.py").read_text(encoding="utf-8")
    assert 'opensearch_signing: Literal["sigv4", "none"] = "sigv4"' in settings
    runbook = fold((CORE / "harness" / "cloud_platform" / "runbooks.py").read_text(encoding="utf-8"))
    assert "admits that role alone, with no fine-grained access control" in runbook.replace('" "', "")
    assert "two private subnets, in two availability zones" in runbook
    access = fold((CORE / "services" / "api" / "search_access.py").read_text(encoding="utf-8"))
    for part in ("1. **classification:** no higher than the principal's clearance", "2. **handling code:**",
                 "3. **datasets:** one of the case's"):  # fmt: skip
        assert part in access, part
    app = (CORE / "services" / "api" / "app.py").read_text(encoding="utf-8")
    for name in ("search_route", "suggest_route"):  # the results page's and the box's own routes
        route = next(n for n in ast.walk(ast.parse(app)) if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
        assert "access_filter=index_access_filter(index.scheme, principal)" in (ast.get_source_segment(app, route) or ""), name
    text = guide("administration")
    q13 = text[text.index("13. **OpenSearch without fine-grained access control.**") :]
    q13 = q13[: q13.index("## ")]
    assert "admits one IAM role, the namespace's, with no fine-grained access control and no OpenSearch users?" in q13
    assert ("OspreyFlow applies each reader's access in its own query to the index: the Conduit adds to every "
            "search, before it is sent, a filter that keeps only what the reader's clearance, handling codes and "
            "the case's datasets allow") in q13  # fmt: skip
    assert "(`opensearch_signing: none`, section 6a.1)" in q13 and "two private subnets, in two availability zones" in q13
