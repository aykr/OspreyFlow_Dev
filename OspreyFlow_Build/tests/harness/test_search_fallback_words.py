"""What the deployment's words say search does without OpenSearch, held to what search does.

The rendered RUNBOOK.md, Preflight's offer of the reduced variant, its memory check's advice and
`spec/05_DEPLOYMENT.md` §3 said full-text "falls back to PostgreSQL". Nothing searches PostgreSQL:
there is no `to_tsvector` or `tsquery` in the Conduit or the adapters (docs' v0.5.2 sweep,
EARLY_FACTS.md §4). With no search index (`search: postgres-fulltext`), or when OpenSearch does
not answer (ADR-150's fallback), `search_service.search_page` answers from the graph store's own
exact search, at most `FALLBACK_DEPTH` matches and with no date filter, and the page says why in
`LIMITED_REASONS`' words. Each case below drives that real fallback and checks the words against
what it answered, so the words cannot drift from it."""

from __future__ import annotations

import re
from pathlib import Path

from harness.preflight import memory
from harness.preflight.context import PreflightContext
from harness.preflight.reduced import offer_for
from harness.render import render
from services.api import search_service as s

from schemas.deployment import OspreyConfig, SearchBackend
from schemas.search import SearchPageRequest
from tests.harness.test_preflight import GIB, config, context, rendered_dir  # noqa: F401
from tests.harness.test_render import _fake_resolver
from tests.services.api.test_search_service import _ask, _Graph, _Index, _typed

_SPEC = Path(__file__).resolve().parents[2] / "spec/05_DEPLOYMENT.md"
_WRONG = re.compile(r"PostgreSQL full-text|falls\s+back\s+to\s+PostgreSQL", re.IGNORECASE)


def _answered(index: _Index | None) -> str:
    """The reason the real fallback gives, asked as the search page asks it."""
    out = _ask(SearchPageRequest(query="AB123456C"), _Graph(exact=[_typed("p1")]), index)
    assert out.source == "fallback" and out.limited_reason is not None
    return out.limited_reason


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _search_line(cfg: OspreyConfig) -> str:
    runbook = render(cfg, resolver=_fake_resolver).artefacts["RUNBOOK.md"]
    [line] = [p for p in runbook.split("\n\n") if p.startswith("Search backend:")]
    return _flat(line)


def _reduced(cfg: OspreyConfig) -> OspreyConfig:
    return cfg.model_copy(
        update={
            "components": cfg.components.model_copy(
                update={"search": SearchBackend.POSTGRES_FULLTEXT}
            )
        }
    )


def test_the_runbook_says_what_search_does_with_no_index(config: OspreyConfig) -> None:  # noqa: F811
    line = _search_line(_reduced(config))
    assert not _WRONG.search(line), line
    assert "exact search" in line and f"at most {s.FALLBACK_DEPTH} matches" in line, line
    assert _answered(None) in line, line


def test_the_runbook_says_what_search_does_when_opensearch_does_not_answer(
    config: OspreyConfig,  # noqa: F811
) -> None:
    assert config.components.search is SearchBackend.OPENSEARCH
    line = _search_line(config)
    assert not _WRONG.search(line), line
    assert _answered(_Index(error=s.IndexUnavailable("refused"))) in line, line


def test_preflight_offers_the_reduced_variant_in_what_it_does(context: PreflightContext) -> None:  # noqa: F811
    context.memory_probe = lambda: 8 * GIB
    result = memory.check(context)
    assert not _WRONG.search(result.what_to_do), result.what_to_do
    offer = offer_for([result], context.config)
    assert offer is not None
    text = _flat(offer.render_text())
    assert not _WRONG.search(text), text
    assert "semantic search" not in text, "no semantic search is built for it to lose"
    assert _answered(None) in text, text


def test_spec_05_says_what_the_reduced_variant_searches_with() -> None:
    text = _flat(_SPEC.read_text(encoding="utf-8"))
    start = text.index("If Preflight finds less than 16 GB")
    section = text[start : text.index("### 3.1", start)]
    assert not _WRONG.search(section), section
    assert "semantic search" not in section, section
    assert _answered(None) in section, section
    assert _answered(_Index(error=s.IndexUnavailable("refused"))) in section, section
